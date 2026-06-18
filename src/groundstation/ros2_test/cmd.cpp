#include "cmd.hpp"


int flight_takeoff_land_example(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<DroneController>();
    
    // Execute sequence
    node->arm();
    node->takeoff();
    std::this_thread::sleep_for(seconds(10));  // Hover
    node->land();
    
    rclcpp::shutdown();
    return 0;
}


