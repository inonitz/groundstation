#pragma once
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/bool.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include "px4_offboard_node_base.hpp"


class OffboardControl : public rclcpp::Node {
public:
	OffboardControl() : Node("offboard_control") {
        // PX4 Requires Best Effort & Transient Local QoS 
        // https://docs.px4.io/main/en/ros/ros2_comm.html
        rclcpp::QoS qos_profile(kDefaultHistoryBufSize);
        qos_profile.best_effort();
        qos_profile.transient_local();

		const auto timer_cb = [this]() {
            timer_callback(*this);
            return;
        };

        m_pubPath   = this->create_publisher<DronePathPointType>(kInTrajectoryPointTopic,  qos_profile);
		m_pubStatus = this->create_publisher<DroneStatusType   >(kInOffboardCtrlModeTopic, qos_profile);
		m_pubCMD    = this->create_publisher<DroneCmdType      >(kInVehicleCmdTopic,       qos_profile);
        
        // m_subKeyboardTwist = this->create_subscription<Px4KeyboardTwistType>(
        //     kPx4KeyboardTwistTopic, kDefaultHistoryBufSize,
        //     [this](Px4KeyboardTwistType::ConstSharedPtr msg) { external_velocity_callback(msg); }
        // );
        // m_subKeyboardArm = this->create_subscription<Px4KeyboardArmType>(
        //     kPx4KeyboardArmingStateTopic, kDefaultHistoryBufSize,
        //     [this](Px4KeyboardArmType::ConstSharedPtr msg) { external_arming_callback(msg); }
        // );
        // m_subASRTwist = this->create_subscription<ASRTextTwistType>(
        //     kOutASRServerTwistTopic, kDefaultHistoryBufSize,
        //     [this](ASRTextTwistType::ConstSharedPtr msg) { external_velocity_callback(msg); }
        // );
        // m_subASRArmState = this->create_subscription<ASRArmType>(
        //     kOutASRServerArmStateTopic, kDefaultHistoryBufSize,
        //     [this](ASRArmType::ConstSharedPtr msg) { external_arming_callback(msg); }
        // );
        m_subLocalPos = this->create_subscription<DroneOdometryType>(
            kOutVehicleOdometryTopic, rclcpp::SensorDataQoS(),
            [this](const DroneOdometryType::ConstSharedPtr msg) {
                m_current_z_ned = msg->position[2];
            }
        );

        m_timer = this->create_wall_timer(kOffboardUpdatePeriod, timer_cb);


        RCLCPP_INFO(this->get_logger(), "Offboard Control Node Initialized");
        return;
    }

    /* Basic Operations */
    void arm(bool armTrueDisarmFalse);
    void takeoff();
    void land();
    void force_disarm();

    /* 
        Will run every 'frame' depending on the Refresh/Update period set. 
        Atleast 2Hz, will be more.
    */
    void timer_callback(OffboardControl& toModify);

    /* Subcriptions - Updating Local State using Keyboard Package */
    void external_arming_callback(std_msgs::msg::Bool msg);
    void external_velocity_callback(geometry_msgs::msg::Twist::SharedPtr msg);

    /* Subcriptions - Updating Local State using Topics exposed by Flight Controller */
    void external_status_callback(DroneStatusType status);
    void external_attitude_callback();


private:
    __force_inline auto timestamp_now_ms() {
        return this->get_clock()->now().nanoseconds() / 1000;
    }


    __force_inline void publish_trajectory_setpoint(Vec3 const& vel, f32 yawPerSec) {
        const std::array<f32, 3> kNan{
            std::numeric_limits<f32>::quiet_NaN(),
            std::numeric_limits<f32>::quiet_NaN(),
            std::numeric_limits<f32>::quiet_NaN()
        };
        DronePathPointType _{};


        _.timestamp    = timestamp_now_ms();
        _.position     = kNan;
        _.velocity     = { vel.x, vel.y, vel.z };
        _.acceleration = kNan;
        _.jerk         = kNan;
        _.yaw          = kNan[0];
        _.yawspeed     = yawPerSec;

        m_pubPath->publish(_);
        ++m_setPointPublished;
        return;
    }

    __force_inline void publish_offboardctrl_mode() {
        DroneStatusType _{};

        _.timestamp         = timestamp_now_ms();
        _.position          = false;
        _.velocity          = true;
        _.acceleration      = false;
        _.attitude          = false;
        _.body_rate         = false;
        _.thrust_and_torque = false;
        _.direct_actuator   = false;

        m_pubStatus->publish(_);
        ++m_setModePublished;
        return;
    }

    __force_inline void publish_vehicle_cmd(
        DroneCmdIdTypeType    const& cmd, 
        DroneCmdParamListType const& params={}
    ) {
        DroneCmdType _{};

        _.timestamp = timestamp_now_ms();
        _.param1 = params[0];
        _.param2 = params[1];
        _.param3 = params[2];
        _.param4 = params[3];
        _.param5 = __scast(f64, params[4]);
        _.param6 = __scast(f64, params[5]);
        _.param7 = params[6];
        _.command = cmd;
        _.target_system     = kDefaultDroneDeviceID;
        _.target_component  = kDefaultDroneDeviceID;
        _.source_system     = kDefaultGroundStationDeviceID;
        _.source_component  = 0;    /* Default Component ID */
        _.confirmation      = 0;    /* Always Zero for Offboard Scripts: */
        _.from_external     = true; /* Not coming from the internal PX4 C++ Code */
        m_pubCMD->publish(_);
        ++m_cmdPublished;
        return;
    }

private:
    enum class DroneState : std::uint8_t { 
        STANDBY, 
        TAKEOFF, 
        FLIGHT, 
        LANDING 
    };

	PublisherPtr<DronePathPointType> m_pubPath;
	PublisherPtr<DroneStatusType>    m_pubStatus;
	PublisherPtr<DroneCmdType>       m_pubCMD;
    SubscriberPtr<DroneOdometryType> m_subLocalPos;
    TimerSharedPtr                   m_timer;
    std::atomic<u64>                 m_setPointPublished;
    std::atomic<u64>                 m_setModePublished;
    std::atomic<u64>                 m_cmdPublished;

    Vec3 m_currentVel{0.0f, 0.0f, 0.0f};
    f32  m_currentYawSpeed{0.0f};
    f32  m_current_z_ned{0.0f};
    DroneState m_state{DroneState::STANDBY};
};