/*
    ROS-free unit test for the two PURE decision points the canned-plan rewrite extracted out of
    the FmuNode class:
      - commandIdFromAction(action string) -> CommandID   (command_id.hpp)
      - parseTestPlan(argc, argv)          -> TestPlan     (test/fmu_test_plans.hpp)

    These are the parts that were previously untestable because they were buried in a ROS node.
    No rclcpp, no sim, no hardware -- runs anywhere (see fmu/CMakeLists.txt, GROUNDSTATION_BUILD_TESTS).
*/
#include <cstdio>
#include <string>
#include "../command_id.hpp"
#include "fmu_test_plans.hpp"

static int g_fail = 0;
#define CHECK(cond)                                                             \
    do {                                                                        \
        if (!(cond)) { std::printf("FAIL line %d: %s\n", __LINE__, #cond); ++g_fail; } \
    } while (0)

static TestPlan parseFlag(const char* flag) {
    char a0[] = "fmu", a1[] = "objective";
    char* argv[3] = { a0, a1, const_cast<char*>(flag) };
    return parseTestPlan(3, argv);
}

int main() {
    /* commandIdFromAction: every handled action -> its id; anything else -> MAX_ID. */
    CHECK(commandIdFromAction("takeoff")  == CommandID::TAKEOFF);
    CHECK(commandIdFromAction("land")     == CommandID::LAND);
    CHECK(commandIdFromAction("stop")     == CommandID::STOP);
    CHECK(commandIdFromAction("hover")    == CommandID::HOVER);
    CHECK(commandIdFromAction("go")       == CommandID::GO);
    CHECK(commandIdFromAction("rotate")   == CommandID::ROTATE);
    CHECK(commandIdFromAction("approach") == CommandID::APPROACH);
    CHECK(commandIdFromAction("follow")   == CommandID::FOLLOW);
    CHECK(commandIdFromAction("orbit")    == CommandID::ORBIT);
    CHECK(commandIdFromAction("search")   == CommandID::SEARCH);
    CHECK(commandIdFromAction("")         == CommandID::MAX_ID);   /* empty */
    CHECK(commandIdFromAction("curve")    == CommandID::MAX_ID);   /* internal, never an action */
    CHECK(commandIdFromAction("reassess") == CommandID::MAX_ID);   /* internal, never an action */
    CHECK(commandIdFromAction("TAKEOFF")  == CommandID::MAX_ID);   /* case-sensitive on purpose */
    CHECK(commandIdFromAction("go ")      == CommandID::MAX_ID);   /* no trimming */

    /* cmdName is the inverse of commandIdFromAction for the handled verbs (round-trip). */
    CHECK(std::string(cmdName(CommandID::TAKEOFF)) == "takeoff");
    CHECK(std::string(cmdName(CommandID::MAX_ID))  == "?");
    for (const char* v : {"takeoff","land","stop","hover","go","rotate","approach","follow","orbit","search"})
        CHECK(std::string(cmdName(commandIdFromAction(v))) == v);

    /* parseTestPlan: each surviving flag -> its enum; unknown / removed / none -> None. */
    CHECK(parseFlag("--canned-cross")           == TestPlan::Cross);
    CHECK(parseFlag("--canned-approach")        == TestPlan::Approach);
    CHECK(parseFlag("--canned-approach-real")   == TestPlan::ApproachReal);
    CHECK(parseFlag("--canned-flood")           == TestPlan::Flood);
    CHECK(parseFlag("--canned-cross-flood")     == TestPlan::CrossFlood);
    CHECK(parseFlag("--canned-battery-rth")     == TestPlan::BatteryRth);
    CHECK(parseFlag("--canned-battery-landnow") == TestPlan::BatteryLandNow);
    CHECK(parseFlag("--canned-boundary")        == TestPlan::Boundary);
    CHECK(parseFlag("--canned-storm")           == TestPlan::Storm);
    CHECK(parseFlag("--canned-approach-impact") == TestPlan::ApproachImpact);
    CHECK(parseFlag("--canned-speed")           == TestPlan::None);   /* removed flag */
    CHECK(parseFlag("--nonsense")               == TestPlan::None);
    CHECK(parseFlag("a normal objective")       == TestPlan::None);

    char a0[] = "fmu";
    char* argv1[1] = { a0 };
    CHECK(parseTestPlan(1, argv1) == TestPlan::None);                /* no flag at all */

    if (g_fail == 0) { std::printf("fmu_translate_test: ALL PASS\n"); return 0; }
    std::printf("fmu_translate_test: %d FAILURE(S)\n", g_fail);
    return 1;
}
