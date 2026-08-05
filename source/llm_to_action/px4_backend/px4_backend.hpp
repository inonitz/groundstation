#pragma once
/*
    PX4Backend — the concrete drone backend for PX4 SITL / a real PX4 FC.

    Owns EVERYTHING platform-specific: the three PX4 publishers, the odom/status
    subscriptions, the ~30Hz offboard stream loop, and the arm->OFFBOARD handshake.
    The FMU holds one of these and drives it through semantic verbs; it never
    touches a px4_msgs type or the wire directly.

    Concurrency: this reuses the FMU's proven model — a Reentrant callback group
    with std::atomic scalar sharing (odom callback -> control/stream loops). No
    mutex is introduced (see design spec Future-Milestone M1).

    Frame: canonical ENU (East, North, Up+) across the seam. NED exists ONLY on the
    PX4 wire; odomCallback converts NED->ENU on ingest and streamTick converts
    ENU->NED on egress -- the two isolated conversion points.
*/
#include <atomic>
#include <cmath>
#include <px4_msgs/msg/vehicle_odometry.hpp>
#include <px4_msgs/msg/vehicle_status.hpp>

#include "px4_backend_base.hpp"   /* topics, QoS, tuning, OffboardTranslator, Vec3 */
#include "generic_backend/generic_backend.hpp"  /* GenericBackend + shared BackendStatus/IOState/Odometry */


using OdomMsgType   = px4_msgs::msg::VehicleOdometry;
using StatusMsgType = px4_msgs::msg::VehicleStatus;


/* BackendStatus / IOState / Odometry now live in generic_backend_types.hpp
   (single definition shared with every backend across the seam). */


class PX4Backend : public GenericBackend<PX4Backend> {
public:
    PX4Backend(rclcpp::Node* node, rclcpp::CallbackGroup::SharedPtr cbg);
    ~PX4Backend();

    /* ---- seam impls (invoked through GenericBackend<PX4Backend>) ----------- */
    bool start_impl();   /* create pubs/subs + stream timer. Call once after construction. */
    void stop_impl();    /* cancel the stream timer (dtor also calls this).                */

    BackendStatus takeoff_impl();                          /* STANDBY->HANDSHAKING, else REJECTED. */
    BackendStatus land_impl();                             /* no-op OK; FMU streams the descent.   */
    void          set_velocity_impl(Vec3 worldVel, f32 yawspeed);  /* stream this ENU vel.         */
    void          disarm_impl();
    void          force_disarm_impl();

    Odometry odometry_impl() const;
    IOState  state_impl() const { return m_ioState.load(std::memory_order_relaxed); }

    /* ---- backend-specific (off-seam) --------------------------------------- */
    bool     gotFirstOdom() const { return m_gotFirstOdom.load(std::memory_order_relaxed); }

private:
    void streamTick();
    void odomCallback(const OdomMsgType::ConstSharedPtr msg);
    void statusCallback(const StatusMsgType::ConstSharedPtr msg);
    u64  nowUs() const { return __scast(u64, m_node->get_clock()->now().nanoseconds() / 1000); }

    rclcpp::Node*                    m_node;
    rclcpp::CallbackGroup::SharedPtr m_cbg;

    rclcpp::Publisher<OffboardTranslator::TrajectorySetpoint>::SharedPtr  m_pubTraj;
    rclcpp::Publisher<OffboardTranslator::OffboardControlMode>::SharedPtr m_pubMode;
    rclcpp::Publisher<OffboardTranslator::VehicleCommand>::SharedPtr      m_pubCmd;
    rclcpp::Subscription<OdomMsgType>::SharedPtr                          m_subOdom;
    rclcpp::Subscription<StatusMsgType>::SharedPtr                        m_subStatus;

    /* Shared pose (odom cb -> control/stream loops). */
    std::atomic<f32> m_posN{0.0f}, m_posE{0.0f}, m_posD{0.0f}, m_yaw{0.0f};
    std::atomic<f32> m_velN{0.0f}, m_velE{0.0f}, m_velD{0.0f}, m_yawrate{0.0f};
    std::atomic<u64> m_hostStampUs{0};
    /* Streamed setpoint (control loop -> stream loop). */
    std::atomic<f32> m_vx{0.0f}, m_vy{0.0f}, m_vz{0.0f}, m_yawsp{0.0f};
    /* Handshake / wire state. */
    std::atomic<IOState> m_ioState{IOState::STANDBY};
    std::atomic<u8>      m_navState{0}, m_armingState{0};
    std::atomic<u64>     m_setpointCount{0}, m_handshakeStart{0};
    std::atomic<bool>    m_gotFirstOdom{false};

    /* Stream timer LAST -> destroyed FIRST (stops ticking before pubs die). */
    rclcpp::TimerBase::SharedPtr m_streamTimer;
};
