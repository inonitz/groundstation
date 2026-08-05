#include "px4_backend.hpp"

/* All shared-scalar access uses relaxed ordering, matching the proven FMU code
   (single logical producer per field; correctness does not depend on cross-field
   ordering here). */
static constexpr std::memory_order rlx = std::memory_order_relaxed;


PX4Backend::PX4Backend(rclcpp::Node* node, rclcpp::CallbackGroup::SharedPtr cbg)
    : m_node(node), m_cbg(std::move(cbg)) {}

PX4Backend::~PX4Backend() { stop(); }


void PX4Backend::start() {
    rclcpp::SubscriptionOptions subOpts;
    subOpts.callback_group = m_cbg;

    m_pubTraj = m_node->create_publisher<OffboardTranslator::TrajectorySetpoint>(
        kPx4TrajSetpointTopic, px4_pub_qos());
    m_pubMode = m_node->create_publisher<OffboardTranslator::OffboardControlMode>(
        kPx4OffboardModeTopic, px4_pub_qos());
    m_pubCmd  = m_node->create_publisher<OffboardTranslator::VehicleCommand>(
        kPx4VehicleCmdTopic, px4_pub_qos());

    m_subOdom = m_node->create_subscription<OdomMsgType>(
        kPx4OdometryTopic, px4_sub_qos(),
        std::bind(&PX4Backend::odomCallback, this, std::placeholders::_1), subOpts);
    m_subStatus = m_node->create_subscription<StatusMsgType>(
        kPx4VehicleStatusTopic, px4_sub_qos(),
        std::bind(&PX4Backend::statusCallback, this, std::placeholders::_1), subOpts);

    m_streamTimer = m_node->create_wall_timer(
        std::chrono::milliseconds{kOffboardPublishPeriodMs},
        std::bind(&PX4Backend::streamTick, this), m_cbg);

    RCLCPP_INFO(m_node->get_logger(), "[PX4_BACKEND_DEBUG] started (stream %uHz).",
        kOffboardPublishRateHz);
}

void PX4Backend::stop() {
    if (m_streamTimer) m_streamTimer->cancel();
}


/* ---- Subscriptions ------------------------------------------------------- */
void PX4Backend::odomCallback(const OdomMsgType::ConstSharedPtr msg) {
    f32 qw = msg->q[0], qx = msg->q[1], qy = msg->q[2], qz = msg->q[3];
    /* PX4 quaternion order is [w, x, y, z]. Extract yaw (Z), NED convention. */
    f32 yawNed = std::atan2(2.0f * (qw * qz + qx * qy),
                            1.0f - 2.0f * (qy * qy + qz * qz));

    /* Convert the PX4 NED sample to canonical ENU here -- the ONLY place NED
       enters the seam. The atomics named *N/*E/*D now hold ENU (x=East, y=North,
       z=Up); odometry() returns them as a proper ENU Vec3. */
    Vec3 posEnu = ned_to_enu({ msg->position[0], msg->position[1], msg->position[2] });
    Vec3 velEnu = ned_to_enu({ msg->velocity[0], msg->velocity[1], msg->velocity[2] });
    f32  yawEnu = enu_yaw_from_ned(yawNed);

    m_posN.store(posEnu.x, rlx);   /* East  */
    m_posE.store(posEnu.y, rlx);   /* North */
    m_posD.store(posEnu.z, rlx);   /* Up    */
    m_yaw.store(yawEnu, rlx);
    m_velN.store(velEnu.x, rlx);
    m_velE.store(velEnu.y, rlx);
    m_velD.store(velEnu.z, rlx);
    m_yawrate.store(enu_yawrate_to_ned(msg->angular_velocity[2]), rlx);  /* NED<->ENU rate: negate (self-inverse). */
    m_hostStampUs.store(nowUs(), rlx);

    if (!m_gotFirstOdom.load(rlx)) {
        m_gotFirstOdom.store(true, rlx);
        RCLCPP_INFO(m_node->get_logger(),
            "[PX4_BACKEND_DEBUG] FIRST ODOM altENU=%.2f yaw=%.2f", posEnu.z, yawEnu);
    }
}

void PX4Backend::statusCallback(const StatusMsgType::ConstSharedPtr msg) {
    m_navState.store(msg->nav_state, rlx);
    m_armingState.store(msg->arming_state, rlx);
}


/* ---- ~30Hz offboard stream loop (the ONLY publisher) --------------------- */
void PX4Backend::streamTick() {
    u64  ts = nowUs();
    Vec3 velEnu{ m_vx.load(rlx), m_vy.load(rlx), m_vz.load(rlx) };  /* FMU streams ENU vel (climb/descent). */
    f32  yawspEnu = m_yawsp.load(rlx);
    /* Convert canonical ENU back to PX4 NED on the way out (the ONLY egress point). */
    Vec3 velNed  = enu_to_ned(velEnu);
    f32  yawspNed = enu_yawrate_to_ned(yawspEnu);

    /* Stream mode + setpoint FIRST so PX4 sees an active offboard signal. */
    m_pubMode->publish(OffboardTranslator::mode_velocity(ts));
    m_pubTraj->publish(OffboardTranslator::velocity_setpoint(ts, velNed, yawspNed));
    u64 cnt = m_setpointCount.fetch_add(1, rlx) + 1;

    /* Handshake: arm FIRST, then request OFFBOARD; retry every tick until PX4
       confirms both. Gate on first odometry (estimator ready) + warmup, else
       arming before a valid velocity estimate spins motors -> no climb -> disarm. */
    if (m_ioState.load(rlx) == IOState::HANDSHAKING) {
        if (!m_gotFirstOdom.load(rlx)) return;
        if (cnt - m_handshakeStart.load(rlx) < kOffboardWarmupSetpoints) return;

        u8 nav = m_navState.load(rlx);
        u8 arm = m_armingState.load(rlx);
        if (arm != StatusMsgType::ARMING_STATE_ARMED) {
            m_pubCmd->publish(OffboardTranslator::arm(ts, true));
        }
        if (nav != StatusMsgType::NAVIGATION_STATE_OFFBOARD) {
            m_pubCmd->publish(OffboardTranslator::set_offboard(ts));
        }
        if (arm == StatusMsgType::ARMING_STATE_ARMED
            && nav == StatusMsgType::NAVIGATION_STATE_OFFBOARD) {
            m_ioState.store(IOState::FLIGHT, rlx);
            RCLCPP_INFO(m_node->get_logger(),
                "[PX4_BACKEND_DEBUG] OFFBOARD+ARM CONFIRMED at setpoints=%lu",
                __scast(unsigned long, cnt));
        }
    }

    RCLCPP_INFO_THROTTLE(m_node->get_logger(), *m_node->get_clock(), 1000,
        "[PX4_BACKEND_DEBUG] io=%d setpoints=%lu nav=%d arm=%d altENU=%.2f velzENU=%.2f",
        __scast(int, m_ioState.load(rlx)), __scast(unsigned long, cnt),
        __scast(int, m_navState.load(rlx)), __scast(int, m_armingState.load(rlx)),
        m_posD.load(rlx), velEnu.z);
}


/* ---- Semantic verbs ------------------------------------------------------ */
BackendStatus PX4Backend::takeoff() {
    if (m_ioState.load(rlx) != IOState::STANDBY) {
        return { BackendStatus::Code::REJECTED };
    }
    /* Warm up the stream from the current count, then the tick engages offboard. */
    m_handshakeStart.store(m_setpointCount.load(rlx), rlx);
    m_ioState.store(IOState::HANDSHAKING, rlx);
    RCLCPP_INFO(m_node->get_logger(),
        "[PX4_BACKEND_DEBUG] takeoff: STANDBY->HANDSHAKING (warmup start=%lu).",
        __scast(unsigned long, m_handshakeStart.load(rlx)));
    return { BackendStatus::Code::PENDING };
}

BackendStatus PX4Backend::land() {
    return { BackendStatus::Code::OK };  /* PX4: FMU streams the descent; nothing to do here. */
}

void PX4Backend::set_velocity(Vec3 worldVel, f32 yawspeed) {
    m_vx.store(worldVel.x, rlx);
    m_vy.store(worldVel.y, rlx);
    m_vz.store(worldVel.z, rlx);
    m_yawsp.store(yawspeed, rlx);
}

void PX4Backend::disarm() {
    m_pubCmd->publish(OffboardTranslator::arm(nowUs(), false));
    m_ioState.store(IOState::STANDBY, rlx);
}

void PX4Backend::force_disarm() {
    m_pubCmd->publish(OffboardTranslator::force_disarm(nowUs()));
    m_ioState.store(IOState::STANDBY, rlx);
}


/* ---- Telemetry ----------------------------------------------------------- */
Odometry PX4Backend::odometry() const {
    Odometry o;
    o.pos          = { m_posN.load(rlx), m_posE.load(rlx), m_posD.load(rlx) };
    o.vel          = { m_velN.load(rlx), m_velE.load(rlx), m_velD.load(rlx) };
    o.yaw          = m_yaw.load(rlx);
    o.yawrate      = m_yawrate.load(rlx);
    o.host_stamp_us = m_hostStampUs.load(rlx);
    o.valid        = m_gotFirstOdom.load(rlx);
    return o;
}
