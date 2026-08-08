#pragma once
/*
    PX4Backend I/O contract — the SINGLE source of truth for everything
    platform-specific about talking to PX4 over ROS 2:
      - topic names            (kPx4* below)
      - QoS profiles           (px4_pub_qos / px4_sub_qos)
      - stream/handshake tuning (rates, warmup)
      - NED tuning constants    (used by Tasks 1-3; ENU equivalents added in Task 4)
      - wire-message builders   (OffboardTranslator::*)

    NOTHING ROS- or PX4-specific should be hardcoded inside px4_backend.cpp; it
    all lives here so a reviewer changes one file to retarget topics/QoS/tuning.

    Pure math (frame conversions) lives in frame_convert.hpp (no ROS include),
    so it stays unit-testable in isolation.
*/
#include <array>
#include <limits>
#include <rclcpp/rclcpp.hpp>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/battery_status.hpp>
#include <util2/C/base_type.h>
#include <util2/C/macro.h>
#include "frame/frame_convert.hpp"


/* ---- ROS 2 topic names (PX4 uXRCE-DDS bridge) ---------------------------- */
/* PX4 appends _vN when a .msg has MESSAGE_VERSION=N>0. VehicleStatus is v4;   */
/* VehicleOdometry is v0 (no suffix). A sub on the wrong name fails SILENTLY.  */
constexpr const char* kPx4TrajSetpointTopic = "/fmu/in/trajectory_setpoint";
constexpr const char* kPx4OffboardModeTopic = "/fmu/in/offboard_control_mode";
constexpr const char* kPx4VehicleCmdTopic   = "/fmu/in/vehicle_command";
constexpr const char* kPx4OdometryTopic     = "/fmu/out/vehicle_odometry";
constexpr const char* kPx4VehicleStatusTopic = "/fmu/out/vehicle_status_v4";
constexpr const char* kPx4BatteryStatusTopic = "/fmu/out/battery_status_v1";  /* MESSAGE_VERSION=1 */

/* ---- Stream loop + handshake tuning -------------------------------------- */
constexpr u32 kMsInOneSecond            = 1000;
/* DJI Tello cannot ingest setpoints above ~20Hz; publish at 30Hz for margin.  */
constexpr u32 kOffboardPublishRateHz    = 30;
constexpr u32 kOffboardPublishPeriodMs  = kMsInOneSecond / kOffboardPublishRateHz;
/* PX4 rejects an OFFBOARD switch unless setpoints have streamed for ~1s.       */
/* 40 @ 30Hz ~= 1.33s of warmup before arm + set_offboard.                      */
constexpr u64 kOffboardWarmupSetpoints  = 40;

/* ---- NED tuning constants (PX4 wire-internal). The ENU constants the FMU
   state machine uses now live in fmu/fmu_node_base.hpp. --------------------- */
/* NED: down is positive. Proven takeoff profile from speech_to_action.         */
constexpr f32 kTakeoffTargetAltNed = -2.0f;   /* climb target ~2m up.          */
constexpr f32 kTakeoffClimbVelNed  = -2.0f;   /* climb at 2 m/s (weak -1.0 tipped on uneven terrain). */
constexpr f32 kLandDescendVelNed   =  0.5f;   /* descend at 0.5 m/s.           */
constexpr f32 kGroundContactAltNed = -0.1f;   /* consider landed near ~0.      */


/* ---- QoS profiles -------------------------------------------------------- */
/* PX4 command/setpoint inputs: best-effort + transient-local, depth 10.       */
static inline rclcpp::QoS px4_pub_qos() {
    rclcpp::QoS q(10);
    q.best_effort();
    q.transient_local();
    return q;
}
/* PX4 telemetry outputs (odom/status): sensor-data profile.                   */
static inline rclcpp::QoS px4_sub_qos() {
    return rclcpp::QoS(rclcpp::SensorDataQoS());
}


/*
    OffboardTranslator: a DUMB collection of wire-message builders. No node, no
    publishers, no state. Callers pass world-NED velocities (built via
    frame_convert.hpp) and publish the returned messages at ~30Hz.
*/
struct OffboardTranslator {
    using TrajectorySetpoint  = px4_msgs::msg::TrajectorySetpoint;
    using OffboardControlMode = px4_msgs::msg::OffboardControlMode;
    using VehicleCommand      = px4_msgs::msg::VehicleCommand;

    static constexpr u8 kDroneSysId  = 1;
    static constexpr u8 kGroundSysId = 255;

    static OffboardControlMode mode_velocity(u64 ts_us) {
        OffboardControlMode m{};
        m.timestamp         = ts_us;
        m.position          = false;
        m.velocity          = true;
        m.acceleration      = false;
        m.attitude          = false;
        m.body_rate         = false;
        m.thrust_and_torque = false;
        m.direct_actuator   = false;
        return m;
    }

    static TrajectorySetpoint velocity_setpoint(u64 ts_us, Vec3 const& velNed, f32 yawspeed) {
        const f32 kNan = std::numeric_limits<f32>::quiet_NaN();
        TrajectorySetpoint sp{};
        sp.timestamp    = ts_us;
        sp.position     = { kNan, kNan, kNan };
        sp.velocity     = { velNed.x, velNed.y, velNed.z };
        sp.acceleration = { kNan, kNan, kNan };
        sp.jerk         = { kNan, kNan, kNan };
        sp.yaw          = kNan;
        sp.yawspeed     = yawspeed;
        return sp;
    }

    static VehicleCommand make_command(
        u64                       ts_us,
        u32                       command,
        std::array<f32, 7> const& params = {}
    ) {
        VehicleCommand c{};
        c.timestamp        = ts_us;
        c.param1           = params[0];
        c.param2           = params[1];
        c.param3           = params[2];
        c.param4           = params[3];
        c.param5           = __scast(f64, params[4]);
        c.param6           = __scast(f64, params[5]);
        c.param7           = params[6];
        c.command          = command;
        c.target_system    = kDroneSysId;
        c.target_component = kDroneSysId;
        c.source_system    = kGroundSysId;
        c.source_component = 0;
        c.confirmation     = 0;
        c.from_external    = true;
        return c;
    }

    static VehicleCommand arm(u64 ts_us, bool on) {
        std::array<f32, 7> p{};
        p[0] = on ? 1.0f : 0.0f;
        return make_command(ts_us, VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM, p);
    }

    /* Enable custom OFFBOARD main mode (base=1, main=6). */
    static VehicleCommand set_offboard(u64 ts_us) {
        std::array<f32, 7> p{};
        p[0] = 1.0f;
        p[1] = 6.0f;
        return make_command(ts_us, VehicleCommand::VEHICLE_CMD_DO_SET_MODE, p);
    }

    static VehicleCommand force_disarm(u64 ts_us) {
        std::array<f32, 7> p{};
        p[0] = 0.0f;
        p[1] = 21196.0f; /* magic: bypass PX4 landing checks. */
        return make_command(ts_us, VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM, p);
    }
};
