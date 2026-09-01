#pragma once
/*
    DjiBackend I/O contract (part 2 of 2) -- the /status/ telemetry parse, split
    out from dji_backend_base.hpp because it needs nlohmann/json. Kept OUT of
    dji_backend.hpp so the FMU translation unit never pulls the JSON headers (its
    strict -Werror warning set would reject them). Included only by
    dji_backend.cpp and test/dji_convert_test.cpp.

    Exception-free by construction: nlohmann's non-throwing parse plus type-checked
    field getters, so it is safe even if a caller compiles with -fno-exceptions.
*/
#include <nlohmann/json.hpp>            /* MUST precede util2/C/macro.h (below) */
#include "dji_backend/dji_backend_base.hpp"  /* pulls frame_convert -> util2 macro.h */
#include "generic_backend/generic_backend_types.hpp"  /* Odometry, kBatteryReadingUnknown */

/* util2/C/macro.h (pulled transitively above) defines a function-like
   `boolean(arg)` macro that collides with nlohmann::json::boolean member names.
   nlohmann is included FIRST so it parses clean; drop the macro here so it can
   never clobber a consumer that includes nlohmann after this header. */
#ifdef boolean
#  undef boolean
#endif


/* POD image of the fields we read from /status/. velocity3D is the trustworthy
   indoor signal; position3D is GPS lat/lon/alt on the real drone (invalid
   indoors) but {x,y,z} on the mock -- we read x/y/z when present and otherwise
   leave pos zero, since the backend dead-reckons position from velocity3D.
   FRAME of velocity3D is not yet confirmed with the author; treated as ENU here
   (fine for the mock, where yaw is fixed). */
struct StatusTelemetry {
    bool isFlying{false};
    i32  batteryPct{kBatteryReadingUnknown};
    Vec3 vel;          /* velocity3D {x,y,z}         */
    Vec3 pos;          /* position3D (mock: x,y,z)   */
    f32  yaw{0.0f};    /* attitude.yaw               */
    bool valid{false};
};

/* Guarded getters: never throw even under -fno-exceptions. A missing or
   wrong-typed field falls back to the default. */
static inline f32 dji_jf(const nlohmann::json& j, const char* k, f32 d) {
    auto it = j.find(k);
    return (it != j.end() && it->is_number()) ? it->get<f32>() : d;
}
static inline i32 dji_ji(const nlohmann::json& j, const char* k, i32 d) {
    auto it = j.find(k);
    return (it != j.end() && it->is_number()) ? it->get<i32>() : d;
}
static inline bool dji_jb(const nlohmann::json& j, const char* k, bool d) {
    auto it = j.find(k);
    return (it != j.end() && it->is_boolean()) ? it->get<bool>() : d;
}
static inline Vec3 dji_jvec(const nlohmann::json& a, const char* k) {
    auto it = a.find(k);
    if (it == a.end() || !it->is_object()) return {};
    return { dji_jf(*it, "x", 0.0f), dji_jf(*it, "y", 0.0f), dji_jf(*it, "z", 0.0f) };
}

/* Parse a /status/ response body. Returns false (out.valid stays false) on null /
   malformed JSON / missing "aircraft". Uses nlohmann's non-throwing parse. */
static inline bool parse_status_json(const char* body, StatusTelemetry& out) {
    if (!body) return false;
    nlohmann::json j = nlohmann::json::parse(body, nullptr, /*allow_exceptions=*/false);
    if (j.is_discarded() || !j.is_object()) return false;
    auto ac = j.find("aircraft");
    if (ac == j.end() || !ac->is_object()) return false;
    const nlohmann::json& a = *ac;

    out.isFlying   = dji_jb(a, "isFlying", false);
    out.batteryPct = dji_ji(a, "battery", kBatteryReadingUnknown);
    out.vel        = dji_jvec(a, "velocity3D");
    out.pos        = dji_jvec(a, "position3D");
    auto at = a.find("attitude");
    out.yaw        = (at != a.end() && at->is_object()) ? dji_jf(*at, "yaw", 0.0f) : 0.0f;
    out.valid      = true;
    return true;
}

/* POD telemetry -> the platform-neutral Odometry the FMU consumes. position3D is
   GPS indoors (invalid), so pos here is best-effort; the backend supplies a
   dead-reckoned position when it needs one. */
static inline Odometry status_to_odometry(const StatusTelemetry& t, u64 hostStampUs) {
    Odometry od;
    od.pos           = t.pos;
    od.vel           = t.vel;
    od.yaw           = t.yaw;
    od.host_stamp_us = hostStampUs;
    od.valid         = t.valid;
    return od;
}
