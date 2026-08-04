#pragma once
#include <array>
#include <cmath>
#include <limits>
#include <util2/C/base_type.h>
#include <util2/C/macro.h>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>


/*
    OffboardTranslator: a DUMB struct. It converts generic world-frame (NED)
    setpoints into PX4 wire messages. No ROS node, no publishers, no state.
    The FMU owns the flight state machine and the publishers; it just calls
    these builders and publishes the result at ~30Hz.

    Frame note: all velocities passed IN here are already world-NED
    (north, east, down). FLU(body) -> NED conversion is done separately via
    flu_to_ned() when a relative VLM command is first activated.
*/


struct Vec3 { f32 x{0.0f}, y{0.0f}, z{0.0f}; };


struct OffboardTranslator {
    using TrajectorySetpoint  = px4_msgs::msg::TrajectorySetpoint;
    using OffboardControlMode = px4_msgs::msg::OffboardControlMode;
    using VehicleCommand      = px4_msgs::msg::VehicleCommand;

    static constexpr u8 kDroneSysId   = 1;
    static constexpr u8 kGroundSysId  = 255;

    /* Rotate a body FLU vector (fwd,left,up) into world NED given current yaw. */
    /* NOTE: yaw is NED convention (CW-positive from north). Verify in sim.     */
    static Vec3 flu_to_ned(Vec3 const& flu, f32 yaw) {
        Vec3 ned;
        f32  c;
        f32  s;

        c = std::cos(yaw);
        s = std::sin(yaw);
        ned.x = flu.x * c + flu.y * s;   /* north */
        ned.y = flu.x * s - flu.y * c;   /* east  */
        ned.z = -flu.z;                  /* down  */
        return ned;
    }

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
        u64                          ts_us,
        u32                          command,
        std::array<f32, 7> const&    params = {}
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
