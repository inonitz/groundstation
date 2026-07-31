#pragma once
#include <util/base.hpp>
#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
#include <px4_msgs/msg/vehicle_odometry.hpp>


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
constexpr const char* kOutVehiclePositionTopic = "/fmu/out/vehicle_local_position";
constexpr const char* kOutVehicleOdometryTopic = "/fmu/out/vehicle_odometry";
constexpr const char* kOutVehicleStatusTopic   = "/fmu/out/vehicle_status_v1";
constexpr const char* kOutVehicleAttitudeTopic = "/fmu/out/vehicle_attitude";


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

