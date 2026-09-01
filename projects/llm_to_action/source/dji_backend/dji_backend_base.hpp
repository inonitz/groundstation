#pragma once
/*
    DjiBackend I/O contract (part 1 of 2) -- the DJI-bridge wire constants and the
    PURE, dependency-light control math: LAN endpoints, stream/poll rates, the
    velocity envelope (clamp), the ENU-world -> body FlightParam map, and the
    FlightParam JSON serialiser.

    This half pulls NO JSON library, so it is safe to include from dji_backend.hpp
    and therefore from the FMU translation unit (whose strict -Werror warning set
    would choke on nlohmann's headers). The /status/ *parse* lives next door in
    dji_status_parse.hpp, included only by dji_backend.cpp + the unit test.

    Mirrors tello_backend_base.hpp's role: nothing DJI-specific is hardcoded in
    dji_backend.cpp; host/port/rates/tuning all retarget in ONE file.

    Wire (FROZEN, docs/active/spec-dji-websocket-protocol.md):
      Control   WS  /c/ws/sticks : client streams FlightParam = {vx,vy,vz,yaw},
                    BODY-frame m/s (vx fwd, vy RIGHT, vz up) + yaw rate; the app
                    flushes to the drone at ~18 Hz. The stream is the keepalive.
      Telemetry GET /status/      : aircraft.{isFlying,battery,velocity3D,...}.
      Verbs     POST /c/takeoff, /c/land (discrete).

    Frame: canonical world frame across the backend interface is ENU (E,N,Up+).
    DJI FlightParam is body Forward-Right-Up. enu_to_flu(worldVelEnu, yaw) gives
    body Forward-LEFT-Up, so FlightParam.vy = -left (= right). Single edge:
    enu_vel_to_flightparam() below.
*/
#include <cmath>
#include <cstdio>
#include <cstddef>
#include <util2/C/base_type.h>
#include "frame/frame_convert.hpp"


/* ---- LAN endpoints (mock or the real phone; set at construction) ----------- */
/* The mock: ws://127.0.0.1:8080 + http://127.0.0.1:8080. Real: the phone's IP.  */
constexpr const char* kDjiDefaultHost   = "127.0.0.1";
constexpr u16         kDjiDefaultPort   = 8080;
constexpr const char* kDjiSticksPath    = "/c/ws/sticks";
constexpr const char* kDjiStatusPath    = "/status/";
constexpr const char* kDjiTakeoffPath   = "/c/takeoff";
constexpr const char* kDjiLandPath      = "/c/land";
/* Raw-video TCP stream: the app (VideoTcpServer.kt, DEFAULT_STREAM_PORT) LISTENS here;
   the Linux receiver connects in and reads a raw H.264/H.265 Annex-B elementary stream. */
constexpr u16         kDjiVideoPort     = 5600;

/* ---- Loop tuning ----------------------------------------------------------- */
/* The app flushes sticks to the drone at ~18 Hz; matching it keeps the keepalive
   fed without spamming. MSDK telemetry updates ~10 Hz, so 15 Hz polling just
   re-reads occasionally -- cheap, and it bounds staleness.                      */
constexpr u32 kDjiStreamRateHz          = 18;
constexpr u32 kDjiStatusPollHz          = 15;

/* ---- Velocity + yaw-rate envelope (clamp) --------------------------------- */
/* vx/vy/vz: m/s, conservative until the app author confirms the virtual-stick
   limits (dji-apiserver-review.md Q5). yaw: DJI ANGULAR_VELOCITY range is
   +/-100 deg/s (SDK VirtualStickRange.YAW_CONTROL_MAX_ANGULAR_VELOCITY),
   CONFIRMED against ExoSkeletons DJIVirtualStick.build() (yawControlMode =
   ANGULAR_VELOCITY -> deg/s). One place to widen once measured.                 */
constexpr f32 kDjiMaxSpeedMps           = 2.0f;
constexpr f32 kDjiMaxYawRateDegps       = 100.0f;              /* SDK hard ceiling */
constexpr f32 kRadToDeg                 = __scast(f32, 180.0 / M_PI);

/* ---- Yaw-rate sign (CONFIRMED) -------------------------------------------- */
/* On the wire FlightParam.yaw is a body yaw RATE in DEG/S (DJI ANGULAR_VELOCITY).
   DJI positive yaw = CLOCKWISE (heading increases) -- confirmed from ExoSkeletons
   AircraftController.spinBy/flyCircle: yaw = vel * clockwiseSign and the loop
   converges as attitude.yaw rises. Our interface yaw rate is ENU CCW+, so NEGATE.
   Isolate the convention to this ONE constant. (Bench-verify the physical turn
   direction once, props-off, before trusting any in-flight yaw.)               */
constexpr f32 kDjiYawRateSign           = -1.0f;


/* ---- The control setpoint on the wire -------------------------------------- */
/* FlightParam = {vx,vy,vz,yaw}: body-frame m/s (vx fwd, vy RIGHT, vz up) + yaw
   rate in DEG/S (DJI ANGULAR_VELOCITY, CW+). Nullable; we always send all four.  */
struct FlightParam { f32 vx{0.0f}, vy{0.0f}, vz{0.0f}, yaw{0.0f}; };


static inline f32 dji_clamp(f32 v, f32 lim) {
    if (v >  lim) return  lim;
    if (v < -lim) return -lim;
    return v;
}

/* The single frame edge: ENU-world velocity (m/s) + heading (ENU CCW+, rad) +
   yaw rate (ENU CCW+, rad/s) -> body FlightParam, clamped to the envelope.
   enu_to_flu gives forward-LEFT-up; DJI wants forward-RIGHT-up, so vy = -left. */
static inline FlightParam enu_vel_to_flightparam(Vec3 worldEnu, f32 yawEnu, f32 yawspeed) {
    Vec3 flu = enu_to_flu(worldEnu, yawEnu);
    FlightParam p;
    p.vx  = dji_clamp( flu.x, kDjiMaxSpeedMps);      /* forward           */
    p.vy  = dji_clamp(-flu.y, kDjiMaxSpeedMps);      /* right = -left     */
    p.vz  = dji_clamp( flu.z, kDjiMaxSpeedMps);      /* up                */
    p.yaw = dji_clamp(kDjiYawRateSign * yawspeed * kRadToDeg, kDjiMaxYawRateDegps);
    return p;
}

/* Teleop-direct: a body FLU velocity straight to a FlightParam (no dependence on
   a possibly-drifting yaw estimate). Same right = -left flip. */
static inline FlightParam flu_vel_to_flightparam(Vec3 flu, f32 yawspeed) {
    FlightParam p;
    p.vx  = dji_clamp( flu.x, kDjiMaxSpeedMps);
    p.vy  = dji_clamp(-flu.y, kDjiMaxSpeedMps);
    p.vz  = dji_clamp( flu.z, kDjiMaxSpeedMps);
    p.yaw = dji_clamp(kDjiYawRateSign * yawspeed * kRadToDeg, kDjiMaxYawRateDegps);
    return p;
}

/* Serialise a FlightParam to the wire JSON into a caller-owned buffer. snprintf,
   no heap -- this runs on the ~18 Hz stream hot path. Returns bytes written
   (excluding NUL), or <0 on encoding error (never happens for finite floats). */
static inline int flightparam_to_json(const FlightParam& p, char* buf, size_t n) {
    return std::snprintf(buf, n, "{\"vx\":%.4f,\"vy\":%.4f,\"vz\":%.4f,\"yaw\":%.4f}",
                         __scast(double, p.vx), __scast(double, p.vy),
                         __scast(double, p.vz), __scast(double, p.yaw));
}
