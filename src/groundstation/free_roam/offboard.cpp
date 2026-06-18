#include "offboard.hpp"
#include "base.hpp"


void OffboardControl::arm(bool armTrueDisarmFalse)
{
	RCLCPP_INFO(this->get_logger(), "Sending Arm Command: %d", armTrueDisarmFalse);
    
	DroneCmdParamList list{};
	// 1.0 = ARM. 0.0 = DISARM. // https://github.com/PX4/px4_msgs/blob/main/msg/VehicleCommand.msg
    list[0] = armTrueDisarmFalse ? 1.0f : 0.0f;
    publish_vehicle_cmd(DroneCmd::VEHICLE_CMD_COMPONENT_ARM_DISARM, list);
}

void OffboardControl::takeoff()
{
	RCLCPP_INFO(this->get_logger(), "Setting Offboard Mode...");

    DroneCmdParamList list{};
    // Set custom mode to PX4_CUSTOM_MAIN_MODE_OFFBOARD (6)
	// https://docs.px4.io/main/en/ros/ros2_offboard_control.html
    list[0] = 1.0f; // VEHICLE_MODE_FLAG_CUSTOM_MODE_ENABLED
    list[1] = 6.0f; // PX4_CUSTOM_MAIN_MODE_OFFBOARD
    publish_vehicle_cmd(DroneCmd::VEHICLE_CMD_DO_SET_MODE, list);
}

void OffboardControl::land()
{
	RCLCPP_INFO(this->get_logger(), "Sending Vehicle Command: LAND");

	// https://github.com/PX4/px4_msgs/blob/main/msg/VehicleCommand.msg
    DroneCmdParamList list{};
    publish_vehicle_cmd(DroneCmd::VEHICLE_CMD_NAV_LAND, list);
}


void OffboardControl::timer_callback(OffboardControl& toModify)
{
    // High frequency logs should use DEBUG to avoid flooding the terminal
    RCLCPP_DEBUG(this->get_logger(), "Publishing Offboard Mode & Trajectory Setpoint. (Vel: %.2f, %.2f, %.2f)", 
        m_currentVel.x, 
		m_currentVel.y, 
		m_currentVel.z
	);

	// https://docs.px4.io/main/en/flight_modes/offboard.html
	// Continuous streaming loop matching PX4 spec
	toModify.publish_offboardctrl_mode();
	toModify.publish_trajectory_setpoint(m_currentVel, m_currentYawSpeed);
	return;
}


void OffboardControl::external_arming_callback(Px4KeyboardArmType::ConstSharedPtr msg)
{
	const bool arm_intent = msg->data & 0x01;
	RCLCPP_INFO(this->get_logger(), "Arming Callback Triggered. Intent: %d", arm_intent);

	arm(arm_intent);
	if(arm_intent) {
		takeoff();
	}
	return;
}

void OffboardControl::external_velocity_callback(Px4KeyboardTwistType::ConstSharedPtr msg)
{
	RCLCPP_DEBUG(this->get_logger(), "Velocity Callback Triggered");
    // Convert ROS 2 ENU to PX4 NED
    m_currentVel.x = msg->linear.x;  // Forward stays North
    m_currentVel.y = -msg->linear.y; // Left (+Y ENU) becomes West (-Y NED)
    m_currentVel.z = -msg->linear.z; // Up (+Z ENU) becomes Up (-Z NED)
    
    // Convert Yaw rate (CCW positive in ROS to CW positive in PX4)
    m_currentYawSpeed = -msg->angular.z;
	return;
}




int main(int argc, char * argv[]) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<OffboardControl>());
    rclcpp::shutdown();
    return 0;
}