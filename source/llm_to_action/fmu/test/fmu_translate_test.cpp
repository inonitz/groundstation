/*
    ROS-free unit test for the two PURE decision points the scenario rewrite extracted out of
    the FmuNode class:
      - commandIdFromAction(action string) -> CommandID   (command_id.hpp)
      - parseTestScenario(argc, argv)          -> TestScenario     (test/fmu_test_scenarios.hpp)

    These are the parts that were previously untestable because they were buried in a ROS node.
    No rclcpp, no sim, no hardware -- runs anywhere (see fmu/CMakeLists.txt, GROUNDSTATION_BUILD_TESTS).
*/
#include <cstdio>
#include <string>
#include <cmath>
#include "../command_id.hpp"
#include "../fmu_helpers.hpp"
#include "fmu_test_scenarios.hpp"

static int g_fail = 0;
#define CHECK(cond)                                                             \
    do {                                                                        \
        if (!(cond)) { std::printf("FAIL line %d: %s\n", __LINE__, #cond); ++g_fail; } \
    } while (0)

static TestScenario parseFlag(const char* flag) {
    char a0[] = "fmu", a1[] = "objective";
    char* argv[3] = { a0, a1, const_cast<char*>(flag) };
    return parseTestScenario(3, argv);
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

    /* labelMatchesTarget: exact match, human synonyms collapse to "person", non-human stays exact. */
    CHECK(labelMatchesTarget("person", "person"));
    CHECK(labelMatchesTarget("car", "car"));
    CHECK(labelMatchesTarget("person", "human in red"));
    CHECK(labelMatchesTarget("person", "the red guy"));
    CHECK(labelMatchesTarget("person", "WOMAN"));
    CHECK(!labelMatchesTarget("car", "human in red"));   /* human target, non-person detection */
    CHECK(!labelMatchesTarget("person", "red car"));      /* non-human target, non-exact */
    CHECK(!labelMatchesTarget(nullptr, "person"));

    /* lateralComponent: strips the along-forward part. */
    Vec3 la = lateralComponent(Vec3{2.0f,0.0f,0.0f}, Vec3{1.0f,0.0f,0.0f});
    CHECK(std::fabs(la.x) < 1e-5f && std::fabs(la.y) < 1e-5f && std::fabs(la.z) < 1e-5f);
    Vec3 lb = lateralComponent(Vec3{1.0f,1.0f,0.0f}, Vec3{1.0f,0.0f,0.0f});
    CHECK(std::fabs(lb.x) < 1e-5f && std::fabs(lb.y - 1.0f) < 1e-5f);

    /* parseTestScenario: each surviving flag -> its enum; unknown / removed / none -> None. */
    CHECK(parseFlag("--scenario-cross")           == TestScenario::Cross);
    CHECK(parseFlag("--scenario-approach")        == TestScenario::Approach);
    CHECK(parseFlag("--scenario-approach-real")   == TestScenario::ApproachReal);
    CHECK(parseFlag("--scenario-queue-overflow")           == TestScenario::QueueOverflow);
    CHECK(parseFlag("--scenario-queue-overflow-airborne")  == TestScenario::QueueOverflowAirborne);
    CHECK(parseFlag("--scenario-battery-rth")     == TestScenario::BatteryRth);
    CHECK(parseFlag("--scenario-battery-landnow") == TestScenario::BatteryLandNow);
    CHECK(parseFlag("--scenario-obstacle-stop")            == TestScenario::ObstacleStop);
    CHECK(parseFlag("--scenario-storm")           == TestScenario::Storm);
    CHECK(parseFlag("--scenario-approach-impact") == TestScenario::ApproachImpact);
    CHECK(parseFlag("--scenario-hover")           == TestScenario::Hover);
    CHECK(parseFlag("--scenario-rotate")          == TestScenario::Rotate);
    CHECK(parseFlag("--scenario-orbit")           == TestScenario::Orbit);
    CHECK(parseFlag("--scenario-speed")           == TestScenario::None);   /* removed flag */
    CHECK(parseFlag("--nonsense")               == TestScenario::None);
    CHECK(parseFlag("a normal objective")       == TestScenario::None);

    char a0[] = "fmu";
    char* argv1[1] = { a0 };
    CHECK(parseTestScenario(1, argv1) == TestScenario::None);                /* no flag at all */

    if (g_fail == 0) { std::printf("fmu_translate_test: ALL PASS\n"); return 0; }
    std::printf("fmu_translate_test: %d FAILURE(S)\n", g_fail);
    return 1;
}
