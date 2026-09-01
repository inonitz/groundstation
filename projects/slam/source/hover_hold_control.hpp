#pragma once
/*
    hover_hold_control -- the position-hold control law for the Tello, as pure math.

    NO ROS, NO backend -- depends only on Vec3 + <cmath>, so it is unit-testable with
    a standalone g++ (see test/hover_hold_control_test.cpp) and wired unchanged into
    whichever hover-hold node consumes it (SLAM-fed or ArUco-fed -- the controller does
    not care where the position error came from).

    Design, tuned for THIS sensor (see the PID discussion in the plan):
      - P-dominant. `Kp * error` is the workhorse; gentle so a laggy/jittery estimate
        does not oscillate.
      - Small I with hard anti-windup, to trim steady bias (the Tello drifts on a blind
        VPS). Clamped so a drifting estimate cannot wind it up and drive the drone off,
        and reset() drops it on a tracking pause so it never integrates stale error.
      - NO raw derivative term. We have no clean velocity (vgx/vgy are the blind VPS
        channel) and differentiating a jittery position estimate injects noise. Damping,
        if needed, comes from a filtered input upstream (the OneEuro in slam_pose_bridge),
        not a D term here.
      - Deadband + output clamp: ignore sub-noise error, and never command more than a
        gentle indoor speed.

    Frame: the controller is frame-agnostic. The caller supplies the position error in a
    consistent control frame (marker frame for ArUco, ENU for SLAM) and maps the returned
    velocity back to the backend's expected frame. Vertical (z) is left to the caller /
    height loop; this holds the horizontal plane and returns z = 0.
*/
#include <cmath>
#include "frame/frame_convert.hpp"   /* Vec3, f32 */


struct HoverHoldConfig {
    f32 mk_kp{0.8f};        /* 1/s : velocity per metre of error.                    */
    f32 mk_ki{0.15f};       /* 1/s2: gentle steady-bias trim.                        */
    f32 mk_maxVel{0.4f};    /* m/s : output clamp, deliberately gentle indoors.      */
    f32 mk_maxIntg{0.2f};   /* m/s : anti-windup clamp on the integral contribution. */
    f32 mk_deadband{0.03f}; /* m   : ignore sub-3cm error (noise floor).             */
};

struct HoverHoldController {
    HoverHoldConfig m_cfg{};
    f32             m_ix{0.0f};   /* integral contribution (m/s), per axis. */
    f32             m_iy{0.0f};

    /* Drop the integrator. Call on a tracking pause or a setpoint jump so stale error
       never accumulates. */
    void reset() {
        m_ix = 0.0f;
        m_iy = 0.0f;
        return;
    }

    /* posError = setpoint - measured, in the control frame. Returns the horizontal
       velocity command (z = 0); the caller maps it to the backend frame. */
    Vec3 update(Vec3 posError, f32 dt) {
        return { axis(posError.x, m_ix, dt),
                 axis(posError.y, m_iy, dt),
                 0.0f };
    }

private:
    f32 axis(f32 err, f32& intg, f32 dt) {
        if (std::fabs(err) < m_cfg.mk_deadband) {
            err = 0.0f;               /* inside the deadband: no push, no integration. */
        }
        intg += m_cfg.mk_ki * err * dt;
        if (intg >  m_cfg.mk_maxIntg) intg =  m_cfg.mk_maxIntg;   /* anti-windup clamp. */
        if (intg < -m_cfg.mk_maxIntg) intg = -m_cfg.mk_maxIntg;

        f32 v = m_cfg.mk_kp * err + intg;
        if (v >  m_cfg.mk_maxVel) v =  m_cfg.mk_maxVel;           /* output clamp.      */
        if (v < -m_cfg.mk_maxVel) v = -m_cfg.mk_maxVel;
        return v;
    }
};
