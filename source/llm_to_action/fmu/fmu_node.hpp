#pragma once
#include <atomic>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>
#include <memory>
#include <nlohmann/json.hpp>
#include <readerwriterqueue.h>
#include <util2/C/macro.h>
#include <util2/time.hpp>
#include <rclcpp/rclcpp.hpp>

#include <px4_msgs/msg/vehicle_odometry.hpp>
#include <px4_msgs/msg/vehicle_status.hpp>
#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <cv_bridge/cv_bridge.hpp>
#include <base64.h>

#include "gstreamer_udp_cam_rx/rx_node_base.hpp"  /* UDPCamMsgType, khUDPCamMsgType, camera topic */
#include "fmu_node_base.hpp"
#include "llm_base.hpp"
#include "llamaclient.hpp"
#include "offboard_translator.hpp"


using OdomMsgType   = px4_msgs::msg::VehicleOdometry;
using StatusMsgType = px4_msgs::msg::VehicleStatus;

typedef char FixedStringType[32];
typedef char LargeFixedStringType[128];


enum class TaskState {
    PENDING,
    RUNNING,
    PAUSED,
    FINISHED_SUCCESS,
    FINISHED_FAIL,
    STOPPED
};

enum class CommandID : u8 {
    TAKEOFF  = 0,
    LAND     = 1,
    STOP     = 2,
    GO       = 3,
    CURVE    = 4,
    ROTATE   = 5,
    ORBIT    = 6,
    SEARCH   = 7,
    REASSESS = 8,
    MAX_ID   = 10
};

/* FMU-owned flight state machine (was baked into the old offboard node). */
enum class FlightState : u8 {
    STANDBY,
    TAKEOFF,
    FLIGHT,
    LANDING
};

struct CmdTakeoff {};
struct CmdLand {};
struct CmdStop {};

struct CmdGo {
    f32 x{0.0f}, y{0.0f}, z{0.0f}, speed{0.0f};
};

struct CmdCurve {
    f32 x1{0.0f}, y1{0.0f}, z1{0.0f};
    f32 x2{0.0f}, y2{0.0f}, z2{0.0f};
    f32 speed{0.0f};
    u64 m_reserved{0};
};

struct CmdRotate {
    i32  angle_deg{0};
    bool cw_or_ccw{true};
    u64  m_reserved{0};
};

struct CmdOrbit {
    FixedStringType target{"\0"};
    f32             radius{0.0f};
    f32             angle_deg{0.0f};
    f32             speed{0.0f};
    bool            cw_or_ccw{true};
};

struct CmdSearch {
    FixedStringType target{"\0"};
    i32             expected_time{0};
    i32             timeout{0};
};

struct CmdReassess {
    FixedStringType reason{"\0"};
};

struct alignpk(CACHE_LINE_BYTES) GenericCommand {
    union {
        struct alignpk(CACHE_LINE_BYTES) {
            u8 m_rawId;
            u8 m_padToMultipleForCmd[sizeof(u64) - sizeof(u8)];
            u8 m_cmdBytes[CACHE_LINE_BYTES - sizeof(u64)];
        } m_rawBytes;

        struct {
            u64 m_reserved;
            union {
                CmdTakeoff  m_takeoff;
                CmdLand     m_land;
                CmdStop     m_stop;
                CmdGo       m_goto;
                CmdCurve    m_followCurve;
                CmdRotate   m_rotateInPlace;
                CmdOrbit    m_orbitTarget;
                CmdSearch   m_SearchTarget;
                CmdReassess m_Reassess;
            };
        } m_extractCmd;
    };

    GenericCommand() : m_rawBytes{__scast(u8, CommandID::MAX_ID), {0}, {0}} {}
    GenericCommand(CmdTakeoff) : m_rawBytes{__scast(u8, CommandID::TAKEOFF), {0}, {0}} {}
    GenericCommand(CmdLand)    : m_rawBytes{__scast(u8, CommandID::LAND), {0}, {0}} {}
    GenericCommand(CmdStop)    : m_rawBytes{__scast(u8, CommandID::STOP), {0}, {0}} {}

    GenericCommand(CmdGo const& cmd) : m_rawBytes{__scast(u8, CommandID::GO), {0}, {0}} {
        memcpy(&m_rawBytes.m_cmdBytes, &cmd, sizeof(CmdGo));
    }
    GenericCommand(CmdCurve const& cmd) : m_rawBytes{__scast(u8, CommandID::CURVE), {0}, {0}} {
        memcpy(&m_rawBytes.m_cmdBytes, &cmd, sizeof(CmdCurve));
    }
    GenericCommand(CmdRotate const& cmd) : m_rawBytes{__scast(u8, CommandID::ROTATE), {0}, {0}} {
        memcpy(&m_rawBytes.m_cmdBytes, &cmd, sizeof(CmdRotate));
    }
    GenericCommand(CmdOrbit const& cmd) : m_rawBytes{__scast(u8, CommandID::ORBIT), {0}, {0}} {
        memcpy(&m_rawBytes.m_cmdBytes, &cmd, sizeof(CmdOrbit));
    }
    GenericCommand(CmdSearch const& cmd) : m_rawBytes{__scast(u8, CommandID::SEARCH), {0}, {0}} {
        memcpy(&m_rawBytes.m_cmdBytes, &cmd, sizeof(CmdSearch));
    }
    GenericCommand(CmdReassess const& cmd) : m_rawBytes{__scast(u8, CommandID::REASSESS), {0}, {0}} {
        memcpy(&m_rawBytes.m_cmdBytes, &cmd, sizeof(CmdReassess));
    }

    /* Defaulted -> trivially copyable -> the queue keeps the fast POD path. */
    GenericCommand& operator=(GenericCommand const& other) = default;

    [[nodiscard]] CommandID id() const { return __scast(CommandID, m_rawBytes.m_rawId); }
};

struct ActiveTask {
    GenericCommand       m_cmd;
    TaskState            m_state = TaskState::PENDING;
    u64                  m_reserved = 0;
    FixedStringType      m_status = "\0";
    LargeFixedStringType m_thought = "\0";
};

/* Perception + telemetry are STUBBED for Phase 1 (no real YOLO yet). */
struct TargetDetection {
    FixedStringType label{"\0"};
    i32             bbox_xmin{0}, bbox_ymin{0}, bbox_xmax{0}, bbox_ymax{0};
    f32             median_depth_cm{0.0f};
};

struct VehicleTelemetry {
    f32 altitude_cm{0.0f};
    f32 vx_cm_s{0.0f}, vy_cm_s{0.0f}, vz_cm_s{0.0f};
    i32 battery_pct{100};
};

struct HistoryBuffer {
    std::string             m_initialCommand;
    std::vector<ActiveTask> m_completedTasks;
};


class FlightManagementUnitNode : public rclcpp::Node {
public:
    FlightManagementUnitNode() : rclcpp::Node("high_level_navigation_node") {
        rclcpp::SubscriptionOptions subOpts;
        /* NOTE (Phase 2): the PX4-specific QoS + publishers below move into a  */
        /* per-platform DroneBackend (PX4Backend / TelloBackend). Hardcoded     */
        /* here only for the Phase-1 PX4 SITL smoke test.                       */
        rclcpp::QoS px4Qos(10);

        px4Qos.best_effort();
        px4Qos.transient_local();

        m_cbGroup = this->create_callback_group(rclcpp::CallbackGroupType::Reentrant);
        subOpts.callback_group = m_cbGroup;

        m_taskQueue = std::make_unique<spsc_queue<ActiveTask>>(3 * kControlLoopRateHz);

        m_subImg = this->create_subscription<UDPCamMsgType>(
            kOutUDPCameraRawFrameTopic, 10,
            std::bind(&FlightManagementUnitNode::imgCallback, this, std::placeholders::_1),
            subOpts
        );
        m_subOdom = this->create_subscription<OdomMsgType>(
            kInOdometryTopic, rclcpp::SensorDataQoS(),
            std::bind(&FlightManagementUnitNode::odomCallback, this, std::placeholders::_1),
            subOpts
        );
        m_subStatus = this->create_subscription<StatusMsgType>(
            kInVehicleStatusTopic, rclcpp::SensorDataQoS(),
            std::bind(&FlightManagementUnitNode::statusCallback, this, std::placeholders::_1),
            subOpts
        );

        m_pubTraj = this->create_publisher<OffboardTranslator::TrajectorySetpoint>(
            "/fmu/in/trajectory_setpoint", px4Qos);
        m_pubMode = this->create_publisher<OffboardTranslator::OffboardControlMode>(
            "/fmu/in/offboard_control_mode", px4Qos);
        m_pubCmd  = this->create_publisher<OffboardTranslator::VehicleCommand>(
            "/fmu/in/vehicle_command", px4Qos);

        m_controlTimer = this->create_wall_timer(
            std::chrono::milliseconds{kControlLoopPeriodMs},
            std::bind(&FlightManagementUnitNode::controlLoop, this), m_cbGroup);
        m_offboardTimer = this->create_wall_timer(
            std::chrono::milliseconds{kOffboardPublishPeriodMs},
            std::bind(&FlightManagementUnitNode::offboardPublishLoop, this), m_cbGroup);

        m_vlmClient.create(kSystemPrompt, 0.4f, 1024);
        m_chat.m_completedTasks.reserve(kDefaultPromptHistorySize);

        RCLCPP_INFO(this->get_logger(), "Flight Management Unit Active.");
    }

    ~FlightManagementUnitNode() override { m_vlmClient.destroy(); }

    /* Bootstrap: arm the mission. Phase 1 may inject a canned plan instead of VLM. */
    void start(std::string_view objective, bool useCannedPlan = false) {
        m_chat.m_initialCommand = objective;
        m_missionActive.store(true, std::memory_order_release);
        if (useCannedPlan) {
            injectCannedPlan();
        }
        RCLCPP_INFO(this->get_logger(),
            "[DIAG] Mission started (canned=%d). queued~=%zu. objective: %.*s",
            __scast(int, useCannedPlan), m_taskQueue->size_approx(),
            __scast(int, objective.size()), objective.data());
    }

private:
    template <typename T>
    using spsc_queue = moodycamel::ReaderWriterQueue<T, sizeof(T)>;

    /* ---- Subscriptions --------------------------------------------------- */
    void imgCallback(khUDPCamMsgType msg) { std::atomic_store(&m_currImg, msg); }

    void odomCallback(const OdomMsgType::ConstSharedPtr msg) {
        f32 qw, qx, qy, qz, yaw;

        m_posN.store(msg->position[0], std::memory_order_relaxed);
        m_posE.store(msg->position[1], std::memory_order_relaxed);
        m_posD.store(msg->position[2], std::memory_order_relaxed);

        /* PX4 quaternion order is [w, x, y, z]. Extract yaw (Z). */
        qw = msg->q[0]; qx = msg->q[1]; qy = msg->q[2]; qz = msg->q[3];
        yaw = std::atan2(2.0f * (qw * qz + qx * qy),
                         1.0f - 2.0f * (qy * qy + qz * qz));
        m_yaw.store(yaw, std::memory_order_relaxed);

        if (!m_gotFirstOdom.load(std::memory_order_relaxed)) {
            m_gotFirstOdom.store(true, std::memory_order_relaxed);
            RCLCPP_INFO(this->get_logger(),
                "[DIAG] FIRST ODOM received. altNED=%.2f yaw=%.2f", msg->position[2], yaw);
        }
    }

    /* PX4 arming/nav-state feedback -> drives the confirmed offboard handshake. */
    void statusCallback(const StatusMsgType::ConstSharedPtr msg) {
        m_navState.store(msg->nav_state, std::memory_order_relaxed);
        m_armingState.store(msg->arming_state, std::memory_order_relaxed);
    }

    /* ---- 20Hz control + deterministic completion ------------------------- */
    void controlLoop() {
        f32         n, e, d, dx, dy, dz, dist, sp;
        ActiveTask  next;
        FlightState st;
        CommandID   id;

        n  = m_posN.load(std::memory_order_relaxed);
        e  = m_posE.load(std::memory_order_relaxed);
        d  = m_posD.load(std::memory_order_relaxed);
        st = m_flightState.load(std::memory_order_relaxed);

        /* State transitions driven by odometry. */
        if (st == FlightState::TAKEOFF && d <= kTakeoffTargetAltNed) {
            m_flightState.store(FlightState::FLIGHT, std::memory_order_relaxed);
            RCLCPP_INFO(this->get_logger(), "[DIAG] TAKEOFF->FLIGHT altNED=%.2f", d);
            completeCurrent("takeoff_ok");
            return;
        }
        if (st == FlightState::LANDING && d >= kGroundContactAltNed) {
            m_pubCmd->publish(OffboardTranslator::force_disarm(nowUs()));
            m_flightState.store(FlightState::STANDBY, std::memory_order_relaxed);
            m_offboardEngaged.store(false, std::memory_order_relaxed);
            RCLCPP_INFO(this->get_logger(), "[DIAG] LANDING->STANDBY altNED=%.2f", d);
            completeCurrent("land_ok");
            return;
        }
        if (st == FlightState::TAKEOFF || st == FlightState::LANDING) {
            return; /* offboard loop is executing the maneuver. */
        }

        /* FLIGHT / STANDBY: run the active movement task or pull the next. */
        if (m_hasActive) {
            id = m_currTask.m_cmd.id();
            if (id == CommandID::GO) {
                dx   = m_targetN - n;
                dy   = m_targetE - e;
                dz   = m_targetD - d;
                dist = std::sqrt(dx * dx + dy * dy + dz * dz);
                if (dist < kGoCompletionRadiusM) {
                    setActiveVel({0.0f, 0.0f, 0.0f}, 0.0f);
                    completeCurrent("go_ok");
                } else {
                    sp = m_activeSpeed / dist; /* normalize * speed (m/s). */
                    setActiveVel({dx * sp, dy * sp, dz * sp}, 0.0f);
                }
            } else {
                /* Non-GO movement not yet implemented in Phase 1: auto-complete. */
                completeCurrent("noop_ok");
            }
            return;
        }

        if (m_taskQueue->try_dequeue(next)) {
            activateTask(next);
        }
    }

    /* ---- ~30Hz offboard streaming (PX4 watchdog) ------------------------- */
    /* TODO (Phase 2): move this into the DroneBackend; the FMU should not      */
    /* drive a platform-specific publish loop directly.                        */
    void offboardPublishLoop() {
        Vec3        vel{0.0f, 0.0f, 0.0f};
        f32         yawspeed = 0.0f;
        FlightState st;
        u64         ts, cnt;
        u8          nav, armSt;

        ts  = nowUs();
        st  = m_flightState.load(std::memory_order_relaxed);
        cnt = m_setpointCount.fetch_add(1, std::memory_order_relaxed) + 1;

        switch (st) {
        case FlightState::STANDBY:  break;                       /* zero vel.   */
        case FlightState::TAKEOFF:  vel.z = kTakeoffClimbVelNed; break;
        case FlightState::LANDING:  vel.z = kLandDescendVelNed;  break;
        case FlightState::FLIGHT:
            vel.x    = m_activeVx.load(std::memory_order_relaxed);
            vel.y    = m_activeVy.load(std::memory_order_relaxed);
            vel.z    = m_activeVz.load(std::memory_order_relaxed);
            yawspeed = m_activeYaw.load(std::memory_order_relaxed);
            break;
        }

        /* Stream mode + setpoint FIRST so PX4 sees an active offboard signal. */
        m_pubMode->publish(OffboardTranslator::mode_velocity(ts));
        m_pubTraj->publish(OffboardTranslator::velocity_setpoint(ts, vel, yawspeed));

        /* PX4 offboard handshake. Proven order (speech_to_action): arm first,   */
        /* then request OFFBOARD — but never fire blind. Gate on first odometry   */
        /* (estimator ready) + warmup, then RETRY every tick until VehicleStatus  */
        /* confirms ARMED + OFFBOARD. Arming before the estimator was ready spun   */
        /* the motors with no valid velocity estimate -> no climb -> auto-disarm. */
        if (st == FlightState::TAKEOFF
            && !m_offboardEngaged.load(std::memory_order_relaxed)
            && m_gotFirstOdom.load(std::memory_order_relaxed)
            && (cnt - m_takeoffWarmupStart.load(std::memory_order_relaxed))
                >= kOffboardWarmupSetpoints)
        {
            nav   = m_navState.load(std::memory_order_relaxed);
            armSt = m_armingState.load(std::memory_order_relaxed);

            if (armSt != StatusMsgType::ARMING_STATE_ARMED) {
                m_pubCmd->publish(OffboardTranslator::arm(ts, true));
            }
            if (nav != StatusMsgType::NAVIGATION_STATE_OFFBOARD) {
                m_pubCmd->publish(OffboardTranslator::set_offboard(ts));
            }
            if (armSt == StatusMsgType::ARMING_STATE_ARMED
                && nav == StatusMsgType::NAVIGATION_STATE_OFFBOARD) {
                m_offboardEngaged.store(true, std::memory_order_relaxed);
                RCLCPP_INFO(this->get_logger(),
                    "[DIAG] OFFBOARD+ARM CONFIRMED at setpoints=%lu",
                    __scast(unsigned long, cnt));
            }
        }

        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
            "[DIAG] publishing: state=%d setpoints=%lu engaged=%d nav=%d arm=%d altNED=%.2f velz=%.2f",
            __scast(int, st), __scast(unsigned long, cnt),
            __scast(int, m_offboardEngaged.load(std::memory_order_relaxed)),
            __scast(int, m_navState.load(std::memory_order_relaxed)),
            __scast(int, m_armingState.load(std::memory_order_relaxed)),
            m_posD.load(std::memory_order_relaxed), vel.z);
    }

    /* ---- Task lifecycle helpers ------------------------------------------ */
    void activateTask(ActiveTask const& task) {
        f32       n, e, d, yaw;
        Vec3      relFlu, relNed;
        CmdGo     g;
        CommandID id;

        m_currTask = task;
        m_currTask.m_state = TaskState::RUNNING;
        m_hasActive = true;
        id = m_currTask.m_cmd.id();

        switch (id) {
        case CommandID::TAKEOFF:
            /* Do NOT arm here — the offboard loop engages after warmup. */
            m_takeoffWarmupStart.store(m_setpointCount.load(std::memory_order_relaxed),
                                       std::memory_order_relaxed);
            m_flightState.store(FlightState::TAKEOFF, std::memory_order_relaxed);
            RCLCPP_INFO(this->get_logger(),
                "[DIAG] TAKEOFF: warming up offboard stream before arm (start=%lu).",
                __scast(unsigned long, m_takeoffWarmupStart.load(std::memory_order_relaxed)));
            break;
        case CommandID::LAND:
            m_flightState.store(FlightState::LANDING, std::memory_order_relaxed);
            RCLCPP_INFO(this->get_logger(), "[DIAG] LAND activated.");
            break;
        case CommandID::GO:
            g   = m_currTask.m_cmd.m_extractCmd.m_goto;
            n   = m_posN.load(std::memory_order_relaxed);
            e   = m_posE.load(std::memory_order_relaxed);
            d   = m_posD.load(std::memory_order_relaxed);
            yaw = m_yaw.load(std::memory_order_relaxed);
            /* VLM gives relative FLU in cm -> world-NED target. */
            relFlu = { g.x / 100.0f, g.y / 100.0f, g.z / 100.0f };
            relNed = OffboardTranslator::flu_to_ned(relFlu, yaw);
            m_targetN = n + relNed.x;
            m_targetE = e + relNed.y;
            m_targetD = d + relNed.z;
            m_activeSpeed = (g.speed > 0.0f ? g.speed : kDefaultGoSpeedCmS) / 100.0f;
            RCLCPP_INFO(this->get_logger(),
                "[DIAG] GO activated. targetNED=(%.2f,%.2f,%.2f) speed=%.2f",
                m_targetN, m_targetE, m_targetD, m_activeSpeed);
            break;
        default:
            RCLCPP_INFO(this->get_logger(), "[DIAG] task id=%d auto-completes.",
                __scast(int, id));
            break; /* STOP / others auto-complete in controlLoop. */
        }
    }

    void completeCurrent(const char* status) {
        strncpy(m_currTask.m_status, status, sizeof(m_currTask.m_status) - 1);
        m_currTask.m_state = TaskState::FINISHED_SUCCESS;
        m_chat.m_completedTasks.push_back(m_currTask);
        m_hasActive = false;
        setActiveVel({0.0f, 0.0f, 0.0f}, 0.0f);
    }

    void setActiveVel(Vec3 const& v, f32 yawspeed) {
        m_activeVx.store(v.x, std::memory_order_relaxed);
        m_activeVy.store(v.y, std::memory_order_relaxed);
        m_activeVz.store(v.z, std::memory_order_relaxed);
        m_activeYaw.store(yawspeed, std::memory_order_relaxed);
    }

    __force_inline u64 nowUs() { return this->get_clock()->now().nanoseconds() / 1000; }

    /* ---- VLM plumbing (invoked by the Phase-2 event-driven wake, not a poll) ---- */
    std::string buildDynamicPrompt() {
        std::string prompt;
        char        buf[256];
        size_t      i;

        prompt  = std::string(kSystemPrompt) + "\n\n";
        prompt += "[COORDINATE FRAME]\nFLU (+X Forward, +Y Left, +Z Up)\n\n";
        prompt += "[MISSION OBJECTIVE]\n" + m_chat.m_initialCommand + "\n\n";
        prompt += "[EXECUTED COMMAND HISTORY]\n";
        for (i = 0; i < m_chat.m_completedTasks.size(); ++i) {
            snprintf(buf, sizeof(buf), "{\"status\":\"%s\", \"thought\":\"%s\", \"id\":%d}\n",
                m_chat.m_completedTasks[i].m_status,
                m_chat.m_completedTasks[i].m_thought,
                __scast(int, m_chat.m_completedTasks[i].m_cmd.id()));
            prompt += buf;
        }
        return prompt;
    }

    void callLlamaServer(std::string_view userQuery, khUDPCamMsgType const& img,
                         std::string& out) {
        std::string               b64, content, dyn;
        OptionalHttpRequestFuture  fut;
        nlohmann::json            j;
        cv::Mat                   frame, resized;
        std::vector<uchar>        buffer;
        std::vector<int>          params;

        params = { cv::IMWRITE_JPEG_QUALITY, 75 };
        frame  = cv_bridge::toCvShare(img, "bgr8")->image;
        if (!frame.empty()) {
            cv::resize(frame, resized, cv::Size{640, 640}, 0, 0, cv::INTER_LINEAR);
            cv::imencode(".jpg", resized, buffer, params);
            b64 = base64_encode(buffer.data(), buffer.size());
        }

        dyn = buildDynamicPrompt();
        fut = m_vlmClient.send(dyn, userQuery, b64);
        if (fut.has_value()) {
            auto res = fut->get();
            if (res && res->status == 200) {
                j = nlohmann::json::parse(res->body, nullptr, false);
                if (!j.is_discarded()) {
                    content = j["choices"][0]["message"]["content"];
                }
            }
        }
        out = content;
    }

    void translateToBaseCommands(std::string_view flightPlan) {
        nlohmann::json plan;
        std::string    action, thought;
        GenericCommand cmd;
        ActiveTask     task;
        CmdGo          go;

        plan = nlohmann::json::parse(flightPlan, nullptr, false);
        if (plan.is_discarded() || !plan.is_array()) {
            RCLCPP_WARN(this->get_logger(), "[DIAG] plan JSON parse failed / not array.");
            return;
        }

        for (const auto& item : plan) {
            if (!item.contains("action")) continue;
            action  = item["action"].get<std::string>();
            thought = item.value("thought", "");

            if (action == "takeoff") {
                cmd = GenericCommand(CmdTakeoff{});
            } else if (action == "land") {
                cmd = GenericCommand(CmdLand{});
            } else if (action == "stop") {
                cmd = GenericCommand(CmdStop{});
            } else if (action == "go") {
                go  = { item.value("x", 0.0f), item.value("y", 0.0f),
                        item.value("z", 0.0f), item.value("speed", 0.0f) };
                cmd = GenericCommand(go);
            } else {
                continue; /* Phase 1: only takeoff/land/stop/go executed. */
            }

            task = ActiveTask{};
            task.m_cmd   = cmd;
            task.m_state = TaskState::PENDING;
            strncpy(task.m_thought, thought.c_str(), sizeof(task.m_thought) - 1);
            m_taskQueue->enqueue(task); /* TODO: handle backpressure. */
        }
    }

    /* Canned plan is the SAME JSON the VLM emits, routed through the real       */
    /* translate path — no inverse function needed.                             */
    void injectCannedPlan() {
        static const char* kCannedPlanJson = R"([
            {"thought":"canned takeoff",    "action":"takeoff"},
            {"thought":"canned go forward", "action":"go", "x":100, "y":0, "z":0, "speed":30},
            {"thought":"canned land",       "action":"land"}
        ])";
        translateToBaseCommands(kCannedPlanJson);
    }

private:
    rclcpp::CallbackGroup::SharedPtr                m_cbGroup;
    rclcpp::Subscription<UDPCamMsgType>::SharedPtr  m_subImg;
    rclcpp::Subscription<OdomMsgType>::SharedPtr    m_subOdom;
    rclcpp::Subscription<StatusMsgType>::SharedPtr  m_subStatus;
    rclcpp::Publisher<OffboardTranslator::TrajectorySetpoint>::SharedPtr  m_pubTraj;
    rclcpp::Publisher<OffboardTranslator::OffboardControlMode>::SharedPtr m_pubMode;
    rclcpp::Publisher<OffboardTranslator::VehicleCommand>::SharedPtr      m_pubCmd;
    rclcpp::TimerBase::SharedPtr                    m_controlTimer;
    rclcpp::TimerBase::SharedPtr                    m_offboardTimer;

    std::unique_ptr<spsc_queue<ActiveTask>>         m_taskQueue;
    ActiveTask                                      m_currTask;
    bool                                            m_hasActive{false};
    std::atomic<bool>                               m_gotFirstOdom{false};

    llamaClientConnection                           m_vlmClient;
    khUDPCamMsgType                                 m_currImg;
    HistoryBuffer                                   m_chat;
    VehicleTelemetry                                m_telemetry;
    std::vector<TargetDetection>                    m_targets;

    /* Shared pose (odom thread -> control/offboard threads). */
    std::atomic<f32>          m_posN{0.0f}, m_posE{0.0f}, m_posD{0.0f}, m_yaw{0.0f};
    /* Active setpoint (control thread -> offboard thread). */
    std::atomic<f32>          m_activeVx{0.0f}, m_activeVy{0.0f}, m_activeVz{0.0f}, m_activeYaw{0.0f};
    std::atomic<FlightState>  m_flightState{FlightState::STANDBY};
    std::atomic<bool>         m_missionActive{false};
    std::atomic<bool>         m_offboardEngaged{false};
    std::atomic<u64>          m_setpointCount{0};
    std::atomic<u64>          m_takeoffWarmupStart{0};
    std::atomic<u8>           m_navState{0}, m_armingState{0};

    /* GO world-NED target + speed (control thread only). */
    f32 m_targetN{0.0f}, m_targetE{0.0f}, m_targetD{0.0f}, m_activeSpeed{0.3f};
};
