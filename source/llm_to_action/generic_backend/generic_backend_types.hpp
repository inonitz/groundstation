#pragma once
/*
    Generic backend-interface types -- the SINGLE definition of the platform-neutral
    shapes every drone backend exposes across the backend interface. Previously these were
    duplicated in px4_backend.hpp and tello_backend_base.hpp and had already
    drifted apart (IOState 4- vs 3-valued; Odometry with/without yawrate). Both
    concrete backends now include this file so there is exactly one definition.

    Reconciled to the SUPERSET so no backend loses information: IOState carries
    PX4's HANDSHAKING (Tello simply never emits it), and Odometry carries PX4's
    yawrate (Tello leaves it 0).

    Frame: canonical world frame across the backend interface is the ENU convention (East, North, Up+).
*/
#include <util2/C/base_type.h>
#include "frame/frame_convert.hpp"   /* Vec3 */


/* Verb result. Minimal set; grow only when a caller branches on a new code. */
struct BackendStatus {
    enum class Code : u8 { OK, PENDING, REJECTED, FAULT };
    Code code{Code::OK};
};

/* Backend-owned wire/flight state machine. Superset of both backends: Tello
   uses only {STANDBY, FLIGHT, FAULT}; PX4 additionally uses HANDSHAKING for the
   arm->OFFBOARD handshake. */
enum class IOState : u8 { STANDBY, HANDSHAKING, FLIGHT, FAULT };

/* Platform-neutral telemetry snapshot handed to the FMU (world frame, ENU).
   PX4 fills every field; Tello has no absolute horizontal position (pos is
   height-only, x=y=0) and no yaw-rate estimate (yawrate stays 0). */
struct Odometry {
    Vec3 pos;                 /* world position ENU (x=East, y=North, z=Up).      */
    Vec3 vel;                 /* world velocity ENU -- measured, for debug/LAND.  */
    f32  yaw{0.0f};           /* heading ENU (CCW+ from East, radians).           */
    f32  yawrate{0.0f};       /* body yaw-rate (rad/s) -- PX4 only; Tello 0.      */
    u64  host_stamp_us{0};    /* HOST clock at receipt (staleness).               */
    bool valid{false};        /* false until first telemetry ever received.       */
};
