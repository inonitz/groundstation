#pragma once
/**
 * @brief Offboard control example
 * @file offboard_control.cpp
 * @addtogroup examples
 * @author Mickey Cowden <info@cowden.tech>
 * @author Nuno Marques <nuno.marques@dronesolutions.io>
 */
#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_control_mode.hpp>
#include <rclcpp/rclcpp.hpp>
#include <stdint.h>

#include <chrono>
#include <iostream>

using namespace std::chrono;


class OffboardControl : public rclcpp::Node
{
public:
	OffboardControl() : Node("offboard_control")
	{
		m_offboard_control_mode = this->create_publisher<px4_msgs::msg::OffboardControlMode>("/fmu/in/offboard_control_mode", 10);
		m_trajectory_setpoint   = this->create_publisher<px4_msgs::msg::TrajectorySetpoint>("/fmu/in/trajectory_setpoint", 10);
		m_vehicle_command       = this->create_publisher<px4_msgs::msg::VehicleCommand>("/fmu/in/vehicle_command", 10);
		m_offboard_setpoints    = 0;

		auto timer_callback = [this]() -> void {

			if (m_offboard_setpoints == 10) {
				// Change to Offboard mode after 10 setpoints
				this->publish_vehicle_command(px4_msgs::msg::VehicleCommand::VEHICLE_CMD_DO_SET_MODE, 1, 6);

				// Arm the vehicle
				this->arm();
			}

			// offboard_control_mode needs to be paired with trajectory_setpoint
			publish_offboard_control_mode();
			publish_trajectory_setpoint();

			// stop the counter after reaching 11
			if (m_offboard_setpoints < 11) {
				m_offboard_setpoints++;
			}
		};
		m_timer = this->create_wall_timer(100ms, timer_callback);
	}

	void arm();
	void disarm();

private:
    template<typename T> using PublisherPtr = typename rclcpp::Publisher<T>::SharedPtr;

	rclcpp::TimerBase::SharedPtr                     m_timer;
	PublisherPtr<px4_msgs::msg::OffboardControlMode> m_offboard_control_mode;
	PublisherPtr<px4_msgs::msg::TrajectorySetpoint>  m_trajectory_setpoint;
	PublisherPtr<px4_msgs::msg::VehicleCommand>      m_vehicle_command;
	std::atomic<uint64_t>                            m_timestamp;
	uint64_t                                         m_offboard_setpoints;

	void publish_offboard_control_mode();
	void publish_trajectory_setpoint();
	void publish_vehicle_command(uint16_t command, float param1 = 0.0, float param2 = 0.0);
};

int simple_offboard_flight_example(int argc, char *argv[]);