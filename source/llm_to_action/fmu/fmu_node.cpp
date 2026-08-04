#include "fmu_node.hpp"


int main(int argc, char* argv[]) {
    std::shared_ptr<FlightManagementUnitNode> node;

    rclcpp::init(argc, argv);
    node = std::make_shared<FlightManagementUnitNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    
    return 0;
}