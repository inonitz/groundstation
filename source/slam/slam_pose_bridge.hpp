#pragma once
/*
    slam_pose_bridge -- the pure math that turns a stella_vslam pose (map frame,
    up-to-scale) into a metric ENU XY the Tello control loop can hold on.

    NO ROS, NO backend, NO stella headers -- depends only on Vec3 + <cmath>, so it
    is unit-testable with a standalone g++ (see test/slam_pose_bridge_test.cpp) and
    reused unchanged by both the C2 hover-hold test node and the later FMU
    integration. The ROS/stella plumbing (subscribe slam/pose, read Tello height,
    feed setSlamPose) lives in the caller; this file is the algebra only.

    Three jobs:
      1. Align the SLAM map to a pseudo-ENU at init -- capture the initial map
         heading so map-horizontal rotates into a world frame whose +x is the
         drone's start heading (same pseudo-world convention the Tello yaw uses).
      2. Resolve monocular scale from the metric Tello height: scale = metric_height
         / slam_vertical, smoothed by a running median (scale is quasi-constant, so
         a median rejects the per-frame height/pose noise that would wobble XY).
      3. Optionally OneEuro-filter the output XY before the controller -- a HYPOTHESIS
         behind an on/off switch (default off), decided empirically in the C2 test.
         The filter must be reset()/frozen when tracking is paused so it never coasts
         on stale values and hides a loss.

    CONVENTION NOTE: which PoseStamped fields are "map-horizontal (x,y)", which is
    "slam_vertical", and the sign of the map yaw are stella conventions the CALLER
    supplies (validated against real slam/pose during C1). This header is agnostic to
    that choice -- its rotation/scale/filter math is correct for any consistent
    mapping the node feeds it.
*/
#include <cmath>
#include "frame/frame_convert.hpp"   /* Vec3, wrap_pi, f32 */


/* ---- OneEuro scalar filter (Casiez et al.) --------------------------------
   Low lag when the signal moves fast, heavy smoothing when it is still -- the
   right shape for a station-keep position signal. dt is seconds since the last
   sample. reset() drops it back to first-sample passthrough. */
struct OneEuroFilter {
    f32  mk_minCutoff{1.0f};   /* Hz: smoothing floor when still.        */
    f32  mk_beta{0.05f};       /* speed coefficient: how fast it de-lags. */
    f32  mk_dCutoff{1.0f};     /* Hz: cutoff for the derivative estimate. */

    bool mb_init{false};
    f32  m_xPrev{0.0f};
    f32  m_dxPrev{0.0f};

    void reset() { mb_init = false; m_xPrev = 0.0f; m_dxPrev = 0.0f; return; }

    f32 filter(f32 x, f32 dt) {
        if (!mb_init || dt <= 0.0f) {
            m_xPrev  = x;
            m_dxPrev = 0.0f;
            mb_init  = true;
            return x;
        }
        f32 dx    = (x - m_xPrev) / dt;
        f32 aD    = alpha(mk_dCutoff, dt);
        f32 dxHat = aD * dx + (1.0f - aD) * m_dxPrev;
        f32 cut   = mk_minCutoff + mk_beta * std::fabs(dxHat);
        f32 a     = alpha(cut, dt);
        f32 xHat  = a * x + (1.0f - a) * m_xPrev;
        m_xPrev   = xHat;
        m_dxPrev  = dxHat;
        return xHat;
    }

private:
    static f32 alpha(f32 cutoff, f32 dt) {
        f32 tau = 1.0f / (2.0f * __scast(f32, M_PI) * cutoff);
        return 1.0f / (1.0f + tau / dt);
    }
};


/* ---- Running-median scale smoother ----------------------------------------
   Scale is quasi-constant, so a small median rejects the spikes a mean would
   smear. Window is odd so the median is a real sample. */
struct ScaleMedian {
    static constexpr u32 kWindow = 9;
    f32 m_buf[kWindow]{};
    u32 m_count{0};

    void push(f32 s) {
        /* Ring by shifting once full -- kWindow is tiny, the copy is cheap and
           keeps value() a simple sort of the live samples. */
        if (m_count < kWindow) {
            m_buf[m_count++] = s;
            return;
        }
        for (u32 i = 1; i < kWindow; ++i) m_buf[i - 1] = m_buf[i];
        m_buf[kWindow - 1] = s;
        return;
    }

    f32 value() const {
        if (m_count == 0) return 1.0f;
        f32 tmp[kWindow];
        for (u32 i = 0; i < m_count; ++i) tmp[i] = m_buf[i];
        /* insertion sort -- kWindow <= 9, no reason for anything fancier. */
        for (u32 i = 1; i < m_count; ++i) {
            f32 v = tmp[i];
            u32 j = i;
            while (j > 0 && tmp[j - 1] > v) { tmp[j] = tmp[j - 1]; --j; }
            tmp[j] = v;
        }
        return tmp[m_count / 2];
    }
};


/* ---- Map->ENU alignment + scale -------------------------------------------- */
struct BridgeAlignment {
    bool        mb_haveYaw0{false};
    f32         m_yaw0{0.0f};        /* map heading at init; ENU east = this heading. */
    ScaleMedian m_scale;
    bool        mb_haveScale{false};
};

/* Capture the initial map heading so map-horizontal rotates into pseudo-ENU. */
static inline void bridgeInitYaw(BridgeAlignment& a, f32 mapYaw0) {
    a.m_yaw0       = mapYaw0;
    a.mb_haveYaw0  = true;
    return;
}

/* Feed one metric-height / slam-vertical pair into the scale estimate. Guarded so
   a ground reading (height ~0) or a degenerate slam vertical cannot poison it. */
static inline void bridgeUpdateScale(BridgeAlignment& a, f32 slamVertical, f32 metricHeightM) {
    if (metricHeightM <= 0.05f) return;               /* on the ground / bad tof. */
    if (std::fabs(slamVertical) < 1e-3f) return;      /* degenerate slam vertical. */
    f32 s = metricHeightM / std::fabs(slamVertical);
    if (s <= 0.0f || s > 1.0e4f) return;              /* obvious garbage.          */
    a.m_scale.push(s);
    a.mb_haveScale = true;
    return;
}

/* Rotate a map-horizontal (x,y) into pseudo-ENU and scale to metres. Height passes
   through from the metric source (tof/baro), never from the up-to-scale slam z.
   Returns ENU (x=East, y=North, z=Up). */
static inline Vec3 bridgeMapToMetricEnu(BridgeAlignment const& a, f32 mapX, f32 mapY, f32 metricHeightM) {
    f32 s  = a.mb_haveScale ? a.m_scale.value() : 1.0f;
    f32 c  = std::cos(-a.m_yaw0);
    f32 sn = std::sin(-a.m_yaw0);
    f32 ex = (mapX * c - mapY * sn) * s;              /* East  */
    f32 ny = (mapX * sn + mapY * c) * s;              /* North */
    return { ex, ny, metricHeightM };
}

/* Yaw about the +z axis from a quaternion (standard ENU form). Which map axis is
   "up" is a stella convention the caller confirms in C1; if it is z, this is the
   map heading to feed bridgeInitYaw / the ENU rotation. */
static inline f32 yawAboutZ(f32 qx, f32 qy, f32 qz, f32 qw) {
    return std::atan2(2.0f * (qw * qz + qx * qy),
                      1.0f - 2.0f * (qy * qy + qz * qz));
}


/* ---- Optional OneEuro on the output XY (toggleable, default off) ------------ */
struct XyOneEuro {
    OneEuroFilter m_fx;
    OneEuroFilter m_fy;
    bool          mb_enabled{false};   /* the ON/OFF switch the C2 test flips. */

    void reset() { m_fx.reset(); m_fy.reset(); return; }

    /* Filters ENU XY in place when enabled; passes through otherwise. Freeze by
       calling reset() on a tracking pause so it never coasts on stale values. */
    Vec3 apply(Vec3 enu, f32 dt) {
        if (!mb_enabled) return enu;
        return { m_fx.filter(enu.x, dt), m_fy.filter(enu.y, dt), enu.z };
    }
};
