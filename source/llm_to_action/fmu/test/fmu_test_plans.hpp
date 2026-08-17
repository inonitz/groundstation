#pragma once
/*
    Canned test-plan scenarios, lifted OUT of the FmuNode class.

    Honest label: these are NOT unit tests. Each entry is a scripted VLM output (the SAME JSON the
    model would emit) plus, for the fault-injection scenarios, the synthetic condition the control
    loop should arm. They only mean anything with the whole node + a SITL sim running -- they are
    end-to-end scenario DATA the node replays via FmuNode::runTestPlan(). The genuinely in-process
    checkable pieces are commandIdFromAction (command_id.hpp) and parseTestPlan (below); those get
    the real unit test in test/fmu_translate_test.cpp.

    ROS-free on purpose: just an enum + strings, so main()'s arg parse and the unit test both use
    it without pulling the node in.
*/
#include <string>
#include <string_view>
#include <util2/C/base_type.h>


/* Which scripted scenario to replay. None (-1) = a normal VLM-driven run (no test). Values match
   the surviving "--canned-*" flags; parseTestPlan maps argv[2] -> this. */
enum class TestPlan : i8 {
    None           = -1,
    Cross          = 0,   /* body-frame FLU axis sweep (out + undo, one axis at a time).   */
    Approach       = 1,   /* no-YOLO closed-loop approach (arms the synthetic detection rig). */
    ApproachReal   = 2,   /* real-perception approach to "car".                             */
    Flood          = 3,   /* 100-action oversized plan -> backpressure drop test.           */
    CrossFlood     = 4,   /* cross flight, then an airborne flood ~5s after FLIGHT.          */
    BatteryRth     = 5,   /* fly out, force 18% -> <=20% return-to-home failsafe.            */
    BatteryLandNow = 6,   /* fly out, force 8%  -> <=10% land-in-place failsafe.             */
    Boundary       = 7,   /* takeoff, synthetic close obstacle -> emergency-boundary trip.   */
    Storm          = 8,   /* boundary burst, VLM kept active -> escalated reassess prompt.   */
    ApproachImpact = 9    /* approach reaches standoff off-nominal -> impact (not ok) verdict. */
};

/* argv -> TestPlan. Selection is argv[2] == "--canned-*"; anything else (including a bare
   objective) is None. Lives with the scenarios it selects, out of main(). */
inline TestPlan parseTestPlan(int argc, char** argv) {
    if (argc <= 2) return TestPlan::None;
    std::string_view f = argv[2];
    if (f == "--canned-cross")           return TestPlan::Cross;
    if (f == "--canned-approach")        return TestPlan::Approach;
    if (f == "--canned-approach-real")   return TestPlan::ApproachReal;
    if (f == "--canned-flood")           return TestPlan::Flood;
    if (f == "--canned-cross-flood")     return TestPlan::CrossFlood;
    if (f == "--canned-battery-rth")     return TestPlan::BatteryRth;
    if (f == "--canned-battery-landnow") return TestPlan::BatteryLandNow;
    if (f == "--canned-boundary")        return TestPlan::Boundary;
    if (f == "--canned-storm")           return TestPlan::Storm;
    if (f == "--canned-approach-impact") return TestPlan::ApproachImpact;
    return TestPlan::None;
}

/* ---- scenario JSON (the scripted VLM outputs; same schema translateToBaseCommands parses) ---- */

inline std::string testPlanCrossJson() {
    return R"([
        {"thought":"canned takeoff",             "action":"takeoff"},
        {"thought":"canned go forward",          "action":"go", "x":100,  "y":0,    "z":0, "speed":30},
        {"thought":"canned return to start",     "action":"go", "x":-100, "y":0,    "z":0, "speed":30},
        {"thought":"canned go left",             "action":"go", "x":0,    "y":100,  "z":0, "speed":30},
        {"thought":"canned return to start",     "action":"go", "x":0,    "y":-100, "z":0, "speed":30},
        {"thought":"canned go back",             "action":"go", "x":-100, "y":0,    "z":0, "speed":30},
        {"thought":"canned return to start",     "action":"go", "x":100,  "y":0,    "z":0, "speed":30},
        {"thought":"canned go right",            "action":"go", "x":0,    "y":-100, "z":0, "speed":30},
        {"thought":"canned return to start",     "action":"go", "x":0,    "y":100,  "z":0, "speed":30},
        {"thought":"canned land",                "action":"land"}
    ])";
}

inline std::string testPlanApproachJson() {
    return R"([
        {"thought":"canned takeoff",  "action":"takeoff"},
        {"thought":"canned approach", "action":"approach",
         "target_object":"canned_target", "speed":30},
        {"thought":"canned land",     "action":"land"}
    ])";
}

inline std::string testPlanApproachRealJson() {
    return R"([
        {"thought":"canned takeoff",  "action":"takeoff"},
        {"thought":"canned approach", "action":"approach",
         "target_object":"car", "speed":30},
        {"thought":"canned land",     "action":"land"}
    ])";
}

inline std::string testPlanOutboundJson() {
    return R"([
        {"thought":"canned takeoff",    "action":"takeoff"},
        {"thought":"canned fly out 8m", "action":"go", "x":800, "y":0, "z":0, "speed":40},
        {"thought":"canned land",       "action":"land"}
    ])";
}

/* Boundary and Storm both just take off; the synthetic obstacle is armed by the caller. */
inline std::string testPlanTakeoffOnlyJson() {
    return R"([
        {"thought":"canned takeoff", "action":"takeoff"}
    ])";
}

/* 100 no-op 'stop' actions in one plan -- the worst-case oversized-plan storm. Built, not static. */
inline std::string testPlanFloodJson() {
    std::string plan = "[";
    for (u32 i = 0; i < 100; ++i) {
        if (i) plan += ",";
        plan += R"({"thought":"flood","action":"stop"})";
    }
    plan += "]";
    return plan;
}
