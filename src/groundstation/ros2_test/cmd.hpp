#pragma once
#include <chrono>
#include <thread>
#include <rclcpp/rclcpp.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_attitude_setpoint.hpp>
#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/srv/vehicle_command.hpp>


using namespace std::chrono;


class DroneController : public rclcpp::Node
{
public:
    DroneController() : Node("drone_controller")
    {
        // Create publishers for PX4 commands
        m_cmdPublisher = this->create_publisher<px4_msgs::msg::VehicleCommand>(
            "/fmu/in/vehicle_command", 10);
        

        RCLCPP_INFO(this->get_logger(), "Drone controller node started");
        // Initialize command messages
        m_arm = px4_msgs::msg::VehicleCommand();
        m_arm.command = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM;
        m_arm.param1 = 1.0;  // 1.0 to Arm
        m_arm.target_system = 1;
        m_arm.target_component = 1;
        m_arm.source_system = 1;
        m_arm.source_component = 1;
        m_arm.from_external = true;

        // m_takeoff = px4_msgs::msg::VehicleCommand();
        // m_takeoff.command = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_NAV_TAKEOFF;
        // m_takeoff.param1 = 1.0; 
        // m_takeoff.target_system = 1;
        // m_takeoff.target_component = 1;
        // m_takeoff.source_system = 1;
        // m_takeoff.source_component = 1;
        // m_takeoff.from_external = true;
        m_takeoff.command = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_NAV_TAKEOFF;
        m_takeoff.param1 = 1.0; 
        m_takeoff.param5 = std::nan(""); // Latitude: Use current
        m_takeoff.param6 = std::nan(""); // Longitude: Use current
        m_takeoff.param7 = 10.0;         // Altitude: 10 meters
        m_takeoff.target_system = 1;
        m_takeoff.target_component = 1;
        m_takeoff.source_system = 1;
        m_takeoff.source_component = 1;
        m_takeoff.from_external = true;

        m_land = px4_msgs::msg::VehicleCommand();
        m_land.command = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_NAV_LAND;
        m_land.param1 = 1.0;
        m_land.target_system = 1;
        m_land.target_component = 1;
        m_land.source_system = 1;
        m_land.source_component = 1;
        m_land.from_external = true;
    }
    
    void arm()
    {
        RCLCPP_INFO(this->get_logger(), "Sending ARM command...");
        m_arm.command = px4_msgs::msg::VehicleCommand::ARMING_ACTION_ARM;
        m_arm.timestamp = this->get_clock()->now().nanoseconds() / 1000;
        m_cmdPublisher->publish(m_arm);
        std::this_thread::sleep_for(milliseconds(1000));
    }
    
    void takeoff()
    {
        RCLCPP_INFO(this->get_logger(), "Sending TAKEOFF command...");
        m_takeoff.command = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_NAV_TAKEOFF;
        m_takeoff.timestamp = this->get_clock()->now().nanoseconds() / 1000;
        m_cmdPublisher->publish(m_takeoff);
        std::this_thread::sleep_for(milliseconds(1000));
    }
    
    void land()
    {
        RCLCPP_INFO(this->get_logger(), "Sending LAND command...");
        m_land.command = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_NAV_LAND;
        m_land.timestamp = this->get_clock()->now().nanoseconds() / 1000;
        m_cmdPublisher->publish(m_land);
        std::this_thread::sleep_for(milliseconds(1000));
    }
    
private:
    rclcpp::Publisher<px4_msgs::msg::VehicleCommand>::SharedPtr m_cmdPublisher;
    px4_msgs::msg::VehicleCommand m_arm;
    px4_msgs::msg::VehicleCommand m_land;
    px4_msgs::msg::VehicleCommand m_takeoff;
};
