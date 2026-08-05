#pragma once
/*
    TelloBackend I/O contract -- the SINGLE source of truth for everything
    Tello-specific: SDK ports, the stream rate, the on-wire state schema, the
    velocity<->stick mapping, and the platform-neutral verb result / telemetry
    shapes shared with the FMU seam.

    Mirrors px4_backend_base.hpp's role for PX4: nothing Tello-specific should be
    hardcoded inside tello_backend.cpp; it all lives here so a reviewer retargets
    ports / rates / tuning in one file.

    Pure and ROS-free: depends only on util2 base types + frame_convert.hpp, so
    the parser and the frame/stick math stay unit-testable in isolation
    (see test/tello_convert_test.cpp).

    Frame: canonical world frame across the DroneBackend seam is ENU (East, North,
    Up+). Tello's `rc a b c d` is body FLU-ish (right, forward, up, yaw-CW). The
    ENU->FLU conversion is the single edge; see enu_to_flu in frame_convert.hpp.
*/
#include <cmath>
#include <cstdio>
#include <util2/C/base_type.h>
#include <util2/C/macro.h>
#include "frame/frame_convert.hpp"
#include "generic_backend/generic_backend_types.hpp"  /* BackendStatus, IOState, Odometry */


/* ---- Tello SDK 2.0 UDP endpoints (ctello binds cmd + state internally) ----- */
/* Video H264 elementary stream (decode is the caller's job, not ctello's).     */
constexpr const char* kTelloCmdHost      = "192.168.10.1";
constexpr u16         kTelloCmdPort      = 8889;   /* command / response          */
constexpr u16         kTelloStatePort    = 8890;   /* telemetry (ctello GetState) */
constexpr u16         kTelloVideoPort    = 11111;  /* raw H264 (test harness only)*/

/* ---- Stream loop tuning --------------------------------------------------- */
/* Tello holds the last `rc` for ~a few hundred ms then hovers/auto-lands, so we
   must re-push the setpoint continuously. It cannot ingest >~20Hz reliably.     */
constexpr u32 kTelloStreamRateHz         = 20;
constexpr u32 kTelloStatePollHz          = 10;   /* GetState() poll cadence      */

/* ---- Velocity <-> stick mapping ------------------------------------------- */
/* `rc` sticks are dimensionless [-100,100], NOT m/s. Tello reaches roughly this
   ground speed at full deflection; a first estimate, calibrated on the teleop run
   (plan: hardware calibration of the stick<->m/s constant).                     */
constexpr f32 kTelloMaxSpeedMps          = 1.0f;
constexpr i32 kTelloStickMax             = 100;
/* Full yaw stick corresponds to roughly this body yaw rate (rad/s ~= 180 deg/s). */
constexpr f32 kTelloMaxYawRateRadps      = __scast(f32, M_PI);

/* Body FLU stick quad sent as `rc a b c d` (a=roll/right, b=pitch/fwd,
   c=throttle/up, d=yaw/CW). Ints in [-100,100].                                 */
struct RcCommand { i32 a{0}, b{0}, c{0}, d{0}; };


/* Map a world/body velocity component (m/s) to a Tello stick, saturating. */
static inline i32 mps_to_stick(f32 mps) {
    i32 s = __scast(i32, std::lroundf(mps / kTelloMaxSpeedMps * __scast(f32, kTelloStickMax)));
    if (s >  kTelloStickMax) return  kTelloStickMax;
    if (s < -kTelloStickMax) return -kTelloStickMax;
    return s;
}

/* Inverse: a stick back to the m/s it commands (for round-trip / debug). */
static inline f32 stick_to_mps(i32 stick) {
    return __scast(f32, stick) / __scast(f32, kTelloStickMax) * kTelloMaxSpeedMps;
}

/* Map a body yaw rate (rad/s, CCW+) to a Tello yaw stick, saturating. Tello's
   yaw stick d is CW+, so a CCW+ (ENU) rate maps to -d. */
static inline i32 yawrate_to_stick(f32 radps) {
    i32 s = __scast(i32, std::lroundf(-radps / kTelloMaxYawRateRadps * __scast(f32, kTelloStickMax)));
    if (s >  kTelloStickMax) return  kTelloStickMax;
    if (s < -kTelloStickMax) return -kTelloStickMax;
    return s;
}

/* Body FLU velocity (fwd,left,up in m/s) + a yaw stick -> the `rc` quad.
   Tello roll stick a is +right, so left maps to -a.                            */
static inline RcCommand flu_to_rc(Vec3 flu, i32 yawStick) {
    RcCommand rc;
    rc.a = mps_to_stick(-flu.y);   /* right = -left */
    rc.b = mps_to_stick( flu.x);   /* forward       */
    rc.c = mps_to_stick( flu.z);   /* up            */
    rc.d = yawStick;               /* already a stick (deg/s intent) */
    return rc;
}


/* ---- On-wire state schema (Tello SDK state string) ------------------------- */
/* POD image of the semicolon-delimited state line. Ints in native units
   (deg, cm/s, cm, %, ...); floats: baro (cm), agx/agy/agz (0.001 g).            */
struct TelloState {
    i32 pitch{0}, roll{0}, yaw{0};       /* attitude, degrees                    */
    i32 vgx{0},  vgy{0},  vgz{0};        /* body velocity, cm/s                  */
    i32 templ{0}, temph{0};              /* IMU temperature range, C             */
    i32 tof{0};                          /* time-of-flight height, cm            */
    i32 h{0};                            /* barometric height, cm                */
    i32 bat{0};                          /* battery, percent                     */
    f32 baro{0.0f};                      /* barometer, cm                        */
    i32 time{0};                         /* motor-on time, s                     */
    f32 agx{0.0f}, agy{0.0f}, agz{0.0f}; /* acceleration, 0.001 g                */
};

/* Branchless-ish single-shot parse of the exact 16-field SDK line. Returns true
   only when all 16 fields were consumed; never partially accepts.               */
static inline bool parse_tello_state_branchless(const char* buffer, TelloState& state) {
    if (!buffer) return false;
    int parsed = std::sscanf(buffer,
        "pitch:%d;roll:%d;yaw:%d;vgx:%d;vgy:%d;vgz:%d;templ:%d;temph:%d;tof:%d;"
        "h:%d;bat:%d;baro:%f;time:%d;agx:%f;agy:%f;agz:%f;",
        &state.pitch, &state.roll, &state.yaw, &state.vgx, &state.vgy, &state.vgz,
        &state.templ, &state.temph, &state.tof, &state.h, &state.bat, &state.baro,
        &state.time, &state.agx, &state.agy, &state.agz);
    return (parsed == 16);
}


/* ---- Platform-neutral seam types --------------------------------------------
   BackendStatus / IOState / Odometry are defined once in
   generic_backend_types.hpp (included above) and shared with every backend.
   Tello uses the IOState subset {STANDBY, FLIGHT, FAULT} and leaves
   Odometry.yawrate at 0 (no yaw-rate estimate). --------------------------------*/
