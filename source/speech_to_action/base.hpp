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
#include <std_msgs/msg/string.hpp>
#include <std_msgs/msg/int32_multi_array.hpp>

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

constexpr const char* kOutKeyboardArmStateTopic = "/px4_keyboard/arm_msg";
constexpr const char* kOutKeyboardTwistTopic    = "/px4_keyboard/cmd_vel";
constexpr const char* kOutKeyboardRawTopic      = "/px4_keyboard/in/raw";
constexpr const char* kOutASRServerTranscriptionTopic = "/asr_server/transcribe";
constexpr const char* kOutASRServerTwistTopic         = "/asr_server/cmd_vel";
constexpr const char* kOutASRServerArmStateTopic      = "/asr_server/arm_msg";


using KeyboardTwistType    = geometry_msgs::msg::Twist;
using KeyboardArmType      = std_msgs::msg::Bool;
using KeyboardRawInputType = std_msgs::msg::Int32MultiArray;
using ASRTextType          = std_msgs::msg::String;
using ASRTextTwistType     = geometry_msgs::msg::Twist;
using ASRArmType           = std_msgs::msg::Bool;


template<typename T> using PublisherPtr  = typename rclcpp::Publisher<T>::SharedPtr;
template<typename T> using SubscriberPtr = typename rclcpp::Subscription<T>::SharedPtr;

// template<typename T> using ServiceClientPtr = typename rclcpp::Service<T>::SharedPtr;

/* 
    The path has to be divided to "little steps" 
    for continuous control of the drone in offboard-ctrl mode 
*/
using DronePathDiscretePointType = px4_msgs::msg::TrajectorySetpoint;
using DronePathPointType         = DronePathDiscretePointType;
using DroneStatusType            = px4_msgs::msg::OffboardControlMode;
using DroneCmdType               = px4_msgs::msg::VehicleCommand;
using DroneCmdIdTypeType         = u32;
using DroneCmdParamListType      = std::array<f32, 7>;
using DroneLocalPositionType     = px4_msgs::msg::VehicleLocalPosition;
using DroneOdometryType          = px4_msgs::msg::VehicleOdometry;
// using DroneTimeSyncPoint     = px4_msgs::msg::TimesyncStatus;

