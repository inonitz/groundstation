#pragma once
/*
    Scripted test-scenario data, lifted OUT of the FmuNode class.

    Honest label: these are NOT unit tests. Each entry is a scripted VLM output (the SAME JSON the
    model would emit) plus, for the fault-injection scenarios, the synthetic condition the control
    loop should arm. They only mean anything with the whole node + a SITL sim running -- they are
    end-to-end scenario DATA the node replays via FmuNode::runTestScenario(). The genuinely in-process
    checkable pieces are commandIdFromAction (command_id.hpp) and parseTestScenario (below); those get
    the real unit test in test/fmu_translate_test.cpp.

    ROS-free on purpose: just an enum + strings, so main()'s arg parse and the unit test both use
    it without pulling the node in.
*/
#include <string>
#include <string_view>
#include <util2/C/base_type.h>


/* Which scripted scenario to replay. None (-1) = a normal VLM-driven run (no test). Values match
   the surviving "--scenario-*" flags; parseTestScenario maps argv[2] -> this. */
enum class TestScenario : i8 {
    None           = -1,
    Cross          = 0,   /* body-frame FLU axis sweep (out + undo, one axis at a time).   */
    Approach       = 1,   /* no-YOLO closed-loop approach (arms the synthetic detection rig). */
    ApproachReal   = 2,   /* real-perception approach to "car".                             */
    QueueOverflow  = 3,   /* oversized plan (100 actions) -> backpressure drops the overflow. */
    QueueOverflowAirborne = 4, /* cross flight, then an airborne oversized-plan burst ~5s in. */
    BatteryRth     = 5,   /* fly out, force 18% -> <=20% return-to-home failsafe.            */
    BatteryLandNow = 6,   /* fly out, force 8%  -> <=10% land-in-place failsafe.             */
    ObstacleStop   = 7,   /* takeoff, synthetic close obstacle -> the drone must stop (brake). */
    Storm          = 8,   /* boundary burst, VLM kept active -> escalated reassess prompt.   */
    ApproachImpact = 9,   /* approach reaches standoff off-nominal -> impact (not ok) verdict. */
    Hover          = 10,  /* fwd 1.5m, HOVER holds; the queued back-go must NEVER dequeue.       */
    Rotate         = 11,  /* takeoff, rotate 90 cw then 200 ccw, land (swept-angle verdict).      */
    Orbit          = 12,  /* takeoff, one radius_cm circle around a car, land (accuracy verdict).   */
    Follow         = 13,  /* takeoff, follow the (real-perception) person, hold standoff, keep lock. */
    Search         = 14   /* face away from people, advance-and-scan until one is DETECTED.          */
};

/* argv -> TestScenario. Selection is argv[2] == "--scenario-*"; anything else (including a bare
   objective) is None. Lives with the scenarios it selects, out of main(). */
inline TestScenario parseTestScenario(int argc, char** argv) {
    if (argc <= 2) return TestScenario::None;
    std::string_view f = argv[2];
    if (f == "--scenario-cross")           return TestScenario::Cross;
    if (f == "--scenario-approach")        return TestScenario::Approach;
    if (f == "--scenario-approach-real")   return TestScenario::ApproachReal;
    if (f == "--scenario-queue-overflow")           return TestScenario::QueueOverflow;
    if (f == "--scenario-queue-overflow-airborne")  return TestScenario::QueueOverflowAirborne;
    if (f == "--scenario-battery-rth")     return TestScenario::BatteryRth;
    if (f == "--scenario-battery-landnow") return TestScenario::BatteryLandNow;
    if (f == "--scenario-obstacle-stop")            return TestScenario::ObstacleStop;
    if (f == "--scenario-storm")           return TestScenario::Storm;
    if (f == "--scenario-approach-impact") return TestScenario::ApproachImpact;
    if (f == "--scenario-hover")           return TestScenario::Hover;
    if (f == "--scenario-rotate")          return TestScenario::Rotate;
    if (f == "--scenario-orbit")           return TestScenario::Orbit;
    if (f == "--scenario-follow")          return TestScenario::Follow;
    if (f == "--scenario-search")          return TestScenario::Search;
    return TestScenario::None;
}

/* ---- scenario JSON (the scripted VLM outputs; same schema translateToBaseCommands parses) ---- */

inline std::string scenarioCrossJson() {
    return R"([
        {"thought":"takeoff",             "action":"takeoff"},
        {"thought":"go forward",          "action":"go", "x":100,  "y":0,    "z":0, "speed":30},
        {"thought":"return to start",     "action":"go", "x":-100, "y":0,    "z":0, "speed":30},
        {"thought":"go left",             "action":"go", "x":0,    "y":100,  "z":0, "speed":30},
        {"thought":"return to start",     "action":"go", "x":0,    "y":-100, "z":0, "speed":30},
        {"thought":"go back",             "action":"go", "x":-100, "y":0,    "z":0, "speed":30},
        {"thought":"return to start",     "action":"go", "x":100,  "y":0,    "z":0, "speed":30},
        {"thought":"go right",            "action":"go", "x":0,    "y":-100, "z":0, "speed":30},
        {"thought":"return to start",     "action":"go", "x":0,    "y":100,  "z":0, "speed":30},
        {"thought":"land",                "action":"land"}
    ])";
}

inline std::string scenarioApproachJson() {
    return R"([
        {"thought":"takeoff",  "action":"takeoff"},
        {"thought":"approach", "action":"approach",
         "target_object":"canned_target", "speed":30},
        {"thought":"land",     "action":"land"}
    ])";
}

inline std::string scenarioApproachRealJson() {
    return R"([
        {"thought":"takeoff",  "action":"takeoff"},
        {"thought":"approach", "action":"approach",
         "target_object":"car", "speed":30},
        {"thought":"land",     "action":"land"}
    ])";
}

inline std::string scenarioOutboundJson() {
    return R"([
        {"thought":"takeoff",    "action":"takeoff"},
        {"thought":"fly out 8m", "action":"go", "x":800, "y":0, "z":0, "speed":40},
        {"thought":"land",       "action":"land"}
    ])";
}

/* Boundary and Storm both just take off; the synthetic obstacle is armed by the caller. */
inline std::string scenarioTakeoffOnlyJson() {
    return R"([
        {"thought":"takeoff", "action":"takeoff"}
    ])";
}

/* 100 no-op 'stop' actions in one plan -- the worst-case oversized (queue-overflow) plan. Built, not static. */
inline std::string scenarioQueueOverflowJson() {
    std::string plan = "[";
    for (u32 i = 0; i < 100; ++i) {
        if (i) plan += ",";
        plan += R"({"thought":"flood","action":"stop"})";
    }
    plan += "]";
    return plan;
}

/* HOVER persistence: fwd 1.5m, then HOVER (which never completes), then a back-go + land that must
   NEVER dequeue. If HOVER holds, the drone stays at +1.5m and never reverses -- the ABSENCE of the
   back-motion is the proof it held. If HOVER leaks, the back-go runs and drives it toward start. */
inline std::string scenarioHoverJson() {
    return R"([
        {"thought":"takeoff",                      "action":"takeoff"},
        {"thought":"go forward 1.5m",              "action":"go", "x":150,  "y":0, "z":0, "speed":30},
        {"thought":"hover -- hold here",           "action":"hover"},
        {"thought":"go back 1.5m must NOT run",   "action":"go", "x":-150, "y":0, "z":0, "speed":30},
        {"thought":"land must NOT run",           "action":"land"}
    ])";
}

/* ROTATE granularity: 90 deg cw then 200 deg ccw (a >180 sweep in one command), then land. The
   rotate/ filter reconstructs swept magnitude + direction from the log and checks against these. */
inline std::string scenarioRotateJson() {
    return R"([
        {"thought":"takeoff",        "action":"takeoff"},
        {"thought":"rotate 90 cw",   "action":"rotate", "angle_deg":90,  "direction":"cw"},
        {"thought":"rotate 200 ccw", "action":"rotate", "angle_deg":200, "direction":"ccw"},
        {"thought":"land",           "action":"land"}
    ])";
}

/* ORBIT: takeoff, fly one full fixed-radius circle, then land. The law flies a circle straight
   ahead of the start (depth-seeded radius was abandoned as too noisy), so it does not depend on
   any real object -- runs in a simple car world; the car sits at the orbit centre. */
inline std::string scenarioOrbitJson() {
    return R"([
        {"thought":"takeoff",           "action":"takeoff"},
        {"thought":"orbit the car, full turn", "action":"orbit", "target_object":"car",
         "radius_cm":400, "angle_deg":360, "speed":30, "direction":"ccw"},
        {"thought":"land",              "action":"land"}
    ])";
}

/* FOLLOW: takeoff, then follow the first detected person (real perception; VLM off in the test) at a
   2m standoff. FOLLOW is a yaw-only visual servo -- it centres the target and never self-completes,
   so the drone holds a lock on the moving person. follow/filter.sh checks the lock resolves, sustains,
   and the track id stays stable. */
inline std::string scenarioFollowJson() {
    return R"([
        {"thought":"takeoff",              "action":"takeoff"},
        {"thought":"follow the person",    "action":"follow", "target_index":0, "standoff_cm":200}
    ])";
}

/* SEARCH: takeoff facing AWAY from the people, then advance-and-scan for a person. On a confident
   detection the node logs SEARCH DETECTED and hands the track to APPROACH. search/filter.sh passes
   iff SEARCH activates and then DETECTS a person within the scan. */
inline std::string scenarioSearchJson() {
    return R"([
        {"thought":"takeoff",              "action":"takeoff"},
        {"thought":"search for the car",   "action":"search", "target_object":"car",
         "timeout_sec":90, "search_size":"medium", "start_heading_deg":0, "direction":"ccw"}
    ])";
}
