#include "fmu_node.hpp"


int main(int argc, char* argv[]) {
    std::shared_ptr<FlightManagementUnitNode> node;
    std::string                               objective;

    rclcpp::init(argc, argv);

    /* Phase 1 bring-up: objective from argv[1]. A "--canned-*" flag (argv[2]) selects a scripted
       test scenario and skips the VLM; parseTestPlan maps it to a TestPlan (test/fmu_test_plans.hpp).
       None = a normal VLM-driven run. */
    objective     = (argc > 1) ? argv[1] : "Hold position.";
    TestPlan test = parseTestPlan(argc, argv);

    node = std::make_shared<FlightManagementUnitNode>();

    /* Voice-first launch: an explicitly EMPTY objective (argv[1]=="") with no canned plan
       means "wait for a spoken objective" -- the drone idles in STANDBY until the ASR
       callback delivers the first transcript and calls start(). Any typed objective (the
       argc<=1 default is "Hold position.") or any --canned flag auto-starts as before, so
       every existing test script is unaffected. */
    bool anyTest = (test != TestPlan::None);
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
