#pragma once
/*
    Pure frame-conversion math. NO ROS, NO px4_msgs — depends only on Vec3 and
    <cmath>, so it is unit-testable with a standalone g++ (see test/frame_convert_test.cpp).

    Canonical world frame across the DroneBackend seam is ENU (East, North, Up+);
    PX4 speaks NED (North, East, Down+) on the wire. Body-relative VLM commands are
    FLU (Forward, Left, Up+). Every conversion below is a NAMED function so call
    sites document intent instead of carrying bare sign flips.
*/
#include <cmath>
#include <util2/C/base_type.h>
#include <util2/C/macro.h>


struct Vec3 { f32 x{0.0f}, y{0.0f}, z{0.0f}; };


static inline f32 wrap_pi(f32 a) {
    const f32 kPi = __scast(f32, M_PI);
    while (a >  kPi) a -= 2.0f * kPi;
    while (a < -kPi) a += 2.0f * kPi;
    return a;
}

/* Body FLU (fwd,left,up) -> world NED (north,east,down). yaw is NED (CW+ from north). */
static inline Vec3 flu_to_ned(Vec3 flu, f32 yawNed) {
    f32 c = std::cos(yawNed);
    f32 s = std::sin(yawNed);
    return { flu.x * c + flu.y * s,     /* north */
             flu.x * s - flu.y * c,     /* east  */
            -flu.z };                   /* down  */
}

/* Position/velocity swaps: (E,N,U) <-> (N,E,D). Self-inverse. */
static inline Vec3 ned_to_enu(Vec3 v) { return { v.y, v.x, -v.z }; }
static inline Vec3 enu_to_ned(Vec3 v) { return { v.y, v.x, -v.z }; }

/* Heading: NED (CW+ from North) <-> ENU (CCW+ from East). Same algebraic form. */
static inline f32 enu_yaw_from_ned(f32 yawNed) { return wrap_pi(__scast(f32, M_PI_2) - yawNed); }
static inline f32 ned_yaw_from_enu(f32 yawEnu) { return wrap_pi(__scast(f32, M_PI_2) - yawEnu); }

/* Yaw-rate sign flips between CW+ and CCW+. */
static inline f32 enu_yawrate_to_ned(f32 r) { return -r; }

/* Body FLU -> world ENU: compose through NED so every sign stays consistent. */
static inline Vec3 flu_to_enu(Vec3 flu, f32 yawEnu) {
    return ned_to_enu(flu_to_ned(flu, ned_yaw_from_enu(yawEnu)));
}

/* World ENU -> body FLU: exact inverse of flu_to_enu. A vehicle at heading yawEnu
   (CCW+ from East) has forward=(cos,sin), left=(-sin,cos) in the ENU horizontal
   plane; projecting a world vector onto that body basis is the rotation transpose. */
static inline Vec3 enu_to_flu(Vec3 enu, f32 yawEnu) {
    f32 c = std::cos(yawEnu);
    f32 s = std::sin(yawEnu);
    return {  enu.x * c + enu.y * s,     /* forward */
             -enu.x * s + enu.y * c,     /* left    */
              enu.z };                   /* up      */
}
