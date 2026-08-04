#pragma once
#include <atomic>
#include <string>
#include <vector>
#include <array>
#include <nlohmann/json.hpp>
#include <readerwriterqueue.h>
#include <util2/C/macro.h>
#include <util2/time.hpp>
#include <rclcpp/rclcpp.hpp>

#include "gstreamer_udp_cam_rx/rx_node_base.hpp"
#include "fmu_node_base.hpp"
#include "llm_base.hpp"
#include "llamaclient.hpp"

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <cv_bridge/cv_bridge.hpp>
#include <base64.h>


typedef char FixedStringType[32];
typedef char LargeFixedStringType[128];

constexpr FixedStringType kEmptyFixedString = "\0";

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
    GenericCommand(CmdTakeoff cmd) : m_rawBytes{__scast(u8, CommandID::TAKEOFF), {0}, {0}} {}
    GenericCommand(CmdLand cmd) : m_rawBytes{__scast(u8, CommandID::LAND), {0}, {0}} {}
    GenericCommand(CmdStop cmd) : m_rawBytes{__scast(u8, CommandID::STOP), {0}, {0}} {}
    
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

    GenericCommand& operator=(GenericCommand const& other) {
        if (this != &other) m_rawBytes = other.m_rawBytes;
        return *this;
    }

    [[nodiscard]] u8 id() const { return m_rawBytes.m_rawId; }
};

struct ActiveTask {
    GenericCommand       m_cmd;
    TaskState            m_state = TaskState::PENDING;
    u64                  m_reserved = 0;
    FixedStringType      m_status = "\0";
    LargeFixedStringType m_thought = "\0";
};

struct TargetDetection {
    FixedStringType label{"\0"};
    i32             bbox_xmin{0};
    i32             bbox_ymin{0};
    i32             bbox_xmax{0};
    i32             bbox_ymax{0};
    f32             median_depth_cm{0.0f};
};

struct VehicleTelemetry {
    f32 altitude_cm{0.0f};
    f32 vx_cm_s{0.0f};
    f32 vy_cm_s{0.0f};
    f32 vz_cm_s{0.0f};
    i32 battery_pct{0};
};

struct HistoryBuffer {
    std::string             m_initialCommand;
    std::vector<ActiveTask> m_completedTasks;
};

class FlightManagementUnitNode : public rclcpp::Node {
public:
    FlightManagementUnitNode() : rclcpp::Node("high_level_navigation_node") {
        rclcpp::SubscriptionOptions sub_opts;

        m_cbGroupTimers = this->create_callback_group(rclcpp::CallbackGroupType::Reentrant);
        sub_opts.callback_group = this->create_callback_group(
            rclcpp::CallbackGroupType::MutuallyExclusive
        );

        m_subImg = this->create_subscription<UDPCamMsgType>(
            "udp_camera_topic", 30,
            std::bind(&FlightManagementUnitNode::imgCallback, this, std::placeholders::_1),
            sub_opts
        );

        m_vlmTimer = this->create_wall_timer(
            std::chrono::milliseconds{kVlmReassessmentRateMs},
            std::bind(&FlightManagementUnitNode::vlmTimerCallback, this),
            m_cbGroupTimers
        );

        m_yoloTimer = this->create_wall_timer(
            std::chrono::milliseconds{kYoLoSegmentRefreshRateMs},
            std::bind(&FlightManagementUnitNode::yoloTimerCallback, this),
            m_cbGroupTimers
        );

        m_cmdQueueTimer = this->create_wall_timer(
            std::chrono::milliseconds{kCmdQueueUpdateRateMs},
            std::bind(&FlightManagementUnitNode::cmdQueueTimerCallback, this),
            m_cbGroupTimers
        );

        m_vlmClient.create(kSystemPrompt, 0.4f, 1024);
        m_chat.m_completedTasks.reserve(kDefaultPromptHistorySize);

        RCLCPP_INFO(this->get_logger(), "Flight Management Unit Active.");
    }

    ~FlightManagementUnitNode() override = default;

    void start(std::string_view initialObjective) {
        khUDPCamMsgType imgCopy;
        
        m_chat.m_initialCommand = initialObjective;
        imgCopy = std::atomic_load(&m_currImg);

        if (!imgCopy) {
            RCLCPP_INFO(this->get_logger(), "No Initial Frame delivered to VLM.\n");
        }
    }

private:
    template <typename T>
    using spsc_queue = moodycamel::ReaderWriterQueue<T, sizeof(T)>;

    void imgCallback(khUDPCamMsgType msg) {
        std::atomic_store(&m_currImg, msg);
    }

    void vlmTimerCallback() {
        khUDPCamMsgType latestImg;
        std::string     responseStr;
        
        latestImg = std::atomic_load(&m_currImg);
        if (!latestImg) return;

        callLlamaServer(m_chat.m_initialCommand, latestImg, responseStr);
        if (!responseStr.empty()) {
            translateToBaseCommands(responseStr);
        }
    }

    void yoloTimerCallback() {}
    void cmdQueueTimerCallback() {}

    std::string buildDynamicPrompt() {
        std::string prompt;
        char        buf[256];
        size_t      i;
        
        prompt = std::string(kSystemPrompt) + "\n\n";
        prompt += "[COORDINATE FRAME]\nFLU (+X Forward, +Y Left, +Z Up)\n\n";
        prompt += "[MISSION OBJECTIVE]\n" + m_chat.m_initialCommand + "\n\n";

        snprintf(buf, sizeof(buf), 
            "[VEHICLE STATE]\nAlt: %.1f cm, Vx: %.1f, Vy: %.1f, Vz: %.1f, Bat: %d%%\n\n",
            m_telemetry.altitude_cm, m_telemetry.vx_cm_s, m_telemetry.vy_cm_s, 
            m_telemetry.vz_cm_s, m_telemetry.battery_pct);
        prompt += buf;

        prompt += "[PERCEPTION DATA]\n";
        for (i = 0; i < m_targets.size(); ++i) {
            snprintf(buf, sizeof(buf), 
                "{\"label\":\"%s\", \"bbox\":[%d,%d,%d,%d], \"depth_cm\":%.1f}\n",
                m_targets[i].label, m_targets[i].bbox_xmin, m_targets[i].bbox_ymin,
                m_targets[i].bbox_xmax, m_targets[i].bbox_ymax, 
                m_targets[i].median_depth_cm);
            prompt += buf;
        }
        prompt += "\n";

        prompt += "[EXECUTED COMMAND HISTORY]\n";
        for (i = 0; i < m_chat.m_completedTasks.size(); ++i) {
            snprintf(buf, sizeof(buf), 
                "{\"status\":\"%s\", \"thought\":\"%s\", \"action_id\":%d}\n",
                m_chat.m_completedTasks[i].m_status, 
                m_chat.m_completedTasks[i].m_thought, 
                m_chat.m_completedTasks[i].m_cmd.id());
            prompt += buf;
        }

        return prompt;
    }

    void callLlamaServer(
        std::string_view       userQuery,
        khUDPCamMsgType const& latestImg,
        std::string&           responseString
    ) {
        std::string               b64Str;
        std::string               systemResponseStr;
        std::string               dynamicPrompt;
        OptionalHttpRequestFuture serverResponse;
        nlohmann::json            response_json;
        bool                      serverGood;
        cv::Mat                   frame;
        cv::Mat                   frameResized;
        std::vector<uchar>        buffer;
        int                       encodeParams[2];
        
        encodeParams[0] = cv::IMWRITE_JPEG_QUALITY;
        encodeParams[1] = 75;

        m_timer.begin();
        
        frame = cv_bridge::toCvShare(latestImg, "bgr8")->image;
        if (!frame.empty()) {
            cv::resize(frame, frameResized, cv::Size{640, 640}, 0, 0, cv::INTER_LINEAR);
            cv::imencode(".jpg", frameResized, buffer, 
                std::vector<int>(encodeParams, encodeParams + 2));
            b64Str = base64_encode(buffer.data(), buffer.size());
        }

        dynamicPrompt = buildDynamicPrompt();
        serverResponse = m_vlmClient.send(dynamicPrompt, userQuery, b64Str);

        if (serverResponse.has_value()) {
            auto res = serverResponse->get();
            serverGood = (res && res->status == 200);

            if (serverGood) {
                response_json = nlohmann::json::parse(res->body, nullptr, false);
                if (!response_json.is_discarded()) {
                    systemResponseStr = response_json["choices"][0]["message"]["content"];
                }
            }
        }

        m_timer.end();
        responseString = systemResponseStr;
    }

    void translateToBaseCommands(std::string_view flightPlan) {
        nlohmann::json plan_json;
        std::string    action;
        std::string    tmpStr;
        std::string    thoughtStr;
        GenericCommand cmd;
        ActiveTask     task;
        CommandID      id;
        CmdGo          c_go;
        CmdCurve       c_curve;
        CmdRotate      c_rot;
        CmdOrbit       c_orb;
        CmdSearch      c_srch;
        CmdReassess    c_rea;

        plan_json = nlohmann::json::parse(flightPlan, nullptr, false);
        if (plan_json.is_discarded() || !plan_json.is_array()) return;

        for (const auto& item : plan_json) {
            if (!item.contains("action")) continue;

            action = item["action"].get<std::string>();
            thoughtStr = item.value("thought", "");
            
            id = CommandID::MAX_ID;
            id = (action == "takeoff")   ? CommandID::TAKEOFF : id;
            id = (action == "land")      ? CommandID::LAND : id;
            id = (action == "stop")      ? CommandID::STOP : id;
            id = (action == "go")        ? CommandID::GO : id;
            id = (action == "curve")     ? CommandID::CURVE : id;
            id = (action == "rotate")    ? CommandID::ROTATE : id;
            id = (action == "orbit")     ? CommandID::ORBIT : id;
            id = (action == "search")    ? CommandID::SEARCH : id;
            id = (action == "re-assess") ? CommandID::REASSESS : id;

            switch (id) {
            case CommandID::TAKEOFF: cmd = GenericCommand(CmdTakeoff{}); break;
            case CommandID::LAND:    cmd = GenericCommand(CmdLand{}); break;
            case CommandID::STOP:    cmd = GenericCommand(CmdStop{}); break;
            case CommandID::GO:
                c_go = {item.value("x", 0.0f), item.value("y", 0.0f), 
                        item.value("z", 0.0f), item.value("speed", 0.0f)};
                cmd = GenericCommand(c_go);
                break;
            case CommandID::CURVE:
                c_curve = {item.value("x1", 0.0f), item.value("y1", 0.0f), 
                           item.value("z1", 0.0f), item.value("x2", 0.0f), 
                           item.value("y2", 0.0f), item.value("z2", 0.0f),
                           item.value("speed", 0.0f), 0};
                cmd = GenericCommand(c_curve);
                break;
            case CommandID::ROTATE:
                c_rot = {item.value("angle_deg", 0), 
                         (item.value("direction", "cw") == "cw"), 0};
                cmd = GenericCommand(c_rot);
                break;
            case CommandID::ORBIT:
                c_orb = {{"\0"}, item.value("radius_cm", 0.0f), 
                         item.value("angle_deg", 0.0f), item.value("speed", 0.0f), 
                         (item.value("direction", "cw") == "cw")};
                tmpStr = item.value("target_object", "");
                strncpy(c_orb.target, tmpStr.c_str(), sizeof(c_orb.target) - 1);
                cmd = GenericCommand(c_orb);
                break;
            case CommandID::SEARCH:
                c_srch = {{"\0"}, item.value("expected_search_time_sec", 0), 
                          item.value("timeout_sec", 0)};
                tmpStr = item.value("target_object", "");
                strncpy(c_srch.target, tmpStr.c_str(), sizeof(c_srch.target) - 1);
                cmd = GenericCommand(c_srch);
                break;
            case CommandID::REASSESS:
                c_rea = {{"\0"}};
                tmpStr = item.value("reason", "");
                strncpy(c_rea.reason, tmpStr.c_str(), sizeof(c_rea.reason) - 1);
                cmd = GenericCommand(c_rea);
                break;
            default: continue;
            }

            task.m_cmd   = cmd;
            task.m_state = TaskState::PENDING;
            strncpy(task.m_thought, thoughtStr.c_str(), sizeof(task.m_thought) - 1);
            m_taskQueue.enqueue(task);
        }
    }

private:
    rclcpp::CallbackGroup::SharedPtr               m_cbGroupTimers;
    rclcpp::Subscription<UDPCamMsgType>::SharedPtr m_subImg;
    rclcpp::TimerBase::SharedPtr                   m_vlmTimer;
    rclcpp::TimerBase::SharedPtr                   m_yoloTimer;
    rclcpp::TimerBase::SharedPtr                   m_cmdQueueTimer;

    spsc_queue<ActiveTask>                         m_taskQueue{3 * 20};
    ActiveTask                                     m_currTask;
    llamaClientConnection                          m_vlmClient;
    khUDPCamMsgType                                m_currImg;
    HistoryBuffer                                  m_chat;
    util2::Time::Timestamp                         m_timer;
    VehicleTelemetry                               m_telemetry;
    std::vector<TargetDetection>                   m_targets;
};