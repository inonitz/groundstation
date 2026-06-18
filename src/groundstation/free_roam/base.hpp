#pragma once
#include <array>
#include <bits/chrono.h>
#include <util2/C/macro.h>
#include <util2/C/base_type.h>
#include <rclcpp/rclcpp.hpp>
#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_control_mode.hpp>
#include <px4_msgs/srv/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
#include <px4_msgs/msg/vehicle_odometry.hpp>
// #include <px4_msgs/msg/timesync_status.hpp>

#include <geometry_msgs/msg/twist.hpp>
#include <std_msgs/msg/bool.hpp>


struct alignpk(16) Vec3 {
    f32 x;
    f32 y;
    f32 z;
};


constexpr const u8    kDefaultDroneDeviceID         = 1;
constexpr const u8    kDefaultGroundStationDeviceID = 255;
constexpr const u32   kOffboardUpdatesPerSec   = 100;
constexpr const auto  kOffboardUpdatePeriod    = std::chrono::milliseconds(1000 / kOffboardUpdatesPerSec);
constexpr const u32   kDefaultHistoryBufSize   = 10u;
constexpr const char* kInVehicleCmdTopic       = "/fmu/in/vehicle_command";
constexpr const char* kInTrajectoryPointTopic  = "/fmu/in/trajectory_setpoint";
constexpr const char* kInOffboardCtrlModeTopic = "/fmu/in/offboard_control_mode";
constexpr const char* kOutTimeSyncStatusTopic  = "/fmu/out/timesync_status";
constexpr const char* kOutVehiclePositionTopic = "/fmu/out/vehicle_local_position"; 
constexpr const char* kOutVehicleOdometryTopic = "/fmu/out/vehicle_odometry";
constexpr const char* kOutVehicleStatusTopic   = "/fmu/out/vehicle_status_v1";
constexpr const char* kOutVehicleAttitudeTopic = "/fmu/out/vehicle_attitude";


constexpr const char* kPx4KeyboardCmdVelTopic = "/px4_keyboard/arm_msg";
constexpr const char* kPx4KeyboardTwistTopic  = "/px4_keyboard/cmd_vel";
using Px4KeyboardTwistType = geometry_msgs::msg::Twist;
using Px4KeyboardArmType   = std_msgs::msg::Bool;


template<typename T> using PublisherPtr  = typename rclcpp::Publisher<T>::SharedPtr;
template<typename T> using SubscriberPtr = typename rclcpp::Subscription<T>::SharedPtr;

// template<typename T> using ServiceClientPtr = typename rclcpp::Service<T>::SharedPtr;

/* 
    The path has to be divided to "little steps" 
    for continuous control of the drone in offboard-ctrl mode 
*/
using DronePathDiscretePoint = px4_msgs::msg::TrajectorySetpoint;
using DronePathPoint         = DronePathDiscretePoint;
using DroneStatus            = px4_msgs::msg::OffboardControlMode;
using DroneCmd               = px4_msgs::msg::VehicleCommand;
using DroneCmdIdType         = u32;
using DroneCmdParamList      = std::array<f32, 7>;
using DroneLocalPosition     = px4_msgs::msg::VehicleLocalPosition;
using DroneOdometry          = px4_msgs::msg::VehicleOdometry;
// using DroneTimeSyncPoint     = px4_msgs::msg::TimesyncStatus;

