#include "fmu_node.hpp"


int main(int argc, char* argv[]) {
    std::shared_ptr<FlightManagementUnitNode> node;
    std::string                               objective;
    bool                                      useCanned;
    bool                                      useCross;
    bool                                      useSpeed;

    rclcpp::init(argc, argv);

    /* Phase 1 bring-up: objective from argv[1]. "--canned" (fwd 1m),
       "--canned-cross" (fwd/left/back/right 1m + return, FLU-frame sanity
       check), and "--canned-speed" (fwd+return at low then high speed) all
       skip the VLM. */
    objective = (argc > 1) ? argv[1] : "Hold position.";
    useCanned = (argc > 2) && (std::string(argv[2]) == "--canned");
    useCross  = (argc > 2) && (std::string(argv[2]) == "--canned-cross");
    useSpeed  = (argc > 2) && (std::string(argv[2]) == "--canned-speed");

    node = std::make_shared<FlightManagementUnitNode>();
    node->start(objective, useCanned, useCross, useSpeed);

    /* MUST be built AFTER rclcpp::init — its ctor creates guard conditions   */
    /* from the global context, which is null until init() runs. Cannot be    */
    /* hoisted above init for that reason.                                     */
    {
        rclcpp::executors::MultiThreadedExecutor executor;
        executor.add_node(node);
        executor.spin();
    }

    rclcpp::shutdown();
    return 0;
}
