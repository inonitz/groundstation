#include "fmu_node.hpp"


int main(int argc, char* argv[]) {
    std::shared_ptr<FlightManagementUnitNode> node;
    std::string                               objective;
    bool                                      useCanned;
    bool                                      useCross;
    bool                                      useSpeed;
    bool                                      useApproach;
    bool                                      useApproachReal;
    bool                                      useRotate;
    bool                                      useLandFlare;
    bool                                      useTerrainLand;
    bool                                      useFlood;
    bool                                      useCrossFlood;
    bool                                      useBatteryRth;
    bool                                      useBatteryLandNow;
    bool                                      usePatrol;

    rclcpp::init(argc, argv);

    /* Phase 1 bring-up: objective from argv[1]. "--canned" (fwd 1m),
       "--canned-cross" (fwd/left/back/right 1m + return, FLU-frame sanity
       check), and "--canned-speed" (fwd+return at low then high speed) all
       skip the VLM. "--canned-approach-real" skips only the VLM planner --
       perception is real (real ONNX models, real detection). "--canned-rotate" and
       "--canned-land-flare" are spec-4 Part B log-verification plans (ROTATE granularity,
       LAND flare taper). */
    objective       = (argc > 1) ? argv[1] : "Hold position.";
    useCanned       = (argc > 2) && (std::string(argv[2]) == "--canned");
    useCross        = (argc > 2) && (std::string(argv[2]) == "--canned-cross");
    useSpeed        = (argc > 2) && (std::string(argv[2]) == "--canned-speed");
    useApproach     = (argc > 2) && (std::string(argv[2]) == "--canned-approach");
    useApproachReal = (argc > 2) && (std::string(argv[2]) == "--canned-approach-real");
    useRotate       = (argc > 2) && (std::string(argv[2]) == "--canned-rotate");
    useLandFlare    = (argc > 2) && (std::string(argv[2]) == "--canned-land-flare");
    useTerrainLand  = (argc > 2) && (std::string(argv[2]) == "--canned-terrain-land");
    useFlood        = (argc > 2) && (std::string(argv[2]) == "--canned-flood");
    useCrossFlood   = (argc > 2) && (std::string(argv[2]) == "--canned-cross-flood");
    useBatteryRth   = (argc > 2) && (std::string(argv[2]) == "--canned-battery-rth");
    useBatteryLandNow = (argc > 2) && (std::string(argv[2]) == "--canned-battery-landnow");
    usePatrol       = (argc > 2) && (std::string(argv[2]) == "--canned-patrol");

    node = std::make_shared<FlightManagementUnitNode>();
    node->start(objective, useCanned, useCross, useSpeed, useApproach, useApproachReal,
                useRotate, useLandFlare, useTerrainLand, useFlood, useCrossFlood,
                useBatteryRth, useBatteryLandNow, usePatrol);

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
