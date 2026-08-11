#pragma once
#include <util2/C/base_type.h>
#include <util2/C/macro.h>   /* __scast */
#include <string>
#include <fstream>
#include <cstdlib>   /* strtof / strtol -- non-throwing numeric parse (no exceptions rule). */
#include <cstdio>    /* fprintf stderr warnings, house debug-log idiom.                     */

/*
    Runtime per-drone / per-environment tuning (ROADMAP 9.14, spec
    2026-08-08-runtime-drone-config-constants.md).

    The FMU's physical tuning constants are drone- and environment-dependent: PX4
    Gazebo SITL and a real DJI Tello climb, drift, and brake differently, so one
    binary needs different numbers per airframe. This struct holds those tunables
    and is populated once at FMU construction from a profile file selected by the
    DRONE_CONFIG env var. Nothing is hot-reloaded -- load once, then read.

    CRITICAL invariant: every field DEFAULTS to the exact compiled `constexpr k*`
    value in fmu_node_base.hpp. With no profile loaded the FMU reads these defaults,
    so behavior is byte-for-byte identical to the pre-loader binary (SITL scale).
    The constexpr constants stay put as the documented default and the fallback; do
    NOT drift a default here from its constant without changing both together.

    No YAML library: the profile is a flat `key: value` text file, hand-parsed.
    No exceptions: a bad file sets `ok=false`; the caller decides (an explicitly
    selected-but-broken profile is FATAL + abort, never a silent fallback).
*/
struct DroneConfig {
    /* @takeoff*:
        climb target altitude and climb rate (ENU, Up+). */
    f32 takeoffTargetAltEnu  = 2.0f;     /* m  (kTakeoffTargetAltEnu)  */
    f32 takeoffClimbVelEnu   = 2.0f;     /* m/s (kTakeoffClimbVelEnu)  */

    /* @land*:
        descent rate, flare-start altitude, touchdown rate, ground-contact alt (ENU). */
    f32 landDescendVelEnu    = -0.5f;    /* m/s, Down=-Up (kLandDescendVelEnu)    */
    f32 flareStartAltEnu     = 1.0f;     /* m  (kFlareStartAltEnu)                */
    f32 flareTouchdownVelEnu = -0.12f;   /* m/s (kFlareTouchdownVelEnu)           */
    f32 groundContactEnu     = 0.1f;     /* m, landed when Up <= this (kGroundContactEnu) */

    /* @go*:
        fallback cruise speed and the GO position/cross-track gains. */
    f32 defaultGoSpeedCmS    = 30.0f;    /* cm/s (kDefaultGoSpeedCmS)   */
    f32 goApproachGainHz     = 0.5f;     /* 1/s (kGoApproachGainHz)     */
    f32 goCrossTrackGainHz   = 1.0f;     /* 1/s (kGoCrossTrackGainHz)   */

    /* @rotate*:
        yaw P-gain and the commanded yaw-rate clamp. */
    f32 rotateYawGainHz      = 1.5f;     /* rad/s per rad (kRotateYawGainHz) */
    f32 rotateMaxYawRate     = 0.8f;     /* rad/s clamp (kRotateMaxYawRate)  */

    /* @approach*:
        stop distance and the fallback approach speed. */
    f32 approachStandoffM    = 2.50f;    /* m  (kApproachStandoffM)      */
    f32 approachSpeedDefault = 80.0f;    /* cm/s (kApproachSpeedDefault) */

    /* @search*:
        sweep speed plus the lane geometry / per-leg timeout. Defaults equal the
        MEDIUM size preset (kSearchSizePresets[1]) -- the byte-identical old flat
        values -- so with no profile the size presets behave exactly as before. */
    f32 searchSweepSpeedMps  = 0.50f;    /* m/s (kSearchSweepSpeedMps)          */
    f32 searchLaneLengthM    = 6.0f;     /* m, medium preset laneLengthM        */
    f32 searchLaneSpacingM   = 2.0f;     /* m, medium preset laneSpacingM       */
    u32 searchLegTimeoutMs   = 20000;    /* ms, medium preset legTimeoutMs      */

    /* @orbit*:
        tangential speed around the locked circle. */
    f32 orbitDefaultSpeedMps = 0.30f;    /* m/s (kOrbitDefaultSpeedMps) */

    /* @boundary*:
        emergency-standoff base + velocity scale (trip = base + scale*closingSpeed). */
    f32 boundaryBaseM        = 0.6f;     /* m  (kBoundaryBaseM)      */
    f32 boundaryVelScale     = 0.5f;     /* m per m/s (kBoundaryVelScale) */

    /* @battery*:
        return-to-origin and land-in-place failsafe thresholds. */
    i32 batteryReturnPct     = 20;       /* % (kBatteryReturnPct) */
    i32 batteryLandPct       = 10;       /* % (kBatteryLandPct)   */

    /* @manual*:
        per-axis manual teleop speed under operator override. */
    f32 manualTeleopVelCmS   = 50.0f;    /* cm/s (kManualTeleopVelCmS) */
};


/* Trim ASCII whitespace from both ends of s (in place). */
inline void droneConfigTrim(std::string& s) {
    const char* ws = " \t\r\n";
    std::string::size_type a = s.find_first_not_of(ws);
    if (a == std::string::npos) {
        s.clear();
        return;
    }
    std::string::size_type b = s.find_last_not_of(ws);
    s = s.substr(a, b - a + 1);
    return;
}

/* Non-throwing float parse: whole trimmed token must convert, else false. */
inline bool droneConfigParseF32(std::string const& v, f32& out) {
    if (v.empty()) return false;
    char* end = nullptr;
    float f   = std::strtof(v.c_str(), &end);
    if (end != v.c_str() + v.size()) return false;   /* trailing junk -> reject. */
    out = __scast(f32, f);
    return true;
}

/* Non-throwing signed-int parse (base 10). */
inline bool droneConfigParseI32(std::string const& v, i32& out) {
    if (v.empty()) return false;
    char* end = nullptr;
    long n    = std::strtol(v.c_str(), &end, 10);
    if (end != v.c_str() + v.size()) return false;
    out = __scast(i32, n);
    return true;
}

/* Non-throwing unsigned-int parse (base 10, no negatives). */
inline bool droneConfigParseU32(std::string const& v, u32& out) {
    if (v.empty() || v[0] == '-') return false;
    char* end          = nullptr;
    unsigned long n    = std::strtoul(v.c_str(), &end, 10);
    if (end != v.c_str() + v.size()) return false;
    out = __scast(u32, n);
    return true;
}

/*
    Parse a flat `key: value` profile at `path` into a DroneConfig. Lines are
    whitespace-tolerant; `#` starts a comment; blank lines are skipped. An unknown
    key is a WARN-and-skip (forward-compat with newer profiles). `ok` is set false
    if the file cannot be opened, a line is malformed, or a known key carries an
    unparseable value -- the caller treats a false `ok` on a selected profile as
    fatal. Returns the struct with every unspecified field left at its default (==
    the compiled constexpr), so a partial profile only overrides what it names.
*/
[[nodiscard]] inline DroneConfig loadDroneConfig(std::string const& path, bool& ok) {
    DroneConfig   cfg;
    std::ifstream in(path);
    std::string   line;
    std::string   key;
    std::string   val;
    bool          matched = false;
    bool          good    = false;
    std::string::size_type hash = 0;
    std::string::size_type colon = 0;

    ok = true;
    if (!in.is_open()) {
        fprintf(stderr, "[DRONE_CONFIG] cannot open profile: %s\n", path.c_str());
        ok = false;
        return cfg;
    }

    while (std::getline(in, line)) {
        hash = line.find('#');
        if (hash != std::string::npos) line.erase(hash);   /* strip inline comment. */
        droneConfigTrim(line);
        if (line.empty()) continue;

        colon = line.find(':');
        if (colon == std::string::npos) {
            fprintf(stderr, "[DRONE_CONFIG] malformed line (no ':'): %s\n", line.c_str());
            ok = false;
            continue;
        }
        key = line.substr(0, colon);
        val = line.substr(colon + 1);
        droneConfigTrim(key);
        droneConfigTrim(val);

        matched = true;
        if      (key == "takeoffTargetAltEnu")  good = droneConfigParseF32(val, cfg.takeoffTargetAltEnu);
        else if (key == "takeoffClimbVelEnu")   good = droneConfigParseF32(val, cfg.takeoffClimbVelEnu);
        else if (key == "landDescendVelEnu")    good = droneConfigParseF32(val, cfg.landDescendVelEnu);
        else if (key == "flareStartAltEnu")     good = droneConfigParseF32(val, cfg.flareStartAltEnu);
        else if (key == "flareTouchdownVelEnu") good = droneConfigParseF32(val, cfg.flareTouchdownVelEnu);
        else if (key == "groundContactEnu")     good = droneConfigParseF32(val, cfg.groundContactEnu);
        else if (key == "defaultGoSpeedCmS")    good = droneConfigParseF32(val, cfg.defaultGoSpeedCmS);
        else if (key == "goApproachGainHz")     good = droneConfigParseF32(val, cfg.goApproachGainHz);
        else if (key == "goCrossTrackGainHz")   good = droneConfigParseF32(val, cfg.goCrossTrackGainHz);
        else if (key == "rotateYawGainHz")      good = droneConfigParseF32(val, cfg.rotateYawGainHz);
        else if (key == "rotateMaxYawRate")     good = droneConfigParseF32(val, cfg.rotateMaxYawRate);
        else if (key == "approachStandoffM")    good = droneConfigParseF32(val, cfg.approachStandoffM);
        else if (key == "approachSpeedDefault") good = droneConfigParseF32(val, cfg.approachSpeedDefault);
        else if (key == "searchSweepSpeedMps")  good = droneConfigParseF32(val, cfg.searchSweepSpeedMps);
        else if (key == "searchLaneLengthM")    good = droneConfigParseF32(val, cfg.searchLaneLengthM);
        else if (key == "searchLaneSpacingM")   good = droneConfigParseF32(val, cfg.searchLaneSpacingM);
        else if (key == "searchLegTimeoutMs")   good = droneConfigParseU32(val, cfg.searchLegTimeoutMs);
        else if (key == "orbitDefaultSpeedMps") good = droneConfigParseF32(val, cfg.orbitDefaultSpeedMps);
        else if (key == "boundaryBaseM")        good = droneConfigParseF32(val, cfg.boundaryBaseM);
        else if (key == "boundaryVelScale")     good = droneConfigParseF32(val, cfg.boundaryVelScale);
        else if (key == "batteryReturnPct")     good = droneConfigParseI32(val, cfg.batteryReturnPct);
        else if (key == "batteryLandPct")       good = droneConfigParseI32(val, cfg.batteryLandPct);
        else if (key == "manualTeleopVelCmS")   good = droneConfigParseF32(val, cfg.manualTeleopVelCmS);
        else {
            matched = false;
            fprintf(stderr, "[DRONE_CONFIG] unknown key (skipped): %s\n", key.c_str());
        }

        if (matched && !good) {
            fprintf(stderr, "[DRONE_CONFIG] bad value for %s: '%s'\n", key.c_str(), val.c_str());
            ok = false;
        }
    }
    return cfg;
}
