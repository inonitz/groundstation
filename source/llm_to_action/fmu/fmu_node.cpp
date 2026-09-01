#include "fmu_node.hpp"


int main(int argc, char* argv[]) {
    std::shared_ptr<FlightManagementUnitNode> node;
    std::string                               objective;

    rclcpp::init(argc, argv);

    /* Phase 1 bring-up: objective from argv[1]. A "--scenario-*" flag (argv[2]) selects a scripted
       test scenario and skips the VLM; parseTestScenario maps it to a TestScenario (test/fmu_test_scenarios.hpp).
       None = a normal VLM-driven run. */
    objective     = (argc > 1) ? argv[1] : "Hold position.";
    TestScenario test = parseTestScenario(argc, argv);

    node = std::make_shared<FlightManagementUnitNode>();

    /* Voice-first launch: an explicitly EMPTY objective (argv[1]=="") with no scenario
       means "wait for a spoken objective" -- the drone idles in STANDBY until the ASR
       callback delivers the first transcript and calls start(). Any typed objective (the
       argc<=1 default is "Hold position.") or any --scenario flag auto-starts as before, so
       every existing test script is unaffected. */
    bool anyTest = (test != TestScenario::None);
    if (!objective.empty() || anyTest) {
        node->start(objective, test);
    } else {
        RCLCPP_WARN(node->get_logger(),
            "[FMU_NODE_DEBUG] No objective given -- idling in STANDBY, waiting for a spoken "
            "objective on /asr_server/transcribe.");
    }

    /* MUST be built AFTER rclcpp::init — its ctor creates guard conditions   */
    /* from the global context, which is null until init() runs. Cannot be    */
    /* hoisted above init for that reason.                                     */
    {
        rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions{}, 3);
        executor.add_node(node);
        executor.spin();
    }

    rclcpp::shutdown();
    return 0;
}


/* ======================= SITL / canned-test wiring ==========================
   Out-of-line implementations of the FMU's test-plan entry points, kept OUT of the class header so
   fmu_node.hpp stays declarations. These drive the Gazebo/SITL behaviour + safety-law tests via the
   scripted scenarios in test/fmu_test_scenarios.hpp; a normal flight passes TestScenario::None. */
void FlightManagementUnitNode::runTestScenario(TestScenario test) {
    switch (test) {
    case TestScenario::None:
        return;
    case TestScenario::Cross:
        translateToBaseCommands(scenarioCrossJson());
        break;
    case TestScenario::Approach:
        m_useCannedApproachRig = true;
        translateToBaseCommands(scenarioApproachJson());
        break;
    case TestScenario::ApproachReal:
        translateToBaseCommands(scenarioApproachRealJson());
        break;
    case TestScenario::QueueOverflow:
        RCLCPP_WARN(this->get_logger(),
            "[FMU_NODE_DEBUG] QUEUE-OVERFLOW test: 100 actions vs queue cap %u.", 3u * kControlLoopRateHz);
        translateToBaseCommands(scenarioQueueOverflowJson());
        break;
    case TestScenario::QueueOverflowAirborne:
        m_floodArmed = true;   /* controlLoop fires the airborne flood ~5s after FLIGHT. */
        translateToBaseCommands(scenarioCrossJson());
        break;
    case TestScenario::BatteryRth:
        m_batForceArmed = true; m_batForceValue = 18;   /* <=20% -> return-to-home. */
        translateToBaseCommands(scenarioOutboundJson());
        break;
    case TestScenario::BatteryLandNow:
        m_batForceArmed = true; m_batForceValue = 8;    /* <=10% -> land-in-place. */
        translateToBaseCommands(scenarioOutboundJson());
        break;
    case TestScenario::ObstacleStop:
        m_obstacleArmed = true;   /* controlLoop opens the synthetic-obstacle burst once airborne. */
        translateToBaseCommands(scenarioTakeoffOnlyJson());
        break;
    case TestScenario::Storm:
        m_obstacleArmed = true;
        m_missionActive.store(true, std::memory_order_release);   /* wake the VLM after the burst. */
        translateToBaseCommands(scenarioTakeoffOnlyJson());
        break;
    case TestScenario::ApproachImpact:
        m_forceApproachImpact  = true;   /* motion-gate forced off-nominal -> impact verdict. */
        m_useCannedApproachRig = true;
        translateToBaseCommands(scenarioApproachJson());
        break;
    case TestScenario::Hover:
        translateToBaseCommands(scenarioHoverJson());
        break;
    case TestScenario::Rotate:
        translateToBaseCommands(scenarioRotateJson());
        break;
    case TestScenario::Orbit:
        translateToBaseCommands(scenarioOrbitJson());
        break;
    case TestScenario::Follow:
        translateToBaseCommands(scenarioFollowJson());
        break;
    case TestScenario::Search:
        translateToBaseCommands(scenarioSearchJson());
        break;
    }
}


/* ======================= Per-tick control laws ==============================
   Out-of-line implementations of controlLoop()'s per-command laws (see the stepHover/... group in
   fmu_node.hpp). One runs each 20 Hz tick, selected by the active CommandID. Extracted from
   controlLoop one command at a time; each is behaviour-identical and Gazebo-verified before the next. */
void FlightManagementUnitNode::stepHover() {
    /* Persistent hold: zero velocity, station kept by the backend position controller
       (PX4 EKF / Tello VPS). Never completes -> stays the active task -> the VLM is NOT
       re-woken. Exits only on an interrupt, a re-assess, or a new command. */
    m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
        "[FMU_NODE_DIAGNOSTICS] HOVER holding station.");
}
