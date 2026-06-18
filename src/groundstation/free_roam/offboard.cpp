#include "offboard.hpp"


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

void OffboardControl::force_disarm()
{
    RCLCPP_INFO(this->get_logger(), "Executing FORCE DISARM.");
    DroneCmdParamList list{};
    list[0] = 0.0f;     // 0.0 = DISARM
    list[1] = 21196.0f; // Magic number to bypass PX4 landing checks // https://mavlink.io/en/messages/common.html#MAV_CMD_COMPONENT_ARM_DISARM
    publish_vehicle_cmd(DroneCmd::VEHICLE_CMD_COMPONENT_ARM_DISARM, list);
}


void OffboardControl::timer_callback(OffboardControl& toModify)
{
    toModify.publish_offboardctrl_mode();

    Vec3 target_vel{0.0f, 0.0f, 0.0f};
    f32 target_yaw = 0.0f;

    switch (m_state) {
        case DroneState::STANDBY:
            // Send zero vectors to keep Offboard watchdog happy while on ground
        break;

        case DroneState::TAKEOFF:
            RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 1000, 
                "Taking off... Current Altitude (NED): %.2f", m_current_z_ned);

            if (m_current_z_ned > -2.0f) { 
                target_vel.z = -2.0f; 
            } else {
                RCLCPP_INFO(this->get_logger(), "Altitude reached. Transition -> FLIGHT");
                m_state = DroneState::FLIGHT;
            }
        break;


        case DroneState::FLIGHT:
            // Route keyboard inputs only during active flight
            target_vel = m_currentVel; 
            target_yaw = m_currentYawSpeed;
        break;

        case DroneState::LANDING:
            target_vel.z = 0.5f; // Descend slowly (NED Down is positive)

            if (m_current_z_ned >= -0.1f) { 
                RCLCPP_INFO(this->get_logger(), "Ground Detected. Transition -> STANDBY");
                force_disarm(); 
                m_state = DroneState::STANDBY; 
            }
        break;
    }

    toModify.publish_trajectory_setpoint(target_vel, target_yaw);
}


void OffboardControl::external_arming_callback(Px4KeyboardArmType::ConstSharedPtr msg)
{
    bool arm_intent = (msg->data & 0x01);

    if (arm_intent && m_state == DroneState::STANDBY) {
        RCLCPP_INFO(this->get_logger(), "Transition -> TAKEOFF");
        arm(true);
        takeoff(); // Sets offboard mode // https://docs.px4.io/main/en/ros/ros2_offboard_control.html
        m_state = DroneState::TAKEOFF;
    } 
    else if (!arm_intent && m_state == DroneState::FLIGHT) {
		if(m_current_z_ned >= -1.5f) { /* If UpIsPositive_DroneHeight <= 1.5m we can safely land */
			RCLCPP_INFO(this->get_logger(), "Transition -> LANDING");
			m_state = DroneState::LANDING;
		} else {
			RCLCPP_INFO(this->get_logger(), 
				"Transition -> LANDING NOT SUCCEEDED - Current Height is %2.2f",
				-1.0f * m_current_z_ned
			);
		};
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