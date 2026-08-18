#pragma once
#include <atomic>
#include <chrono>
#include <cstring>
#include <cmath>
#include <string>
#include <mutex>
#include <cctype>
#include <vector>
#include <memory>
#include <future>
#include <cstdlib>
#include <fstream>       /* A2: per-run VLM prompt/response JSONL log.        */
#include <filesystem>    /* A2: ensure kVlmPromptLogDir exists at construction.*/
#include <ctime>         /* A2: per-run log filename timestamp.               */
#include <nlohmann/json.hpp>
#include <readerwriterqueue.h>
#include <util2/C/macro.h>
#include <util2/time.hpp>
#include <rclcpp/rclcpp.hpp>

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <cv_bridge/cv_bridge.hpp>
#include <base64.h>

#include "gstreamer_udp_cam_rx/rx_node_base.hpp"  /* CameraPipelineMsgType, khCameraPipelineMsgType, camera topic */
#include "fmu_node_base.hpp"
#include "drone_config.hpp"   /* DroneConfig + loadDroneConfig (ROADMAP 9.14). */
#include "llm_base.hpp"
#include "llamaclient.hpp"
#include "plan_parse.hpp"
#include "command_id.hpp"                  /* CommandID + commandIdFromAction (ROS-free). */
#include "fmu_helpers.hpp"                 /* pure helpers: lateralComponent, labelMatchesTarget. */
#include "test/fmu_test_scenarios.hpp"         /* TestScenario + parseTestScenario + scenario JSON (ROS-free). */
#include "generic_backend/active_backend.hpp"  /* ActiveBackend (FMU_BACKEND select) + BackendStatus/IOState/Odometry/Vec3 */
#include "perception_runtime.hpp"  /* PerceptionRuntime + global TargetDetection/PerceptionSnapshot (vision lib) */
#include "perception/detection_query.hpp"  /* detectionByLabel, CameraIntrinsics, TargetRelative */
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/string.hpp>      /* A2: /fmu/hud text status.        */
#include <sensor_msgs/msg/image.hpp>    /* A2: annotated-frame + depth topics.*/
#include "keyboard/keyboard_node_base.hpp"  /* kOutKeyboardRawTopic, KeyboardRawInputType (Int32MultiArray) */
#include "asr/asr_node_base.hpp"            /* kOutASRServerTranscriptionTopic, ASRTextType (std_msgs/String) */
#include "keyboard/key_codes.hpp"           /* KeyCodeEnum, KeyAction */
#include "frame/frame_convert.hpp"          /* flu_to_enu / enu_to_flu */


/* Shared-scalar access order (matches the proven baseline). */
static constexpr std::memory_order kMemOrderRelax = std::memory_order_relaxed;

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

/* FMU-owned flight state machine (platform-neutral; drives the backend via verbs). */
enum class FlightState : u8 {
    STANDBY,
    TAKEOFF,
    FLIGHT,
    LANDING
};

struct CmdTakeoff {};
struct CmdLand {};
struct CmdStop {};
struct CmdHover {};   /* persistent hold: zero velocity, never auto-completes, never wakes the VLM. */

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
    i16             bbox[4]{0, 0, 0, 0};   /* VLM-emitted [xmin,ymin,xmax,ymax] in the 640x640 image it sees; valid when xmax>xmin && ymax>ymin. Anchors ORBIT on a non-COCO target (house). */
};

struct CmdSearch {
    FixedStringType target{"\0"};
    i32             target_id{-1};          /* re-find a specific stable track id; -1 = open label search. */
    i32             expected_time{0};
    i32             timeout{0};
    i32             start_heading_deg{0};   /* first sweep heading, relative to current facing (deg). */
    bool            cw_or_ccw{false};       /* fan direction: true=cw, false=ccw. The VLM sets it by context. */
    u8              size{kSearchDefaultSizeIdx};  /* index into kSearchSizePresets: 0=small 1=medium 2=large. */
};

struct CmdReassess {
    FixedStringType reason{"\0"};
};

/* Command definition only (ROADMAP 3.6 / spec 2026-08-05-visual-servoing-approach-design.md §4c).
   No control-law branch yet -- that is block 5.1 (detectionByLabel + the yaw-center/range-decel
   servo). Until then this auto-completes via activateTask's default case, same as ORBIT/SEARCH. */
struct CmdApproach {
    FixedStringType target{"\0"};   /* label fallback. */
    i32             target_id{-1};   /* stable track id from [PERCEPTION] (preferred). */
    f32             speed{0.0f};
    i16             bbox[4]{0, 0, 0, 0};   /* VLM-emitted [xmin,ymin,xmax,ymax] in the 640x640 image; anchors APPROACH on a non-COCO target (house/window) YOLO cannot box. */
};

/* FOLLOW (spec agent1): position-free visual servo that holds a standoff on a VLM-chosen
   target and keeps it centered. target_index selects the detection from the [PERCEPTION] list;
   it is resolved to a label + bbox center once at activation, then tracked by nearest-centroid. */
struct CmdFollow {
    i32 target_index{-1};   /* array position fallback (unstable across frames). */
    i32 target_id{-1};      /* stable track id from [PERCEPTION] (preferred).             */
    i32 standoff_cm{0};
    i32 speed{0};
};

static_assert(sizeof(CmdOrbit)    <= CACHE_LINE_BYTES - sizeof(u64), "CmdOrbit exceeds GenericCommand payload");
static_assert(sizeof(CmdApproach) <= CACHE_LINE_BYTES - sizeof(u64), "CmdApproach exceeds GenericCommand payload");

struct alignpk(CACHE_LINE_BYTES) GenericCommand {
    union {
        struct alignpk(CACHE_LINE_BYTES) {
            u8 m_rawId;
            u8 m_padToMultipleForCmd[sizeof(u64) - sizeof(u8)];
            u8 m_cmdBytes[CACHE_LINE_BYTES - sizeof(u64)];
        } m_rawBytes;

        struct {
            CommandID m_id;
            u8        m_reserved[sizeof(uint64_t) - sizeof(u8)];
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
                CmdApproach m_approach;
                CmdFollow   m_follow;
                CmdHover    m_hover;
            };
        } m_extractCmd;
    };

    GenericCommand() : m_rawBytes{__scast(u8, CommandID::MAX_ID), {0}, {0}} {}
    GenericCommand(CmdTakeoff) : m_rawBytes{__scast(u8, CommandID::TAKEOFF), {0}, {0}} {}
    GenericCommand(CmdLand)    : m_rawBytes{__scast(u8, CommandID::LAND), {0}, {0}} {}
    GenericCommand(CmdStop)    : m_rawBytes{__scast(u8, CommandID::STOP), {0}, {0}} {}
    GenericCommand(CmdHover)   : m_rawBytes{__scast(u8, CommandID::HOVER), {0}, {0}} {}

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
    GenericCommand(CmdApproach const& cmd) : m_rawBytes{__scast(u8, CommandID::APPROACH), {0}, {0}} {
        memcpy(&m_rawBytes.m_cmdBytes, &cmd, sizeof(CmdApproach));
    }
    GenericCommand(CmdFollow const& cmd) : m_rawBytes{__scast(u8, CommandID::FOLLOW), {0}, {0}} {
        memcpy(&m_rawBytes.m_cmdBytes, &cmd, sizeof(CmdFollow));
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

struct HistoryBuffer {
    std::string             m_initialCommand;
    std::vector<ActiveTask> m_completedTasks;
};

class FlightManagementUnitNode : public rclcpp::Node {
public:
    FlightManagementUnitNode() : rclcpp::Node("high_level_navigation_node") {
        rclcpp::SubscriptionOptions subOpts;

        m_cbGroup = this->create_callback_group(rclcpp::CallbackGroupType::Reentrant);
        subOpts.callback_group = m_cbGroup;

        m_taskQueue = std::make_unique<spsc_queue<ActiveTask>>(3 * kControlLoopRateHz);

        /* Runtime per-drone tuning (ROADMAP 9.14). DRONE_CONFIG names a profile file;
           this getenv is the sanctioned runtime-config hook -- the codebase's usual
           zero-getenv rule does not apply to this one selector. Unset -> the all-defaults
           struct, which equals the compiled constexpr (SITL scale), so behavior is
           unchanged. Set-but-missing/unreadable/unparsable -> FATAL + abort: an explicitly
           selected profile must never silently fall back to the wrong-scale defaults (the
           apartment-ceiling crash this loader exists to prevent). Load once, then read. */
        {
            const char* cfgPath = std::getenv("DRONE_CONFIG");
            if (cfgPath && cfgPath[0] != '\0') {
                bool cfgOk = false;
                m_cfg      = loadDroneConfig(cfgPath, cfgOk);
                if (!cfgOk) {
                    RCLCPP_FATAL(this->get_logger(),
                        "[FMU_NODE_FATAL] DRONE_CONFIG='%s' selected but missing/unreadable/"
                        "unparsable -- refusing to fly on fallback constants. Aborting.", cfgPath);
                    std::abort();
                }
                mb_cfgActive = true;
                RCLCPP_INFO(this->get_logger(),
                    "[FMU_NODE_DEBUG] DRONE_CONFIG loaded from %s (takeoffAlt=%.2f climbVel=%.2f "
                    "landVel=%.2f approachStandoff=%.2f searchSpeed=%.2f).",
                    cfgPath, m_cfg.takeoffTargetAltEnu, m_cfg.takeoffClimbVelEnu,
                    m_cfg.landDescendVelEnu, m_cfg.approachStandoffM, m_cfg.searchSweepSpeedMps);
            }
        }

        m_subImg = this->create_subscription<CameraPipelineMsgType>(
            kOutCameraPipelineRawFrameTopic, 10,
            std::bind(&FlightManagementUnitNode::imgCallback, this, std::placeholders::_1),
            subOpts
        );

        /* Operator manual-override toggle (std_msgs/Bool) + the raw keylog stream
           (movement keys act only while override is engaged). ARCH 11. */
        m_subOverride = this->create_subscription<std_msgs::msg::Bool>(
            kFmuOverrideTopic, 10,
            std::bind(&FlightManagementUnitNode::overrideCallback, this, std::placeholders::_1),
            subOpts
        );
        m_subKey = this->create_subscription<KeyboardRawInputType>(
            kOutKeyboardRawTopic, 10,
            std::bind(&FlightManagementUnitNode::keyCallback, this, std::placeholders::_1),
            subOpts
        );

        /* Voice objective (push-to-talk ASR -> std_msgs/String). Spoken on the ground it
           launches the mission; spoken in flight it re-tasks the VLM. See asrCallback. */
        m_subAsr = this->create_subscription<ASRTextType>(
            kOutASRServerTranscriptionTopic, 10,
            std::bind(&FlightManagementUnitNode::asrCallback, this, std::placeholders::_1),
            subOpts
        );

        /* All platform wire I/O lives in the backend. make_active_backend hides
           the per-backend ctor asymmetry (PX4 needs this Node + callback group;
           Tello, being ROS-free, ignores them) behind one uniform call, so the
           FMU stays non-templated and no ROS leaks into a ROS-free backend. */
        m_backend = make_active_backend(this, m_cbGroup);
        m_backend->start();

        initDashboardDiagnostics();   /* A2 dashboard pipeline, iff FMU_OBSERVABILITY is set. */

        /* Two-rate perception (ARCH sec 9): PerceptionRuntime owns its own seg/depth
           threads and publishes an atomic PerceptionSnapshot; buildDynamicPrompt()
           reads it. Thread counts are capped (fmu_node_base.hpp) so ORT cannot starve
           this control loop. The two trailing callbacks are A2 sinks: an already-drawn
           annotated frame and the raw depth mat, published on the topics above. */
        /* Image sinks only when observability is on -- empty otherwise, so the seg/depth
           loops skip the annotate-draw and colormap (their guards are `if (sink)`). */
        std::function<void(cv::Mat const&)> annSink, depthSink;
        if (mb_observability) {
            annSink   = [this](cv::Mat const& a) { publishAnnotatedFrame(a); };
            depthSink = [this](cv::Mat const& d) { publishDepthColormap(d); };
        }
        m_perception = std::make_unique<PerceptionRuntime>(
            kVisionSegModelPath, kVisionDepthModelPath,
            kVisionSegThreads, kVisionDepthThreads,
            kVisionSegLoopMs, kVisionDepthLoopMs,
            [this]() { return std::atomic_load(&m_currImg); },
            std::move(annSink), std::move(depthSink));
        if (!m_perception->ready()) {
            RCLCPP_FATAL(this->get_logger(),
                "[FMU_NODE_FATAL] vision model(s) failed to load -- seg=%s depth=%s. "
                "Path missing/unreadable; aborting instead of flying blind (zero detections).",
                kVisionSegModelPath, kVisionDepthModelPath);
            std::abort();   /* no exceptions in this codebase -- fail fast on a fatal misconfig. */
        }
        m_perception->start();

        m_controlTimer = this->create_wall_timer(
            std::chrono::milliseconds{kControlLoopPeriodMs},
            std::bind(&FlightManagementUnitNode::controlLoop, this), m_cbGroup);

        /* max_tokens is a CEILING on generation, not a target: the model still stops at EOS on a
           short reply, so raising it costs nothing there -- it only stops a long "thought" from
           being clipped mid-sentence (768 was clipping them). 1024 gives headroom. The old 32768
           let a no-EOS runaway ramble for minutes and wedge the planner. temp 0.2 matches the
           server and reduces degenerate loops. (A per-call budget -- e.g. a smaller cap on reassess
           cycles -- is a possible latency tweak, deferred: a low reassess cap re-truncates thoughts,
           and there is no initial-vs-reassess signal plumbed here to branch on.) */
        m_vlmClient.create(kSystemPrompt, 0.2f, 1024);
        m_chat.m_completedTasks.reserve(kDefaultPromptHistorySize);

        RCLCPP_INFO(this->get_logger(),
            "[FMU_NODE_DEBUG] Flight Management Unit Active (control %uHz, backend owns wire).",
            kControlLoopRateHz);
    }

    ~FlightManagementUnitNode() override {
        m_missionActive.store(false, std::memory_order_release);
        if (m_planFuture.valid()) m_planFuture.wait();  /* no VLM call touching a dead client. */
        m_perception->stop();
        m_vlmClient.destroy();
    }

    /* Bootstrap: arm the mission. test != None pre-fills the queue with a scripted scenario and
       skips the VLM (see runTestScenario + test/fmu_test_scenarios.hpp); None is a normal VLM-driven run. */
    void start(std::string_view objective, TestScenario test = TestScenario::None) {
        m_chat.m_initialCommand = objective;
        publishVlmContext();   /* surface the objective on the dashboard right away. */
        m_missionStartUs = nowUs();
        /* Only VLM-driven runs wake the planner; canned runs pre-fill the queue and
           must NOT poll a (possibly absent) VLM server after they drain. */
        bool scenarioRun = (test != TestScenario::None);
        m_missionActive.store(!scenarioRun, std::memory_order_release);
        runTestScenario(test);
        RCLCPP_INFO(this->get_logger(),
            "[FMU_NODE_DEBUG] Mission started (test=%d). queued~=%zu. objective: %.*s",
            __scast(int, test), m_taskQueue->size_approx(),
            __scast(int, objective.size()), objective.data()
        );
        return;
    }

private:
    template <typename T>
    using spsc_queue = moodycamel::ReaderWriterQueue<T, sizeof(T)>;

    /* ---- Subscriptions --------------------------------------------------- */
    void imgCallback(khCameraPipelineMsgType msg) {
        std::atomic_store(&m_currImg, msg);
        u64 c = m_frameCount.fetch_add(1, kMemOrderRelax) + 1;
        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 2000,
            "[FMU_NODE_DEBUG] camera frame rx: %ux%u encoding=%s count=%lu",
            msg->width, msg->height, msg->encoding.c_str(), (unsigned long)c);
    }

    /* Voice command intake. The push-to-talk ASR node publishes each transcript as a
       std_msgs/String on /asr_server/transcribe. This callback runs on a separate executor
       thread, so to keep raiseInterrupt()/flight-state mutation control-thread-only it ONLY
       trims + posts the transcript; controlLoop drains it (m_asrPending) and runs
       handleAsrCommand() on the control thread. Read-back is logged here so a mishear is
       caught before the drone acts (token-probability confidence does NOT track correctness
       -- the operator's ear is the safety net, not an automatic gate). */
    void asrCallback(const ASRTextType::SharedPtr msg) {
        std::string text = msg->data;
        size_t b = text.find_first_not_of(" \t\r\n");
        if (b == std::string::npos) return;            /* silence / blank capture -- ignore. */
        size_t e = text.find_last_not_of(" \t\r\n");
        text = text.substr(b, e - b + 1);

        RCLCPP_WARN(this->get_logger(), "[ASR] heard: \"%s\"", text.c_str());
        {
            std::lock_guard<std::mutex> lk(m_asrMtx);
            m_asrPendingText = text;
        }
        m_asrPending.store(true, std::memory_order_release);   /* control loop picks it up. */
    }

    /* Control-thread handler for a posted ASR transcript. Returns true if it took a terminal
       action that should yield the current control tick (emergency land/stop), false to let
       the loop continue (mission launch / VLM re-task). EMERGENCY callouts are matched as
       short imperatives and act deterministically -- the VLM is NOT in the loop, so spoken
       "land"/"stop" is instant. A full sentence ("find the house and land near it") is NOT an
       emergency; it routes to the VLM as a user_command interrupt. */
    bool handleAsrCommand(const std::string& text) {
        std::string low;
        low.reserve(text.size());
        for (char c : text) low += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        while (!low.empty() && (low.back() == ' ' || low.back() == '.' ||
                                low.back() == '!' || low.back() == '?')) low.pop_back();
        auto endsWith = [&](const char* suf) {
            std::string t = suf;
            return low.size() >= t.size() && low.compare(low.size() - t.size(), t.size(), t) == 0;
        };
        if (endsWith(" now")) { low.resize(low.size() - 4);
            while (!low.empty() && low.back() == ' ') low.pop_back(); }

        FlightState st = m_flightState.load(kMemOrderRelax);

        /* EMERGENCY LAND (deterministic, VLM bypassed) -- same land-in-place primitive the
           battery failsafe uses: drop the plan, stop soliciting, hand the control loop LANDING. */
        if (low == "land" || low == "abort" || low == "emergency" || low == "mayday" ||
            low == "come down" || low == "get down" || low == "descend") {
            if (st == FlightState::STANDBY) {
                RCLCPP_WARN(this->get_logger(), "[ASR] EMERGENCY 'land' ignored -- already grounded.");
                return false;
            }
            RCLCPP_WARN(this->get_logger(), "[ASR] EMERGENCY LAND (deterministic, VLM bypassed).");
            emergencyLandNow();
            return true;
        }
        /* EMERGENCY STOP / HOLD (deterministic hover, VLM bypassed). */
        if (low == "stop" || low == "halt" || low == "freeze" || low == "hold" ||
            low == "hover" || low == "hold position" || low == "stop moving") {
            if (st == FlightState::STANDBY) return false;   /* nothing to stop on the ground. */
            RCLCPP_WARN(this->get_logger(), "[ASR] EMERGENCY STOP -> hover (deterministic, VLM bypassed).");
            emergencyHoldNow();
            return true;
        }

        /* NON-EMERGENCY. Grounded -> launch the mission from the spoken objective. */
        if (st == FlightState::STANDBY) {
            RCLCPP_WARN(this->get_logger(), "[ASR] launching mission from spoken objective.");
            start(text);
            return false;
        }
        /* Airborne -> A3 user_command interrupt: hover now, surface the words in the next
           [USER] prompt block, let the VLM reassess against the running objective. */
        RCLCPP_WARN(this->get_logger(), "[ASR] in-flight command -> user_command interrupt (VLM reassess).");
        m_userCommandText = text;
        raiseInterrupt("user_command");
        return false;
    }

    /* Deterministic emergency land-in-place (mirrors the battery-failsafe land path): drop the
       queued plan, clear active/stash, stop soliciting VLM plans, hand the control loop LANDING. */
    void emergencyLandNow() {
        ActiveTask stale;
        while (m_taskQueue->try_dequeue(stale)) { }
        m_hasActive            = false;
        m_hasStashed           = false;
        m_settleTicksRemaining = 0;
        m_missionActive.store(false, std::memory_order_release);
        m_flightState.store(FlightState::LANDING, kMemOrderRelax);
    }

    /* Deterministic emergency hover-hold: drop the plan, stop soliciting, stream zero velocity.
       The backend repeats the last setpoint, so the drone holds until the next command. */
    void emergencyHoldNow() {
        ActiveTask stale;
        while (m_taskQueue->try_dequeue(stale)) { }
        m_hasActive            = false;
        m_hasStashed           = false;
        m_settleTicksRemaining = 0;
        m_missionActive.store(false, std::memory_order_release);
        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
    }

    /* ---- APPROACH helpers ------------------------------------------------- */
    /* Motion-gate (spec 1 6.4): "reached" is only trusted when the drone is not in a collision
       transient. A real impact spikes yaw-rate + vertical velocity while the range still reads
       plausible off the impact frame (SITL: yawrate 6.9, vertVel -1.75, alt 0.99->0.02 in ~1s).
       Not nominal -> the APPROACH branch treats "reached" as an impact and interrupts. */
    bool approachMotionNominal(Odometry const& od) const {
        if (m_forceApproachImpact) return false;   /* test-only forced impact (--scenario-approach-impact). */
        return std::fabs(od.yawrate) < kApproachNominalYawrate
            && std::fabs(od.vel.z)  < kApproachNominalVertVel;
    }

    /* Projects m_cannedApproachTargetEnu (fixed at APPROACH activation, see activateTask)
       through the drone's live pose into a synthetic PerceptionSnapshot and publishes it via
       PerceptionRuntime::injectSynthetic. Forward-projection inverse of detectionByLabel's
       back-projection: world point -> body-FLU vector -> pixel. Not visible (behind the
       camera or outside the frame) -> publish a valid-but-empty snapshot, exactly what a
       real camera reports when nothing matches. */
    /* Freeze a world (ENU) anchor from a VLM-emitted bbox -- the enabler that lets APPROACH/ORBIT
       drive toward a non-COCO target (house/window) YOLO never boxes. The VLM emits the bbox in the
       640x640 image it is shown (kVlmImageSide); scale to native camera px, median the dense depth
       over it (YOLO-independent), then pinhole back-project through the live pose. This is the exact
       inverse of updateCannedApproachRig's forward projection. Returns false when the bbox is
       absent/degenerate or no depth is measurable there -- the caller then keeps its label path. */
    bool bboxRangeDir(const i16 bbox[4], Odometry const& od, f32& outRangeM, Vec3& outDirEnu) const {
        if (!(bbox[2] > bbox[0] && bbox[3] > bbox[1])) return false;   /* absent / degenerate. */
        f32 sx = static_cast<f32>(kApproachCamera.width)  / static_cast<f32>(kVlmImageSide);
        f32 sy = static_cast<f32>(kApproachCamera.height) / static_cast<f32>(kVlmImageSide);
        cv::Rect rect(cv::Point(static_cast<int>(bbox[0] * sx), static_cast<int>(bbox[1] * sy)),
                      cv::Point(static_cast<int>(bbox[2] * sx), static_cast<int>(bbox[3] * sy)));
        f32 rangeM = m_perception->medianDepthCmInRect(rect) / 100.0f;
        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 500,
            "[FMU_NODE_DIAGNOSTICS] bboxToEnuAnchor rect=(%d,%d,%d,%d) rangeM=%.2f freeDepth=%.2f",
            rect.x, rect.y, rect.width, rect.height, rangeM, m_perception->nearestFreeDepthM());
        if (rangeM <= 0.0f) return false;
        f32  uc   = 0.5f * static_cast<f32>(rect.x + rect.x + rect.width);
        f32  vc   = 0.5f * static_cast<f32>(rect.y + rect.y + rect.height);
        f32  camX = (uc - kApproachCamera.cx) / kApproachCamera.fx;   /* = -relFlu.y / relFlu.x */
        f32  camY = (vc - kApproachCamera.cy) / kApproachCamera.fy;   /* = -relFlu.z / relFlu.x */
        Vec3 dirFlu = { 1.0f, -camX, -camY };
        f32  nrm    = std::sqrt(dirFlu.x * dirFlu.x + dirFlu.y * dirFlu.y + dirFlu.z * dirFlu.z);
        dirFlu = { dirFlu.x / nrm, dirFlu.y / nrm, dirFlu.z / nrm };
        outDirEnu  = flu_to_enu(dirFlu, od.yaw);
        outRangeM  = rangeM;
        return true;
    }

    bool bboxToEnuAnchor(const i16 bbox[4], Odometry const& od, Vec3& outEnu) const {
        f32 r; Vec3 d;
        if (!bboxRangeDir(bbox, od, r, d)) return false;
        outEnu = { od.pos.x + d.x * r, od.pos.y + d.y * r, od.pos.z + d.z * r };
        return true;
    }

    void updateCannedApproachRig(Odometry const& od) {
        Vec3               relEnu, relFlu;
        f32                u, v, camX, camY;
        PerceptionSnapshot synth;
        u64                now;

        now = nowUs();
        synth.host_stamp_us = now;
        synth.valid = true;   /* the "camera" is alive; count==0 means "nothing detected". */

        if ((now - m_cannedApproachActivateUs) > kCannedApproachRigKillAfterUs) {
            m_perception->injectSynthetic(synth);   /* rig "kill": simulate the target leaving frame. */
            return;
        }

        relEnu = { m_cannedApproachTargetEnu.x - od.pos.x,
                   m_cannedApproachTargetEnu.y - od.pos.y,
                   m_cannedApproachTargetEnu.z - od.pos.z };
        relFlu = enu_to_flu(relEnu, od.yaw);

        if (relFlu.x <= 0.05f) {   /* behind (or at) the camera plane -- not visible. */
            m_perception->injectSynthetic(synth);
            return;
        }

        camX = -relFlu.y / relFlu.x;
        camY = -relFlu.z / relFlu.x;
        u    = kApproachCamera.cx + kApproachCamera.fx * camX;
        v    = kApproachCamera.cy + kApproachCamera.fy * camY;

        if (u < 0.0f || u > static_cast<f32>(kApproachCamera.width) ||
            v < 0.0f || v > static_cast<f32>(kApproachCamera.height)) {
            m_perception->injectSynthetic(synth);   /* projected outside the frame. */
            return;
        }

        synth.count = 1;
        std::snprintf(synth.dets[0].label, sizeof(FixedStringType), "%s", m_cannedApproachLabel);
        synth.dets[0].bbox_xmin = static_cast<i32>(u - 20.0f);   /* synthetic 40x40px bbox.   */
        synth.dets[0].bbox_ymin = static_cast<i32>(v - 20.0f);
        synth.dets[0].bbox_xmax = static_cast<i32>(u + 20.0f);
        synth.dets[0].bbox_ymax = static_cast<i32>(v + 20.0f);
        synth.dets[0].confidence = 1.0f;
        synth.dets[0].median_depth_cm =
            std::sqrt(relFlu.x * relFlu.x + relFlu.y * relFlu.y + relFlu.z * relFlu.z) * 100.0f;
        m_perception->injectSynthetic(synth);
    }

    /* ---- Per-tick control laws (one per movement command) ---------------------------------------
       controlLoop() dispatches on the active CommandID and calls exactly ONE of these each tick
       (20 Hz). Each is behaviour-isolated: it reads the tick's Odometry, drives the backend velocity,
       and owns its own scratch -- no cross-command shared locals. DEFINED out-of-line in fmu_node.cpp
       so this header stays declarations. Extracted incrementally out of controlLoop; behaviour is
       verified unchanged in Gazebo per command. */
    void stepHover();

    /* ---- 20Hz control + deterministic completion ------------------------- */
    /* Pure planner side: reads an Odometry snapshot + IOState, issues verbs.
       Frame is canonical ENU (East, North, Up+); backend converts NED at wire. */
    void controlLoop() {
        Odometry    od;
        f32         n, e, d, dx, dy, dz, dist, sp, vN, vE, vD;
        f32         alN, alE, alD, along, remain, crN, crE, crD, mag;
        ActiveTask  next;
        FlightState st;
        CommandID   id;
        CmdApproach appr;
        CmdFollow   fol;
        TargetRelative tr;
        std::shared_ptr<PerceptionSnapshot> snap;
        Vec3        velEnu, aimFlu, fwdDir, lat;
        f32         speedCeil, spF, yawRate, vUp, magV, appTrav, appRem;
        f32         boundSpeed, boundTrig, nearestM, loomFrac, freeM;
        u64         tnow, fdStamp;
        CmdOrbit    orb;
        CmdSearch   srch;
        TargetDetection const* hit;
        f32         errX, oDist, oRadErr, oAngle, oPrevAngle, oDesYaw, oMedRange;
        Vec3        oToDrone, oRadial, oTangent, oDirEnu;
        f32         distStart, headErr, altErr;
        u32         di;

        od = m_backend->odometry();
        n  = od.pos.x;
        e  = od.pos.y;
        d  = od.pos.z;
        st = m_flightState.load(kMemOrderRelax);

        /* Battery failsafe = ultimate safety net: pre-empts the plan AND the pilot. */
        if (batteryFailsafeTick()) return;

        /* Voice command intake (control-thread): drain a posted ASR transcript and act on it.
           Placed right after the battery failsafe (which outranks all) and BEFORE the manual-
           override gate, so an emergency "land"/"stop" fires even while override is held. An
           emergency yields this tick (LANDING/hover already commanded); a launch/re-task falls
           through to the normal loop. */
        if (m_asrPending.exchange(false, std::memory_order_acquire)) {
            std::string asrTxt;
            { std::lock_guard<std::mutex> lk(m_asrMtx); asrTxt.swap(m_asrPendingText); }
            if (handleAsrCommand(asrTxt)) return;
        }

        /* Manual operator override: pilot flies (body-FLU keys -> world ENU); autonomy
           paused. Disabled once a battery failsafe has latched (failsafe wins). */
        if (m_manualOverride.load(kMemOrderRelax) && !mb_batteryReturn && !mb_batteryLand) {
            Vec3 manEnu = flu_to_enu(
                Vec3{ m_manualFwd.load(kMemOrderRelax),
                      m_manualLeft.load(kMemOrderRelax),
                      m_manualUp.load(kMemOrderRelax) }, od.yaw);
            m_backend->set_velocity(manEnu, m_manualYaw.load(kMemOrderRelax));
            return;
        }

        /* HIGH-verbosity heartbeat (every 500ms) — one glance shows the whole rig. */
        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 500,
            "[FMU_NODE_DIAGNOSTICS] fs=%d io=%d posENU=(%.2f,%.2f,%.2f) measVelENU=(%.2f,%.2f,%.2f) yaw=%.2f yawrate=%.2f active=%d qsize=%zu",
            __scast(int, st), __scast(int, m_backend->state()),
            n, e, d, od.vel.x, od.vel.y, od.vel.z, od.yaw, od.yawrate,
            __scast(int, m_hasActive), m_taskQueue->size_approx());

        /* A2 readability HUD (additive, ~5Hz): one clean [FMU_HUD] line + /fmu/hud topic
           so a human/Foxglove text panel sees STATE/ALT/TASK/VLM/DET/VEL/BATT at a glance
           instead of parsing the ~60 debug lines. Reads only what is already in scope here;
           does NOT touch any existing debug line. Throttled by a plain timestamp gate. */
        if (mb_observability && (nowUs() - m_lastHudUs) >= kHudThrottleUs) {
            m_lastHudUs = nowUs();
            publishHud(st, d, od);
        }
        /* A2: ~1 Hz pipeline-rate report on /fmu/rates so the dashboard can show, at a glance,
           perception refresh (seg/depth loop Hz) vs the throttled publish Hz. Counts are deltas
           over the window; first sample reports 0 (no prior baseline). */
        if (mb_observability && m_pubRates && (nowUs() - m_lastRatesUs) >= 1000000ULL) {
            f32 sec   = (nowUs() - m_lastRatesUs) / 1.0e6f;
            u64 segIt = m_perception ? m_perception->segIters()   : 0;
            u64 depIt = m_perception ? m_perception->depthIters() : 0;
            nlohmann::json j;
            j["seg_hz"]       = m_lastSegIters   ? (segIt - m_lastSegIters)   / sec : 0.0f;
            j["depth_hz"]     = m_lastDepthIters ? (depIt - m_lastDepthIters) / sec : 0.0f;
            j["ann_pub_hz"]   = m_annPubs.exchange(0, kMemOrderRelax)   / sec;
            j["depth_pub_hz"] = m_depthPubs.exchange(0, kMemOrderRelax) / sec;
            j["hud_pub_hz"]   = m_hudPubs.exchange(0, kMemOrderRelax)   / sec;
            std_msgs::msg::String rmsg; rmsg.data = j.dump();
            m_pubRates->publish(rmsg);
            m_lastSegIters = segIt; m_lastDepthIters = depIt; m_lastRatesUs = nowUs();
        }

        /* Airborne command-storm (spec-3): once we've been in FLIGHT ~5s, inject the flood
           from a producer-role async (mirrors the VLM's std::async path) so the SPSC contract
           holds -- the control thread only LAUNCHES it here, it never enqueues. */
        if (m_floodArmed && !m_floodFired && st == FlightState::FLIGHT) {
            if (m_floodAtUs == 0)             m_floodAtUs = nowUs() + 5ULL * 1000000ULL;
            else if (nowUs() >= m_floodAtUs) {
                m_floodFired  = true;
                m_floodFuture = std::async(std::launch::async, [this]() { translateToBaseCommands(scenarioQueueOverflowJson()); });
            }
        }

        /* Test-only battery fault injection: once ~15s into FLIGHT (drone is out ~6m), force the
           scripted low reading so the failsafe law fires deterministically, far from home. */
        if (m_batForceArmed && !m_batForceFired && st == FlightState::FLIGHT) {
            if (m_batForceAtUs == 0)             m_batForceAtUs = nowUs() + 15ULL * 1000000ULL;
            else if (nowUs() >= m_batForceAtUs) {
                m_batForceFired = true;
                m_batteryForce.store(m_batForceValue, kMemOrderRelax);
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] TEST battery fault injected -> forcing %d%% (real was %d%%).",
                    m_batForceValue, m_backend->battery_pct());
            }
        }

        if (st == FlightState::TAKEOFF) {
            m_backend->set_velocity(Vec3{0.0f, 0.0f, m_cfg.takeoffClimbVelEnu}, 0.0f);  /* stream the climb (Up+) */
            if (m_backend->state() == IOState::FAULT) {
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] TAKEOFF faulted (backend IOState=FAULT). Aborting task.");
                m_flightState.store(FlightState::STANDBY, kMemOrderRelax);
                completeCurrent("takeoff_faulted");
                return;
            }
            if (d >= m_cfg.takeoffTargetAltEnu) {
                RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] TAKEOFF->FLIGHT altENU=%.2f", d);
                m_flightState.store(FlightState::FLIGHT, kMemOrderRelax);
                completeCurrent("takeoff_ok");
            }
            return;
        }

        if (st == FlightState::LANDING) {
            /* slow-descent from full-speed to slow-touchdown as altitude nears the ground */
            f32 vLand = m_cfg.landDescendVelEnu;
            if (d < m_cfg.flareStartAltEnu) {
                f32 t = (d - m_cfg.groundContactEnu) / (m_cfg.flareStartAltEnu - m_cfg.groundContactEnu);
                if (t < 0.0f) t = 0.0f; else if (t > 1.0f) t = 1.0f;  /* 1 at flare start, 0 at contact */
                vLand = m_cfg.flareTouchdownVelEnu + t * t * (m_cfg.landDescendVelEnu - m_cfg.flareTouchdownVelEnu);  /* t*t: quadratic ease -- brakes harder near the ground than the old linear taper */
            }
            /* stream vLand so the flare taper is verifiable from the log (spec-4 Part B). */
            RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                "[FMU_NODE_DIAGNOSTICS] LAND altENU=%.2f vLand=%.3f", d, vLand);
            m_backend->set_velocity(Vec3{0.0f, 0.0f, vLand}, 0.0f);  /* stream the (flared) descent (Down) */
            if (d <= m_cfg.groundContactEnu) {
                m_backend->force_disarm();
                RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] LANDING->STANDBY altENU=%.2f (force_disarm)", d);
                m_flightState.store(FlightState::STANDBY, kMemOrderRelax);
                completeCurrent("land_ok");
                /* LAND is the mission's terminal intent: stop waking the VLM. Anything
                   already queued still runs; we just stop soliciting NEW plans, so the
                   server goes idle instead of re-planning a landed, disarmed drone. */
                m_missionActive.store(false, std::memory_order_release);
                RCLCPP_INFO(this->get_logger(),
                    "[FMU_NODE_DEBUG] Mission complete after LAND; VLM planning halted.");
            }
            return;
        }

        /* Lost-flight guard (safety): we believe we are airborne, but the backend has left FLIGHT
           -- an unexpected disarm/failsafe (the PX4 backend surfaces it as FAULT), not a commanded
           land (that runs in the LANDING branch above, which returns before here). Streaming velocity
           to a vehicle that is no longer flying is exactly the desync that stranded the FMU at
           fs=FLIGHT while PX4 was disarmed. Stop, reconcile to STANDBY, abort the active task, and
           halt the mission so the VLM is not re-woken to fly a dead/crashed drone. Tello never
           reports FAULT, so this cannot false-trip there -- its own ~15s keepalive auto-land covers it. */
        if (st == FlightState::FLIGHT && m_backend->state() != IOState::FLIGHT) {
            m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
            m_flightState.store(FlightState::STANDBY, kMemOrderRelax);
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] backend left FLIGHT (io=%d) while FMU airborne -> stop, reconcile STANDBY, abort task.",
                __scast(int, m_backend->state()));
            if (m_hasActive) completeCurrent("backend_lost_flight");
            m_missionActive.store(false, std::memory_order_release);
            return;
        }

        /* Test-only obstacle window (--scenario-boundary / --scenario-storm): once airborne, open a
           short burst window; while it is open the emergency boundary below forces a close reading
           (race-free, bypassing perception) so it trips deterministically with no real obstacle in
           the world. The window then closes so the hold path can reach maybePlan and wake the VLM
           (the storm test needs the escalated reassess prompt built). */
        if (m_obstacleArmed && !m_obstacleFired && st == FlightState::FLIGHT) {
            m_obstacleUntilUs = nowUs() + 1500ULL * 1000ULL;   /* ~1.5s burst: >> kInterruptMaxRetries. */
            m_obstacleFired   = true;
        }

        /* Emergency boundary (spec 1 6.1): velocity-scaled standoff, FLIGHT only so it can't
           trip while grounded/taking off/landing. Depth is slow and can freeze on this CPU, so a
           snapshot older than the age cap is treated as unknown -- never a false trip on stale
           depth. nearestDepthM() returns 0 for "nothing measurable", which is not an obstacle. */
        if (st == FlightState::FLIGHT) {
            boundSpeed = std::sqrt(od.vel.x * od.vel.x + od.vel.y * od.vel.y + od.vel.z * od.vel.z);
            boundTrig  = m_cfg.boundaryBaseM + m_cfg.boundaryVelScale * boundSpeed;
            loomFrac   = 0.0f;
            freeM      = 0.0f;
            if (m_obstacleArmed && m_obstacleFired && nowUs() < m_obstacleUntilUs) {
                /* Test-only forced obstacle (--scenario-boundary / --scenario-storm): bypass the
                   perception snapshot so the trip is deterministic and cannot be lost to a race
                   with live YOLO in a populated world. 0.4 m is inside kBoundaryBaseM (0.6). */
                nearestM = 0.4f;
            } else {
                snap = m_perception->snapshot();
                if (snap && snap->valid
                    && (nowUs() - snap->host_stamp_us) <= __scast(u64, kBoundaryMaxSnapshotAgeMs) * 1000ULL) {
                    nearestM = nearestDepthM(*snap);
                    loomFrac = maxBboxFillFrac(*snap, kApproachCamera);
                } else {
                    nearestM = 0.0f;
                }
                /* Free-space depth over the whole depth map -- catches walls and any geometry YOLO
                   does not box. Takes over when it reads closer than the detection depth (or when
                   there is no detection at all). Stale readings are ignored, same as the snapshot. */
                fdStamp = 0;
                freeM   = m_perception->nearestFreeDepthM(&fdStamp);
                if (freeM > 0.0f
                    && (nowUs() - fdStamp) <= __scast(u64, kBoundaryMaxSnapshotAgeMs) * 1000ULL
                    && (nearestM == 0.0f || freeM < nearestM)) {
                    nearestM = freeM;
                }
            }
            /* Stream depth + looming while something is measurable, so log inspection can see why
               the boundary did or did not trip. Skipped when nothing is in view (nearest=0 and no
               fill) so a long hover does not flood the pane and flush earlier lines out of the tmux
               scrollback -- which is what buried the interrupt-storm burst and the override toggle. */
            if ((nearestM > 0.0f && nearestM < kBoundaryDiagRangeM) || loomFrac > 0.0f) {
                RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                    "[FMU_NODE_DIAGNOSTICS] BOUNDARY nearest=%.2f free=%.2f trig=%.2f loomFill=%.2f/%.2f speed=%.2f",
                    nearestM, freeM, boundTrig, loomFrac, kBoundaryLoomFillFrac, boundSpeed);
            }
            if (nearestM > 0.0f && nearestM < boundTrig) {
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] BOUNDARY nearest=%.2f < trig=%.2f (speed=%.2f) -> interrupt.",
                    nearestM, boundTrig, boundSpeed);
                raiseInterrupt("emergency_boundary");
                return;
            }
            /* Depth-independent backstop: a detection filling the frame is imminent even when depth
               over-reads or drops out -- the close-range regime that let the drone drive into a car. */
            if (loomFrac > kBoundaryLoomFillFrac) {
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] BOUNDARY looming fill=%.2f > %.2f (depth unreliable close up, "
                    "speed=%.2f) -> interrupt.",
                    loomFrac, kBoundaryLoomFillFrac, boundSpeed);
                raiseInterrupt("emergency_boundary");
                return;
            }
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
                    m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                    RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] GO complete dist=%.2f", dist);
                    completeCurrent("go_ok");
                } else {
                    /* Cross-track guidance: dir/total frozen at activation (the
                       start->target line). Forward speed decays with remaining
                       progress ALONG that fixed line; a separate term pulls back
                       any drift PERPENDICULAR to it. The commanded direction only
                       ever gets nudged by the (bounded, small) cross-track term --
                       never fully recomputed from bearing-to-target -- so neither
                       the pure-pursuit spiral nor the dead-reckoning runaway can
                       happen here. */
                    alN    = n - m_goStartN;
                    alE    = e - m_goStartE;
                    alD    = d - m_goStartD;
                    along  = alN * m_goDirN + alE * m_goDirE + alD * m_goDirD;
                    remain = m_goTotalDist - along;
                    if (remain < 0.0f) remain = 0.0f;
                    crN = alN - along * m_goDirN;
                    crE = alE - along * m_goDirE;
                    crD = alD - along * m_goDirD;

                    sp = m_cfg.goApproachGainHz * remain;
                    if (sp > m_activeSpeed) sp = m_activeSpeed;

                    vN = m_goDirN * sp - m_cfg.goCrossTrackGainHz * crN;
                    vE = m_goDirE * sp - m_cfg.goCrossTrackGainHz * crE;
                    vD = m_goDirD * sp - m_cfg.goCrossTrackGainHz * crD;
                    mag = std::sqrt(vN * vN + vE * vE + vD * vD);
                    if (mag > m_activeSpeed) {
                        sp  = m_activeSpeed / mag;
                        vN *= sp;
                        vE *= sp;
                        vD *= sp;
                    }
                    m_backend->set_velocity(Vec3{vN, vE, vD}, 0.0f);
                    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                        "[FMU_NODE_DIAGNOSTICS] GO dist=%.2f cmdVelENU=(%.2f,%.2f,%.2f) measVelENU=(%.2f,%.2f,%.2f) yaw=%.2f yawrate=%.2f",
                        dist, vN, vE, vD,
                        od.vel.x, od.vel.y, od.vel.z, od.yaw, od.yawrate);
                }
            } else if (id == CommandID::ROTATE) {
                /* Integrate yaw progress in the commanded direction; complete once the full
                   requested magnitude is swept -- granular incl. >=180 deg (ROADMAP 1.1.2). */
                f32 dYaw = od.yaw - m_rotatePrevYaw;
                while (dYaw >  kPi) dYaw -= 2.0f * kPi;  /* wrap per-tick delta to [-pi, pi] */
                while (dYaw < -kPi) dYaw += 2.0f * kPi;
                m_rotatePrevYaw = od.yaw;
                m_rotateRemainingRad -= m_rotateDir * dYaw;  /* subtract in-direction progress */
                if (m_rotateRemainingRad <= kRotateCompletionRad) {
                    m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                    RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] ROTATE complete remainRad=%.3f", m_rotateRemainingRad);
                    completeCurrent("rotate_ok");
                } else {
                    f32 yawRate = m_rotateDir * m_cfg.rotateYawGainHz * m_rotateRemainingRad;
                    if (yawRate >  m_cfg.rotateMaxYawRate) yawRate =  m_cfg.rotateMaxYawRate;
                    else if (yawRate < -m_cfg.rotateMaxYawRate) yawRate = -m_cfg.rotateMaxYawRate;
                    /* Rate floor: the proportional rate decays to ~0 near the target, which is what
                       left ROTATE ~5 deg short. Hold a minimum turn rate until inside the (now tight)
                       completion band so the last few degrees close promptly and precisely. */
                    else if (yawRate >= 0.0f && yawRate <  kRotateMinYawRate) yawRate =  kRotateMinYawRate;
                    else if (yawRate <  0.0f && yawRate > -kRotateMinYawRate) yawRate = -kRotateMinYawRate;
                    m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, yawRate);
                    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                        "[FMU_NODE_DIAGNOSTICS] ROTATE remainRad=%.3f cmdYawrate=%.3f measYaw=%.2f measYawrate=%.2f",
                        m_rotateRemainingRad, yawRate, od.yaw, od.yawrate);
                }
            } else if (id == CommandID::APPROACH) {
                if (m_useCannedApproachRig || m_approachBboxRig) updateCannedApproachRig(od);

                appr = m_currTask.m_cmd.m_extractCmd.m_approach;
                tnow = nowUs();

                if (m_approachBboxRig) {
                    /* bbox-approach = fly to the FROZEN world anchor by ODOMETRY, not vision. The
                       synthetic rig only "shows" the anchor when it is in frame; once the drone is
                       off-axis (after an orbit) the anchor falls off-frame, the vision servo sees
                       nothing and HOVERS FOREVER (no interrupt, no stuck-detection). We KNOW the
                       anchor's ENU, so just turn toward it and go -- this always makes progress and
                       completes at the stand-off, so it can never get stuck. */
                    Vec3 toT   = { m_cannedApproachTargetEnu.x - od.pos.x,
                                   m_cannedApproachTargetEnu.y - od.pos.y,
                                   m_cannedApproachTargetEnu.z - od.pos.z };
                    f32  horiz = std::sqrt(toT.x * toT.x + toT.y * toT.y);
                    f32  rem   = horiz - m_cfg.approachStandoffM;
                    f32  aYaw  = (horiz > 0.05f)
                               ? kOrbitYawGain * wrap_pi(std::atan2(toT.y, toT.x) - od.yaw) : 0.0f;
                    if (rem <= 0.10f) {
                        m_backend->set_velocity(Vec3{0.0f, 0.0f,
                            kApproachVertGain * (m_cannedApproachTargetEnu.z - od.pos.z)}, aYaw);
                        RCLCPP_INFO(this->get_logger(),
                            "[FMU_NODE_DEBUG] APPROACH(bbox) reached anchor target=%s rem=%.2f -> approach_ok.",
                            appr.target, rem);
                        completeCurrent("approach_ok");
                    } else {
                        f32  spd = std::min(rem, kApproachSpeedDefault / 100.0f);   /* brake near the end. */
                        Vec3 dir = { toT.x / horiz, toT.y / horiz, 0.0f };
                        m_backend->set_velocity(
                            Vec3{ dir.x * spd, dir.y * spd,
                                  kApproachVertGain * (m_cannedApproachTargetEnu.z - od.pos.z) }, aYaw);
                        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                            "[FMU_NODE_DIAGNOSTICS] APPROACH(bbox) go-to anchor target=%s rem=%.2f horiz=%.2f dz=%.2f",
                            appr.target, rem, horiz, m_cannedApproachTargetEnu.z - od.pos.z);
                    }
                    return;
                }
                {
                    /* Prefer the stable track id (holds the chosen person across list re-sorting
                       or a second person in view); fall back to the label. Snap + ids come from
                       ONE frame so the id lookup and the rest of the branch agree. */
                    auto tracked = m_perception->trackedSnapshot();
                    snap = tracked ? std::shared_ptr<PerceptionSnapshot>(tracked, &tracked->snap)
                                   : std::shared_ptr<PerceptionSnapshot>();
                    tr = TargetRelative{};
                    if (tracked && m_approachTrackId >= 0)
                        tr = detectionByTrackId(tracked->snap, tracked->ids, m_approachTrackId, kApproachCamera, tnow);
                    if (!tr.found && snap)
                        tr = detectionByLabel(*snap, appr.target, kApproachCamera, tnow);
                }
                /* Real YOLO on an unfamiliar mesh can flip class mid-approach (seen in SITL:
                   "car" -> "boat" at closer range, same object). If the exact label match
                   missed but exactly one thing is in frame, there is nothing else it could be
                   -- track it by presence, not by a label the model itself is unstable on. */
                if (!tr.found && snap && snap->count == 1) {
                    tr = detectionByLabel(*snap, snap->dets[0].label, kApproachCamera, tnow);
                }

                if (!tr.found || tr.age_us > kApproachFreshUs) {
                    if (m_approachHaveLastAim &&
                        (tnow - m_approachLastAimUs) <= kApproachLostTimeoutUs) {
                        appTrav = 0.0f;
                        appRem  = m_cfg.approachStandoffM;   /* until latched, treat the stop point as far */
                        if (m_approachBudgetLatched) {
                            dx      = od.pos.x - m_approachStartPos.x;
                            dy      = od.pos.y - m_approachStartPos.y;
                            dz      = od.pos.z - m_approachStartPos.z;
                            appTrav = std::sqrt(dx * dx + dy * dy + dz * dz);
                            appRem  = m_approachTravelBudget - appTrav;
                        }
                        if (m_approachBudgetLatched && appRem <= kApproachCoastHoldMarginM) {
                            /* Within the hold margin of the dead-reckoned stop, target lost. Odometry
                               already knows the stop point, so finish on dead-reckon -- do NOT hold
                               waiting for a re-lock that may never come. A permanently-lost target
                               (e.g. it left the frame at close range) would otherwise deadlock here
                               at zero velocity until the coast window expires and the approach fails.
                               Stopping up to kApproachCoastHoldMarginM short of the standoff is safe:
                               it leaves the drone farther from the target, never closer, and never
                               coasts blind into it. */
                            if (!approachMotionNominal(od)) {
                                RCLCPP_WARN(this->get_logger(),
                                    "[FMU_NODE_DEBUG] APPROACH reached range=%.2f but motion off-nominal "
                                    "(yawrate=%.2f vertVel=%.2f) -> impact interrupt.",
                                    m_approachLastRange, od.yawrate, od.vel.z);
                                raiseInterrupt("approach_impact");
                                return;
                            }
                            m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                            RCLCPP_INFO(this->get_logger(),
                                "[FMU_NODE_DEBUG] APPROACH reached target=%s traveled=%.2f/%.2f rem=%.2f (lost, dead-reckon stop)",
                                appr.target, appTrav, m_approachTravelBudget, appRem);
                            completeCurrent("approach_ok");
                        } else {
                            aimFlu = { m_approachLastAimFlu.x * kApproachCoastSpeedMps,
                                       m_approachLastAimFlu.y * kApproachCoastSpeedMps,
                                       m_approachLastAimFlu.z * kApproachCoastSpeedMps };
                            velEnu = flu_to_enu(aimFlu, od.yaw);
                            m_backend->set_velocity(velEnu, 0.0f);
                            RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                                "[FMU_NODE_DIAGNOSTICS] APPROACH coasting target=%s (lost).", appr.target);
                        }
                    } else if (!m_approachHaveLastAim &&
                               (tnow - m_approachActivateUs) <= kApproachLostTimeoutUs) {
                        /* Initial acquisition: the target may not be framed on the exact tick
                           APPROACH activates (detection is intermittent). Hover and wait for the
                           first lock instead of failing on tick one -- only then can coast apply. */
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                            "[FMU_NODE_DIAGNOSTICS] APPROACH acquiring target=%s (no lock yet).", appr.target);
                    } else {
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                        RCLCPP_WARN(this->get_logger(),
                            "[FMU_NODE_DEBUG] APPROACH lost target=%s past coast window -> FAIL.",
                            appr.target);
                        if (snap && snap->count > 0) {
                            RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                                "[FMU_NODE_DEBUG] APPROACH sees %u detection(s), first label=%s age_ms=%.0f",
                                snap->count, snap->dets[0].label, tr.age_us / 1000.0);
                        }
                        completeCurrent("approach_lost_failed");
                    }
                } else {
                    m_approachLastAimFlu  = tr.dirFlu;
                    m_approachLastAimUs   = tnow;
                    m_approachHaveLastAim = true;
                    pushApproachRange(tr.range);
                    m_approachLastRange   = medianApproachRange();   /* median-filtered; rejects depth spikes */

                    /* Depth range is too noisy near the target to brake on directly: in SITL the
                       same parked car reads anywhere from 1.6 m to 6.5 m tick to tick. Braking on
                       that noise makes the drone creep forward until a fluke low read fires, by
                       which point it has already hit the car. So brake on odometry, not depth.
                       Once a stable early range estimate exists, latch the drone position and a
                       fixed travel budget = range - standoff. The stop point is then dead-reckoned
                       from how far the drone has actually moved, which is exact, so a noisy high
                       depth read can no longer re-accelerate us into the target. */
                    if (!m_approachBudgetLatched &&
                        m_approachRangeCount >= kApproachRangeMedianWindow) {
                        m_approachStartPos      = od.pos;
                        m_approachTravelBudget  = m_approachLastRange - m_cfg.approachStandoffM;
                        if (m_approachTravelBudget < 0.0f) m_approachTravelBudget = 0.0f;
                        m_approachBudgetLatched = true;
                        RCLCPP_INFO(this->get_logger(),
                            "[FMU_NODE_DEBUG] APPROACH range locked R0=%.2f travelBudget=%.2f",
                            m_approachLastRange, m_approachTravelBudget);
                    }
                    appTrav = 0.0f;
                    appRem  = m_cfg.approachStandoffM;   /* until latched, treat the stop point as far */
                    if (m_approachBudgetLatched) {
                        dx      = od.pos.x - m_approachStartPos.x;
                        dy      = od.pos.y - m_approachStartPos.y;
                        dz      = od.pos.z - m_approachStartPos.z;
                        appTrav = std::sqrt(dx * dx + dy * dy + dz * dz);
                        appRem  = m_approachTravelBudget - appTrav;
                    }

                    if ((m_approachBudgetLatched && appRem <= 0.0f) ||
                        (m_approachLastRange > 0.0f && m_approachLastRange < m_cfg.approachStandoffM)) {
                        if (!approachMotionNominal(od)) {
                            RCLCPP_WARN(this->get_logger(),
                                "[FMU_NODE_DEBUG] APPROACH reached range=%.2f but motion off-nominal "
                                "(yawrate=%.2f vertVel=%.2f) -> impact interrupt.",
                                m_approachLastRange, od.yawrate, od.vel.z);
                            raiseInterrupt("approach_impact");
                            return;
                        }
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                        RCLCPP_INFO(this->get_logger(),
                            "[FMU_NODE_DEBUG] APPROACH reached target=%s traveled=%.2f/%.2f range=%.2f",
                            appr.target, appTrav, m_approachTravelBudget, m_approachLastRange);
                        completeCurrent("approach_ok");
                    } else {
                        speedCeil = (appr.speed > 0.0f ? appr.speed : m_cfg.approachSpeedDefault) / 100.0f;
                        /* Brake on remaining dead-reckoned travel once latched; before the latch,
                           creep slowly forward while collecting range samples for R0. */
                        spF       = m_approachBudgetLatched
                                        ? kApproachFwdGainHz * appRem
                                        : kApproachCoastSpeedMps;
                        if (spF < 0.0f) spF = 0.0f;
                        if (spF > speedCeil) spF = speedCeil;
                        /* Depth-independent brake: as the REAL target fills the frame it IS close,
                           regardless of the noisy depth budget (that budget dead-reckoned into the car).
                           Ramp spF to zero from kApproachBrakeFillFrac to the stop fill. The canned rig's
                           fixed tiny box (fill~0.02) never reaches this, so the canned approach stays fast. */
                        {
                            f32 fillNow = snap ? maxBboxFillFrac(*snap, kApproachCamera) : 0.0f;
                            if (fillNow > kApproachBrakeFillFrac) {
                                f32 fb = speedCeil * (kApproachStopFillFrac - fillNow) /
                                         (kApproachStopFillFrac - kApproachBrakeFillFrac);
                                if (fb < 0.0f) fb = 0.0f;
                                if (spF > fb) spF = fb;
                            }
                        }
                        yawRate = -kApproachYawGain * tr.errX;
                        vUp     = -kApproachVertGain * tr.errY;
                        /* Never let vertical centering drive the drone below safe AGL (ground person
                           low in frame -> errY pulls down -> sink into dirt -> PX4 disarm). */
                        if (od.pos.z <= kApproachMinAnchorAltEnu && vUp < 0.0f) vUp = 0.0f;
                        aimFlu  = { spF, 0.0f, vUp };
                        velEnu  = flu_to_enu(aimFlu, od.yaw);
                        fwdDir  = flu_to_enu(Vec3{1.0f, 0.0f, 0.0f}, od.yaw);
                        lat     = lateralComponent(od.vel, fwdDir);
                        velEnu.x -= kApproachLateralDamp * lat.x;
                        velEnu.y -= kApproachLateralDamp * lat.y;
                        velEnu.z -= kApproachLateralDamp * lat.z;
                        magV = std::sqrt(velEnu.x * velEnu.x + velEnu.y * velEnu.y + velEnu.z * velEnu.z);
                        if (magV > speedCeil && magV > 0.0f) {
                            velEnu.x *= speedCeil / magV;
                            velEnu.y *= speedCeil / magV;
                            velEnu.z *= speedCeil / magV;
                        }
                        m_backend->set_velocity(velEnu, yawRate);
                        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                            "[FMU_NODE_DIAGNOSTICS] APPROACH target=%s rawRange=%.2f medRange=%.2f "
                            "freeDepth=%.2f budget=%.2f trav=%.2f rem=%.2f fill=%.2f errX=%.2f errY=%.2f "
                            "cmdVelENU=(%.2f,%.2f,%.2f) yawRate=%.2f",
                            appr.target, tr.range, m_approachLastRange,
                            m_perception->nearestFreeDepthM(), m_approachTravelBudget, appTrav, appRem,
                            (snap ? maxBboxFillFrac(*snap, kApproachCamera) : 0.0f),
                            tr.errX, tr.errY, velEnu.x, velEnu.y, velEnu.z, yawRate);
                    }
                }
            } else if (id == CommandID::FOLLOW) {
                /* Yaw-only "follow in place": the drone HOLDS its position and turns its head
                   (yaw + gentle vertical) to keep the target centered -- it does NOT fly toward
                   the target. Truly position-free: no od.pos, no translation, so it is robust to
                   a dead/absent localizer (the Tello). The ONLY translation is a safety back-off
                   when the target is closer than the safe distance. Never completes. */
                fol  = m_currTask.m_cmd.m_extractCmd.m_follow;
                tnow = nowUs();
                snap = m_perception->snapshot();
                {
                    /* jump gate: reject a same-label box that teleports across the frame (churn),
                       so the coast/hover ladder holds instead of grabbing a wrong person. */
                    const f32 kFollowMaxJumpPx = 0.30f * static_cast<f32>(kApproachCamera.width);
                    tr = (snap && m_followHaveLast)
                           ? detectionNearestCenter(*snap, m_followLabel, m_followLastU, m_followLastV, kApproachCamera, tnow, kFollowMaxJumpPx)
                           : (snap ? detectionByLabel(*snap, m_followLabel, kApproachCamera, tnow) : TargetRelative{});
                }

                if (tr.found && tr.age_us <= kApproachFreshUs &&
                    m_followHaveErr && std::fabs(tr.errX - m_followLastErrX) > kFollowErrJumpReject) {
                    /* Box-jump reject: a small/distant person's box jitters frame-to-frame. An errX leap
                       this large in one tick is noise, not lateral motion -- hold and keep the last
                       anchor so the yaw servo can never chase a phantom jump into a spin (the range~16m
                       failure). The next in-tolerance frame re-engages the servo below. */
                    m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                        "[FMU_NODE_DIAGNOSTICS] FOLLOW(yaw-only) target=%s box jumped errX %.2f->%.2f -> holding.",
                        m_followLabel, m_followLastErrX, tr.errX);
                } else if (tr.found && tr.age_us <= kApproachFreshUs) {
                    /* Re-anchor the tracker on the bbox center just locked (px). */
                    m_followLastErrX  = tr.errX;
                    m_followHaveErr   = true;
                    m_followLastU     = kApproachCamera.cx + tr.errX * kApproachCamera.cx;
                    m_followLastV     = kApproachCamera.cy + tr.errY * kApproachCamera.cy;
                    m_followLastAimUs = tnow;
                    m_followHaveLast  = true;

                    /* Yaw + vertical center the target; NO forward chase. standoff_cm (or the config
                       followStandoffM) is the MINIMUM SAFE distance: back off if the target is closer
                       than that, otherwise translate zero. spF is clamped to <= 0 so FOLLOW can never
                       advance -- it holds position and turns its head. (Back-off keys on depth, which
                       is noisy; a spurious retreat is away from the target, i.e. the safe direction.
                       A loom/bbox-fill back-off is a future refinement.) */
                    f32 minSafe = (fol.standoff_cm > 0) ? fol.standoff_cm / 100.0f : m_cfg.followStandoffM;
                    speedCeil   = (fol.speed > 0 ? __scast(f32, fol.speed) : kApproachSpeedDefault) / 100.0f;
                    /* Deadband + gentle gain + low rate cap: ignore sub-deadband error (no twitch on a
                       centred or noisy box) and never let a large error saturate the yaw into a spin. */
                    yawRate = (std::fabs(tr.errX) < kFollowYawDeadband) ? 0.0f : -kFollowYawGain * tr.errX;
                    if (yawRate >  kFollowYawMaxRps) yawRate =  kFollowYawMaxRps;
                    if (yawRate < -kFollowYawMaxRps) yawRate = -kFollowYawMaxRps;
                    vUp     = (std::fabs(tr.errY) < kFollowYawDeadband) ? 0.0f : -kApproachVertGain * tr.errY;
                    spF     = 0.0f;                            /* never advance.                */
                    if (tr.range > 0.0f && tr.range < minSafe)
                        spF = kFollowFwdGain * (tr.range - minSafe);   /* < 0: safety back-off only. */
                    if (spF < -speedCeil) spF = -speedCeil;
                    if (spF > 0.0f)       spF = 0.0f;                  /* hard guarantee: no forward. */
                    aimFlu  = { spF, 0.0f, vUp };
                    velEnu  = flu_to_enu(aimFlu, od.yaw);
                    m_backend->set_velocity(velEnu, yawRate);
                    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                        "[FMU_NODE_DIAGNOSTICS] FOLLOW(yaw-only) target=%s trackId=%d range=%.2f minSafe=%.2f "
                        "errX=%.2f errY=%.2f backoff=%.2f yawRate=%.2f vUp=%.2f",
                        m_followLabel, m_followTrackId, tr.range, minSafe, tr.errX, tr.errY, spF, yawRate, vUp);
                } else if (m_followHaveLast) {
                    /* Was locked, now lost -- most likely the target walked off the frame EDGE. Do NOT
                       hover blind: YAW toward the side where it was last seen to sweep it back into view.
                       m_followLastU is the last bbox-centre column (px); its offset from centre gives the
                       exit side (same sign law as the servo, which is proven to centre). Bounded to
                       kFollowSweepUs after the last sighting so a target gone for good never spins the
                       drone forever; after that, hold still and keep looking (the tr.found branch above
                       re-locks the instant it reappears). FOLLOW still never self-completes. */
                    /* Lost the box. In these scenarios the target paces WITHIN the field of view, so a
                       "loss" is almost always a brief seg detection flicker, NOT a real exit -- the
                       person is still right in front. HOLD position and keep re-acquiring by label; the
                       servo branch above re-locks the instant the box returns. Do NOT yaw to "look" for
                       it: rotating open-loop points the drone away from someone still in view and looks
                       like the drone spinning. FOLLOW never self-completes. (A real look-where-lost, for
                       a target that truly leaves frame, needs non-flickery detection to gate it -- left
                       out until then rather than misfiring on every blink.) */
                    m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
                        "[FMU_NODE_DIAGNOSTICS] FOLLOW(yaw-only) target=%s gap -> holding, re-acquiring.",
                        m_followLabel);
                } else if ((tnow - m_followLastAimUs) <= kFollowLostTimeoutUs) {
                    /* Never locked since activation: short grace window to get the FIRST fix. */
                    m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                        "[FMU_NODE_DIAGNOSTICS] FOLLOW(yaw-only) acquiring target=%s ...", m_followLabel);
                } else {
                    /* Never found the target the VLM named within the acquire window -> tell the VLM so it
                       can search elsewhere or re-pick. A loss AFTER a lock does NOT reach here (held above). */
                    m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                    RCLCPP_WARN(this->get_logger(),
                        "[FMU_NODE_DEBUG] FOLLOW target=%s never acquired > %ums -> follow_no_target (releasing).",
                        m_followLabel, kFollowLostTimeoutMs);
                    completeCurrent("follow_no_target");
                }
            } else if (id == CommandID::ORBIT) {
                orb  = m_currTask.m_cmd.m_extractCmd.m_orbitTarget;
                tnow = nowUs();
                f32 yawRate = 0.0f;

                /* HARDCODED SAFE ORBIT (agent1, 2026-08-13). Deterministic geometry, NO depth. Monocular
                   depth range proved too noisy for an autonomous building-orbit -- every depth-seeded
                   version placed the centre wrong and flung the drone into the terrain (z -> -3.8m). This
                   flies a FIXED circle: centre = kOrbitFixedRadiusM straight ahead of where the orbit
                   starts, radius = the SAME distance (so the drone begins ON the circle and never flies
                   inward toward the wall), altitude HELD at >= kOrbitFixedAltM (cannot descend). The demo
                   narrates that depth estimation is the current limitation. */
                if (!m_orbitLatched) {
                    /* Honour the commanded radius_cm (clamped) so the circle is sized to the target
                       -- a car wants a tighter orbit than a building. Centre stays exactly R ahead so
                       the drone still begins ON the circle and never flies inward. radius_cm unset (0)
                       falls back to the hardcoded default. */
                    f32 R = (orb.radius > 0.0f) ? (orb.radius / 100.0f) : kOrbitFixedRadiusM;
                    if (R < kOrbitMinRadiusM) R = kOrbitMinRadiusM;
                    if (R > kOrbitMaxRadiusM) R = kOrbitMaxRadiusM;
                    Vec3 fwd = flu_to_enu(Vec3{1.0f, 0.0f, 0.0f}, od.yaw);
                    m_orbitCenterEnu = { od.pos.x + fwd.x * R,
                                         od.pos.y + fwd.y * R, od.pos.z };
                    m_orbitRadius   = R;
                    m_orbitAltEnu   = std::max(od.pos.z, kOrbitFixedAltM);
                    m_orbitPrevPos  = od.pos;
                    m_orbitSweptRad = 0.0f;
                    m_orbitLatched  = true;
                    RCLCPP_INFO(this->get_logger(),
                        "[FMU_NODE_DEBUG] ORBIT (hardcoded) target=%s centerENU=(%.2f,%.2f) R=%.2f alt=%.2f dir=%s",
                        orb.target, m_orbitCenterEnu.x, m_orbitCenterEnu.y, m_orbitRadius, m_orbitAltEnu,
                        (m_orbitDir > 0.0f) ? "ccw" : "cw");
                } else {
                    oToDrone = { od.pos.x - m_orbitCenterEnu.x, od.pos.y - m_orbitCenterEnu.y, 0.0f };
                    oDist    = std::sqrt(oToDrone.x * oToDrone.x + oToDrone.y * oToDrone.y);
                    if (oDist < 1e-3f) oDist = 1e-3f;
                    oRadial  = { oToDrone.x / oDist, oToDrone.y / oDist, 0.0f };
                    oTangent = { -oRadial.y * m_orbitDir, oRadial.x * m_orbitDir, 0.0f };
                    oRadErr  = m_orbitRadius - oDist;
                    f32 radialV = kOrbitRadialGainHz * oRadErr;
                    if (radialV >  kOrbitMaxRadialMps) radialV =  kOrbitMaxRadialMps;
                    if (radialV < -kOrbitMaxRadialMps) radialV = -kOrbitMaxRadialMps;
                    f32 strafe = std::max(m_orbitSpeed, kOrbitMinTangentialMps);
                    velEnu.x = oRadial.x * radialV + oTangent.x * strafe;
                    velEnu.y = oRadial.y * radialV + oTangent.y * strafe;
                    velEnu.z = kApproachVertGain * (m_orbitAltEnu - od.pos.z);   /* strong altitude hold. */
                    oDesYaw  = std::atan2(-oToDrone.y, -oToDrone.x);             /* face the centre. */
                    /* Feedforward the orbital angular rate: the bearing to the centre rotates at
                       strafe/R in the orbit direction, so feeding that in lets the P term only trim
                       residual error. Without it the yaw lags the centre and the drone never points
                       exactly at the target (and that offset is what remained at the start heading). */
                    f32 omegaFf = m_orbitDir * strafe / m_orbitRadius;
                    yawRate  = omegaFf + kOrbitYawGain * wrap_pi(oDesYaw - od.yaw);
                    m_backend->set_velocity(velEnu, yawRate);
                    oAngle     = std::atan2(od.pos.y - m_orbitCenterEnu.y, od.pos.x - m_orbitCenterEnu.x);
                    oPrevAngle = std::atan2(m_orbitPrevPos.y - m_orbitCenterEnu.y,
                                            m_orbitPrevPos.x - m_orbitCenterEnu.x);
                    m_orbitSweptRad += std::fabs(wrap_pi(oAngle - oPrevAngle));
                    m_orbitPrevPos   = od.pos;
                    if (m_orbitSweptRad >= m_orbitTargetRad) {
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                        RCLCPP_INFO(this->get_logger(),
                            "[FMU_NODE_DEBUG] ORBIT complete target=%s swept=%.2f/%.2f rad",
                            orb.target, m_orbitSweptRad, m_orbitTargetRad);
                        completeCurrent("orbit_ok");
                    } else {
                        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                            "[FMU_NODE_DIAGNOSTICS] ORBIT target=%s dist=%.2f/%.2f alt=%.2f/%.2f swept=%.2f/%.2f",
                            orb.target, oDist, m_orbitRadius, od.pos.z, m_orbitAltEnu,
                            m_orbitSweptRad, m_orbitTargetRad);
                    }
                }
            } else if (id == CommandID::SEARCH) {
                srch = m_currTask.m_cmd.m_extractCmd.m_SearchTarget;
                tnow = nowUs();
                snap = m_perception->snapshot();

                /* Success: the named target came into view. Log full diagnostics (label/confidence/
                   depth/bbox) -- that line IS the operator notification -- then finish. */
                /* SEARCH-by-tag: hold the tracked snapshot so `hit` (a pointer into it) stays alive
                   through the log below. If the VLM named a specific track_id (re-finding a known
                   target), ONLY that tag counts -- never false-succeed on a different person. Else
                   match the label and surface whatever track_id the hit carries, so the VLM can
                   confirm THAT tag next cycle. */
                std::shared_ptr<TrackedSnapshot> tk = m_perception->trackedSnapshot();
                hit = nullptr;
                i32 hitTrackId = -1;
                if (tk && tk->snap.valid) {
                    for (di = 0; di < tk->snap.count; ++di) {
                        bool match = (srch.target_id >= 0)
                            ? (di < tk->ids.count && tk->ids.id[di] == srch.target_id)
                            : labelMatchesTarget(tk->snap.dets[di].label, srch.target);
                        if (match) {
                            hit        = &tk->snap.dets[di];
                            hitTrackId = (di < tk->ids.count) ? tk->ids.id[di] : -1;
                            break;
                        }
                    }
                }
                if (hit != nullptr && hit->confidence < kSearchMinConfidence) {
                    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 500,
                        "[FMU_NODE_DIAGNOSTICS] SEARCH ignoring weak %s conf=%.2f (< %.2f) -- still searching.",
                        srch.target, hit->confidence, kSearchMinConfidence);
                    hit = nullptr;   /* below the floor: treat as not found and keep the pattern going. */
                }
                if (hit != nullptr) {
                    m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                    RCLCPP_WARN(this->get_logger(),
                        "[FMU_NODE] SEARCH DETECTED target=%s track_id=%d conf=%.2f depth_cm=%.1f "
                        "bbox=(%d,%d,%d,%d) -> auto-approach (not re-planning).",
                        srch.target, hitTrackId, hit->confidence, hit->median_depth_cm,
                        hit->bbox_xmin, hit->bbox_ymin, hit->bbox_xmax, hit->bbox_ymax);
                    /* Search found the target. A weak planner (2B) tends to emit ANOTHER search
                       instead of approaching, looping forever ("search doesn't short-circuit on the
                       vehicle"). Deterministically hand the found track straight to APPROACH so a
                       real detection leads to a real approach, no dependence on the planner here. */
                    {
                        CmdApproach ap{};
                        std::snprintf(ap.target, sizeof(ap.target), "%s", srch.target);
                        ap.target_id = hitTrackId;
                        ap.speed     = 0.0f;
                        ActiveTask approachTask{};
                        approachTask.m_cmd = GenericCommand(ap);
                        std::snprintf(approachTask.m_thought, sizeof(approachTask.m_thought),
                                      "search found %s -> approaching it", srch.target);
                        activateTask(approachTask);
                        return;
                    }
                } else if ((tnow - m_searchStartUs) > m_searchTimeoutUs ||
                           m_searchTotalDistM >= m_searchMaxDistM ||
                           m_searchLegCount >= m_searchMaxLegs || m_searchReturning) {
                    /* Failed: return to where SEARCH started before completing, rather than
                       stranding the drone wherever the last lane happened to end -- a failed
                       search should not itself become a navigation hazard for whatever the VLM
                       plans next. m_searchOriginPos (unlike m_searchStartPos) is set once at
                       activation and never touched by a lane transition, so it is still the
                       true start point here. */
                    if (!m_searchReturning) {
                        m_searchReturning  = true;
                        m_searchLegStartUs = tnow;   /* reused as the return-leg's own timer. */
                        RCLCPP_INFO(this->get_logger(),
                            "[FMU_NODE_DEBUG] SEARCH exhausted target=%s legs=%u elapsed_ms=%.0f -- returning to start.",
                            srch.target, m_searchLegCount, (tnow - m_searchStartUs) / 1000.0);
                    }
                    dx        = m_searchOriginPos.x - od.pos.x;
                    dy        = m_searchOriginPos.y - od.pos.y;
                    distStart = std::sqrt(dx * dx + dy * dy);
                    if (distStart < kGoCompletionRadiusM ||
                        (tnow - m_searchLegStartUs) > __scast(u64, kSearchReturnTimeoutMs) * 1000ULL) {
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                        RCLCPP_INFO(this->get_logger(),
                            "[FMU_NODE_DEBUG] SEARCH return-to-start complete dist=%.2f", distStart);
                        completeCurrent("search_exhausted");
                    } else {
                        altErr   = m_searchAltEnu - od.pos.z;
                        velEnu.x = (dx / distStart) * m_cfg.searchSweepSpeedMps;
                        velEnu.y = (dy / distStart) * m_cfg.searchSweepSpeedMps;
                        velEnu.z = kApproachVertGain * altErr;
                        m_backend->set_velocity(velEnu, 0.0f);
                        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                            "[FMU_NODE_DIAGNOSTICS] SEARCH returning-to-start target=%s dist=%.2f",
                            srch.target, distStart);
                    }
                } else if (m_searchScanning) {
                    /* CHECKPOINT: rotate 360 in place (no translation), holding altitude. Detection is
                       checked every tick above, so a hit mid-spin ends the search. A full turn with no
                       hit -> step forward to the next checkpoint. */
                    f32 dScan = od.yaw - m_searchScanPrevYaw;
                    while (dScan >  kPi) dScan -= 2.0f * kPi;
                    while (dScan < -kPi) dScan += 2.0f * kPi;
                    m_searchScanPrevYaw       = od.yaw;
                    m_searchScanRemainingRad -= std::fabs(dScan);   /* direction-agnostic full turn. */
                    if (m_searchScanRemainingRad <= kRotateCompletionRad) {
                        m_searchScanning   = false;                 /* scanned here, nothing -> advance. */
                        m_searchStartPos   = od.pos;
                        m_searchLegStartUs = tnow;
                        m_searchLegCount++;
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                        RCLCPP_INFO(this->get_logger(),
                            "[FMU_NODE_DEBUG] SEARCH checkpoint %u scanned, target=%s not found -> advance %.1fm.",
                            m_searchLegCount, srch.target, m_searchStepM);
                    } else {
                        f32 yawRate = m_searchDir * 1.0f;   /* dedicated scan rate ~360 in 6.3s: fast enough to
                                                               cover ground, slow enough for YOLO to catch a
                                                               target sweeping through view (rotateMaxYawRate=0.8 was ~8s). */
                        altErr = m_searchAltEnu - od.pos.z;
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, kApproachVertGain * altErr}, yawRate);
                        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                            "[FMU_NODE_DIAGNOSTICS] SEARCH scan checkpoint=%u target=%s remainRad=%.2f",
                            m_searchLegCount, srch.target, m_searchScanRemainingRad);
                    }
                } else {
                    /* ADVANCE: fly straight one step along the search heading (yaw+start_heading_deg),
                       camera facing the travel direction, at fixed altitude. At the step end, scan again.
                       A per-phase timeout also advances us (odometry can drift). */
                    dx        = od.pos.x - m_searchStartPos.x;
                    dy        = od.pos.y - m_searchStartPos.y;
                    distStart = std::sqrt(dx * dx + dy * dy);
                    if (distStart >= m_searchStepM ||
                        (tnow - m_searchLegStartUs) > __scast(u64, m_searchParams.legTimeoutMs) * 1000ULL) {
                        m_searchTotalDistM      += distStart;        /* count real distance toward the cap. */
                        m_searchScanning         = true;             /* reached a checkpoint -> scan 360. */
                        m_searchScanRemainingRad = 2.0f * kPi;
                        m_searchScanPrevYaw      = od.yaw;
                        m_searchLegStartUs       = tnow;
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                    } else {
                        headErr = wrap_pi(m_searchLaneHeadingRad - od.yaw);
                        altErr  = m_searchAltEnu - od.pos.z;
                        aimFlu  = { m_cfg.searchSweepSpeedMps, 0.0f, kApproachVertGain * altErr };
                        velEnu  = flu_to_enu(aimFlu, od.yaw);
                        m_backend->set_velocity(velEnu, m_cfg.rotateYawGainHz * headErr);
                        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                            "[FMU_NODE_DIAGNOSTICS] SEARCH advance checkpoint=%u target=%s dist=%.2f/%.2f total=%.1f/%.1f",
                            m_searchLegCount, srch.target, distStart, m_searchStepM,
                            m_searchTotalDistM, m_searchMaxDistM);
                    }
                }
            } else if (id == CommandID::HOVER) {
                stepHover();
            } else {
                RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] task id=%d not movement -> auto-complete.",
                    __scast(int, id));
                completeCurrent("noop_ok");
            }
            return;
        }

        /* Interrupt hold (spec 1 1.5): a trigger stashed the task and cleared m_hasActive. Keep
           streaming hover while we fall through to maybePlan(), which wakes the VLM to reassess.
           activateTask() clears m_hasStashed when the reassess plan lands; nothing auto-resumes. */
        if (m_hasStashed) {
            m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
        }

        if (m_settleTicksRemaining > 0) {
            m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f); /* hold while residual momentum decays. */
            --m_settleTicksRemaining;
            return;
        }

        /* RTH handoff: the return-to-origin GO has finished (no active task) ->
           land at the origin, once. */
        if (mb_batteryReturn && !mb_batteryLand) {
            mb_batteryLand = true;
            m_flightState.store(FlightState::LANDING, kMemOrderRelax);
            return;
        }

        if (m_taskQueue->try_dequeue(next)) {
            activateTask(next);
        } else {
            maybePlan();  /* queue drained -> ask the VLM for the next plan. */
        }
    }

    /* Event-driven VLM wake (ARCH sec 5): queue empty + mission active -> plan.
       Blocking inference runs OFF the control thread via std::async, so the
       20Hz loop + the backend stream watchdog never stall. m_planning is the
       single-flight guard; the async task is the queue's ONLY producer, so the
       SPSC contract holds. Planning only fires in the idle gap (no active task,
       queue empty), so it never races completeCurrent()'s history writes. */
    void maybePlan() {
        khCameraPipelineMsgType img;
        u64             now;

        if (!m_missionActive.load(std::memory_order_acquire)) return;
        if (m_planning.load(kMemOrderRelax)) return;
        now = nowUs();
        if (now - m_lastPlanUs < kPlanCooldownUs) return;
        img = std::atomic_load(&m_currImg);
        /* Prefer planning WITH vision, but never let an absent/dead camera brick the
           drone: wait up to kVisionWarmupUs for the first frame, then plan text-only.
           As soon as a frame arrives (img non-null) this passes and plans immediately. */
        if (!img && (now - m_missionStartUs) < kVisionWarmupUs) {
            RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 2000,
                "[FMU_NODE_DEBUG] waiting for first camera frame before planning...");
            return;
        }
        /* First-plan warm-up: seg emits its first detection a beat after the first frame. Planning on
           that blank gap makes the VLM think an in-view target is absent and start searching (then it
           spins away and never recovers). Wait up to kPerceptionWarmupUs for the FIRST detection. */
        if (!m_everSawDetection.load(kMemOrderRelax)) {
            auto tk0 = m_perception ? m_perception->trackedSnapshot() : nullptr;
            if (tk0 && tk0->snap.valid && tk0->snap.count > 0) {
                m_everSawDetection.store(true, kMemOrderRelax);
            } else if ((now - m_missionStartUs) < kPerceptionWarmupUs) {
                RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
                    "[FMU_NODE_DEBUG] waiting for first perception detection before first plan...");
                return;
            }
        }

        m_planning.store(true, kMemOrderRelax);
        RCLCPP_INFO(this->get_logger(),
            "[FMU_NODE_DEBUG] VLM wake: requesting plan (vision=%d).", static_cast<int>(static_cast<bool>(img)));
        m_planFuture = std::async(std::launch::async, [this, img]() {
            std::string plan;
            callLlamaServer(m_chat.m_initialCommand, img, plan);
            RCLCPP_INFO(this->get_logger(),
                "[FMU_NODE_DEBUG] VLM plan received (%zu chars).", plan.size());
            translateToBaseCommands(plan);
            m_lastPlanUs = nowUs();
            m_planning.store(false, kMemOrderRelax);
        });
    }

    /* steady_clock, not ROS clock -- must share an epoch with PerceptionRuntime::nowUs()
       (perception_runtime.hpp) since APPROACH diffs a detection's host_stamp_us against
       this. Mixing epochs (ROS wall time vs steady_clock) produced a garbage multi-hour
       "age" on the very first real-perception run. */
    u64 nowUs() const {
        return static_cast<u64>(std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
    }

    /* ================= A2 observability helpers (additive) ===================
       Image/HUD publishing + the per-run VLM prompt/response log. None of this
       feeds control; it is pure inspection tooling for the live demo. */

    /* Enable the A2 dashboard-diagnostics pipeline iff FMU_OBSERVABILITY is set: the annotated /
       depth / HUD / VLM-text / context / rates publishers, the optional FMU_A2_IMG_W/H debug image
       size, and the per-run VLM prompt log (filename fixed once so a whole run lands in one file --
       no per-cycle recompute, no clobber across runs). Off by default: zero publishers, zero
       per-cycle cost. Called once from the ctor; the getenv here is the sanctioned config hook. */
    void initDashboardDiagnostics() {
        /* A2 observability (additive): image topics the perception loops feed, a text
           HUD topic, and the per-run VLM prompt/response log path (filename fixed once
           here so a whole run lands in one file -- no per-cycle recompute, no clobber
           across runs). std::error_code overload: a pre-existing dir is not an error. */
        {
            const char* obs  = std::getenv("FMU_OBSERVABILITY");
            mb_observability = obs && obs[0] != '\0' && obs[0] != '0';
        }
        if (mb_observability) {
            m_pubAnnotated     = this->create_publisher<sensor_msgs::msg::Image>(kVlmViewTopic, 10);
            m_pubDepthColormap = this->create_publisher<sensor_msgs::msg::Image>(kDepthColormapTopic, 10);
            m_pubHud           = this->create_publisher<std_msgs::msg::String>(kFmuHudTopic, 10);
            m_pubVlmText       = this->create_publisher<std_msgs::msg::String>(kVlmTextTopic, 10);
            m_pubVlmContext    = this->create_publisher<std_msgs::msg::String>(kVlmContextTopic, 10);
            m_pubRates         = this->create_publisher<std_msgs::msg::String>(kFmuRatesTopic, 10);
            /* Debug-only higher-res A2 images: FMU_A2_IMG_W / FMU_A2_IMG_H override the 320x240
               publish size. Still ~10 Hz throttled and only encoded while a dashboard client is
               attached, so a bigger size costs nothing until you actually watch it; clamped to the
               source frame at publish time (no upscale). Leave unset for the lean default. */
            if (const char* w = std::getenv("FMU_A2_IMG_W")) { int v = std::atoi(w); if (v > 0) m_a2ImgW = v; }
            if (const char* h = std::getenv("FMU_A2_IMG_H")) { int v = std::atoi(h); if (v > 0) m_a2ImgH = v; }
            if (m_a2ImgW != static_cast<int>(kA2ImgW) || m_a2ImgH != static_cast<int>(kA2ImgH))
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] A2 DEBUG image size = %dx%d (default %dx%d). Higher res costs CPU/bandwidth"
                    " ONLY while the dashboard is open; still ~10 Hz capped.", m_a2ImgW, m_a2ImgH,
                    static_cast<int>(kA2ImgW), static_cast<int>(kA2ImgH));
            m_vlmLogPath       = makeVlmLogPath();
            std::error_code ec;
            std::filesystem::create_directories(kVlmPromptLogDir, ec);
            if (ec) {
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] VLM log dir create failed (%s): %s -- prompt log disabled.",
                    kVlmPromptLogDir, ec.message().c_str());
            }
        }
        RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] observability=%s.",
            mb_observability ? "ON" : "off");
    }

    static const char* flightStateName(FlightState st) {
        switch (st) {
            case FlightState::STANDBY: return "STANDBY";
            case FlightState::TAKEOFF: return "TAKEOFF";
            case FlightState::FLIGHT:  return "FLIGHT";
            case FlightState::LANDING: return "LANDING";
        }
        return "?";
    }

    /* PerceptionRuntime already drew the boxes/labels (it owns the detections); here we
       only wrap the BGR mat as a ROS image and publish it at the seg loop's native rate. */
    void publishAnnotatedFrame(cv::Mat const& bgr) {
        /* No subscriber (dashboard closed) -> do zero image work. With the bridge's on-demand
           subscriptions this means the resize + encode + publish only run while a browser is
           actually watching, so even a high debug resolution costs nothing when unwatched. */
        if (m_pubAnnotated->get_subscription_count() == 0) return;
        u64     now = nowUs();
        cv::Mat small;
        if (now - m_lastAnnUs < kImgThrottleUs) return;   /* ~10 Hz cap -- lean transport. */
        m_lastAnnUs = now;
        cv::resize(bgr, small, cv::Size{std::min(m_a2ImgW, bgr.cols), std::min(m_a2ImgH, bgr.rows)},
                   0, 0, cv::INTER_AREA);
        std_msgs::msg::Header hdr;
        hdr.stamp    = this->now();
        hdr.frame_id = "camera";
        m_pubAnnotated->publish(*cv_bridge::CvImage(hdr, "bgr8", small).toImageMsg());
        m_annPubs.fetch_add(1, kMemOrderRelax);
        return;
    }

    /* Normalize the metric-depth mat to 8-bit, colormap it, publish at the depth rate.
       patchNaNs first so a stray NaN cannot wreck the min/max normalization. */
    void publishDepthColormap(cv::Mat const& depth) {
        cv::Mat clean, norm, color, small;
        u64     now;
        if (depth.empty()) return;
        if (m_pubDepthColormap->get_subscription_count() == 0) return;   /* skip when unwatched. */
        now = nowUs();
        if (now - m_lastDepthUs < kImgThrottleUs) return;   /* throttle before the colormap work. */
        m_lastDepthUs = now;
        clean = depth.clone();
        cv::patchNaNs(clean, 0.0f);
        cv::normalize(clean, norm, 0, 255, cv::NORM_MINMAX, CV_8UC1);
        cv::applyColorMap(norm, color, cv::COLORMAP_TURBO);
        cv::resize(color, small, cv::Size{std::min(m_a2ImgW, color.cols), std::min(m_a2ImgH, color.rows)},
                   0, 0, cv::INTER_AREA);
        std_msgs::msg::Header hdr;
        hdr.stamp    = this->now();
        hdr.frame_id = "camera";
        m_pubDepthColormap->publish(*cv_bridge::CvImage(hdr, "bgr8", small).toImageMsg());
        m_depthPubs.fetch_add(1, kMemOrderRelax);
        return;
    }

    /* TASK field: the active command as a short verb (+ its target where one exists). */
    void hudTask(char* buf, size_t cap) {
        CmdApproach appr;
        CmdOrbit    orb;
        CmdSearch   srch;
        if (!m_hasActive) { std::snprintf(buf, cap, "idle"); return; }
        switch (m_currTask.m_cmd.id()) {
            case CommandID::TAKEOFF: std::snprintf(buf, cap, "takeoff"); return;
            case CommandID::LAND:    std::snprintf(buf, cap, "land");    return;
            case CommandID::STOP:    std::snprintf(buf, cap, "stop");    return;
            case CommandID::HOVER:   std::snprintf(buf, cap, "hover");   return;
            case CommandID::GO:      std::snprintf(buf, cap, "go");      return;
            case CommandID::CURVE:   std::snprintf(buf, cap, "curve");   return;
            case CommandID::ROTATE:  std::snprintf(buf, cap, "rotate");  return;
            case CommandID::REASSESS:std::snprintf(buf, cap, "reassess");return;
            case CommandID::APPROACH:
                appr = m_currTask.m_cmd.m_extractCmd.m_approach;
                std::snprintf(buf, cap, "approach(%s)", appr.target[0] ? appr.target : "?");
                return;
            case CommandID::FOLLOW:
                std::snprintf(buf, cap, "follow(%s)", m_followLabel[0] ? m_followLabel : "?");
                return;
            case CommandID::ORBIT:
                orb = m_currTask.m_cmd.m_extractCmd.m_orbitTarget;
                std::snprintf(buf, cap, "orbit(%s)", orb.target[0] ? orb.target : "?");
                return;
            case CommandID::SEARCH:
                srch = m_currTask.m_cmd.m_extractCmd.m_SearchTarget;
                std::snprintf(buf, cap, "search(%s)", srch.target[0] ? srch.target : "?");
                return;
            default: std::snprintf(buf, cap, "?"); return;
        }
    }

    /* DET field: top few detections as label@conf, or "-" when nothing is in view. */
    void hudDet(char* buf, size_t cap) {
        std::shared_ptr<PerceptionSnapshot> snap = m_perception->snapshot();
        u32    n, i;
        int    off;
        if (!snap || !snap->valid || snap->count == 0) { std::snprintf(buf, cap, "-"); return; }
        n   = std::min(snap->count, 3u);
        off = 0;
        for (i = 0; i < n && off < static_cast<int>(cap) - 1; ++i) {
            off += std::snprintf(buf + off, cap - off, "%s%s@%.0f%%",
                (i == 0) ? "" : ",", snap->dets[i].label, snap->dets[i].confidence * 100.0f);
        }
        return;
    }

    /* Build + emit the ~5Hz human-readable status: [FMU_HUD] log line AND /fmu/hud topic. */
    void publishHud(FlightState st, f32 altUp, Odometry const& od) {
        char               task[64], det[128], body[320];
        f32                vel;
        std_msgs::msg::String msg;
        hudTask(task, sizeof(task));
        hudDet(det, sizeof(det));
        vel = std::sqrt(od.vel.x * od.vel.x + od.vel.y * od.vel.y + od.vel.z * od.vel.z);
        std::snprintf(body, sizeof(body),
            "STATE=%s ALT=%.2fm TASK=%s VLM=%s DET=%s VEL=%.2fm/s BATT=%d%%",
            flightStateName(st), altUp, task,
            m_planning.load(kMemOrderRelax) ? "busy" : "idle",
            det, vel, effectiveBatteryPct());
        RCLCPP_INFO(this->get_logger(), "[FMU_HUD] %s", body);
        msg.data = body;
        m_pubHud->publish(msg);
        m_hudPubs.fetch_add(1, kMemOrderRelax);
        return;
    }

    /* Per-run log filename, computed once at construction: vlm_prompts_<YYYYMMDD_HHMMSS>.jsonl
       under kVlmPromptLogDir. Same timestamp idiom sim_core.sh uses for BAG_DIR, in C++. */
    std::string makeVlmLogPath() const {
        std::time_t t = std::time(nullptr);
        std::tm     tmv{};
        char        stamp[32];
        localtime_r(&t, &tmv);
        std::strftime(stamp, sizeof(stamp), "%Y%m%d_%H%M%S", &tmv);
        return std::string(kVlmPromptLogDir) + "/vlm_prompts_" + stamp + ".jsonl";
    }

    /* One JSON object per line. Image bytes are NOT inlined (they are live on the annotated
       topic) -- only image_attached + image_b64_bytes, to keep a long run's log small.
       Called on the single-flight planning thread (m_planning guards it), so no lock needed. */
    void appendVlmLog(bool imageAttached, size_t b64Bytes,
                      std::string const& prompt, std::string const& response) {
        nlohmann::json rec;
        std::ofstream  f(m_vlmLogPath, std::ios::app);
        if (!f) {
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] VLM prompt log open failed: %s", m_vlmLogPath.c_str());
            return;
        }
        rec["timestamp_us"]    = nowUs();
        rec["image_attached"]  = imageAttached;
        rec["image_b64_bytes"] = static_cast<u64>(b64Bytes);
        rec["prompt"]          = prompt;
        rec["response"]        = response;
        f << rec.dump() << '\n';
        return;
    }

    /* ---- Battery failsafe + manual override ------------------------------ */
    /* Live effective battery %: the test-only fault injection if armed (m_batteryForce != -2),
       else the backend's continuously-updated reading. Read ON DEMAND -- never cached, so a low
       battery can never be masked by a stale value. Cheap: one atomic load + the backend's atomic. */
    i32 effectiveBatteryPct() const {
        i32 bf = m_batteryForce.load(kMemOrderRelax);   /* -2 = inactive; else the forced %. */
        return (bf >= -1) ? bf : m_backend->battery_pct();
    }

    /* Returns true if the failsafe pre-empted this tick. battery % < 0
       (kBatteryReadingUnknown) means no trustworthy reading -> skip; a real 0 is
       empty and triggers. Latches so a wobbling reading can't oscillate the state. */
    bool batteryFailsafeTick() {
        i32 pct = effectiveBatteryPct();
        if (pct < 0)          return false;   /* UNKNOWN sentinel: never a false alarm. */
        if (mb_batteryReturn || mb_batteryLand) return false;   /* EITHER failsafe latched -> committed to a landing; don't re-evaluate (land-in-place must not then escalate to RTH). */

        if (pct <= m_cfg.batteryLandPct && !mb_batteryLand) {      /* critical -> land where we are. */
            mb_batteryLand = true;
            m_hasActive    = false;
            { ActiveTask stale; while (m_taskQueue->try_dequeue(stale)) { } }  /* drop the rest of the plan (consumer side); leftover actions must not run after we land. */
            m_flightState.store(FlightState::LANDING, kMemOrderRelax);
            m_missionActive.store(false, std::memory_order_release);
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] FAILSAFE battery %d%% -> LAND in place.", pct);
            return true;
        }
        if (pct <= m_cfg.batteryReturnPct && !mb_batteryReturn) {  /* low -> return to origin, then land. */
            mb_batteryReturn = true;
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] FAILSAFE battery %d%% -> RETURN to origin.", pct);
            returnToOrigin();
            return true;
        }
        return false;
    }

    /* Pre-empt the plan and fly a straight GO back to the takeoff point (ENU origin);
       the dispatch site then lands us there. Control-thread only; SPSC-safe -- we
       drain as the consumer and NEVER enqueue here. */
    void returnToOrigin() {
        Odometry   od = m_backend->odometry();
        ActiveTask stale;
        Vec3       homeFlu = enu_to_flu(Vec3{ -od.pos.x, -od.pos.y, 0.0f }, od.yaw);  /* hold altitude. */

        while (m_taskQueue->try_dequeue(stale)) { /* drop the stale VLM plan (consumer side). */ }
        m_missionActive.store(false, std::memory_order_release);   /* stop soliciting new plans. */

        CmdGo g{};
        g.x     = homeFlu.x * 100.0f;   /* CmdGo is body-FLU centimetres. */
        g.y     = homeFlu.y * 100.0f;
        g.z     = 0.0f;
        g.speed = 80.0f;                /* brisk 0.8 m/s return -- low battery, get home promptly. */

        ActiveTask home{};
        home.m_cmd   = GenericCommand(g);
        home.m_state = TaskState::PENDING;
        strncpy(home.m_thought, "battery failsafe: return to origin", sizeof(home.m_thought) - 1);

        /* A movement task only runs in the FLIGHT/STANDBY dispatch path. The failsafe can fire
           mid-TAKEOFF (weak battery never reached kTakeoffTargetAltEnu): that branch streams a
           climb and ignores the active task, so the RTH GO would never execute and the drone
           would hang forever with motors armed. Force FLIGHT so the GO runs -- and since we are
           still at the origin it completes at once, and the dispatch-site handoff lands us. */
        m_flightState.store(FlightState::FLIGHT, kMemOrderRelax);
        activateTask(home);
    }

    /* Operator override toggle (std_msgs/Bool). true = take manual control (pause
       autonomy); false = hand control back to the VLM, which re-plans from the
       current pose (it lost positional context while disengaged). */
    void overrideCallback(const std_msgs::msg::Bool::SharedPtr msg) {
        bool prev = m_manualOverride.exchange(msg->data, kMemOrderRelax);
        if (prev == msg->data) return;
        zeroManualVel();
        /* Manual control supersedes the interrupt reflex. Clear it on BOTH transitions so a
           pre-takeover interrupt cannot leave a stale [INTERRUPT]/[ESCALATION] in the post-handback
           re-plan (spec 1 x spec-3). Same control-state-from-callback pattern as the m_hasActive
           reset below (reentrant callback group; pre-existing race, tolerated for these resets). */
        resetInterruptState();

        if (msg->data) {
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] MANUAL OVERRIDE engaged -> autonomy paused, operator in control.");
            return;
        }
        /* Handback: abandon any active/queued task, resume autonomy, force a re-plan
           (the VLM lost positional context while disengaged -> plan fresh from here). */
        ActiveTask stale;
        while (m_taskQueue->try_dequeue(stale)) { }
        m_hasActive            = false;
        m_settleTicksRemaining = 0;
        m_lastPlanUs           = 0;   /* clear cooldown so maybePlan re-plans now. */
        m_missionActive.store(true, std::memory_order_release);
        RCLCPP_WARN(this->get_logger(),
            "[FMU_NODE_DEBUG] MANUAL OVERRIDE released -> autonomy resumes, VLM will re-plan.");
    }

    void zeroManualVel() {
        m_manualFwd.store(0.0f, kMemOrderRelax);
        m_manualLeft.store(0.0f, kMemOrderRelax);
        m_manualUp.store(0.0f, kMemOrderRelax);
        m_manualYaw.store(0.0f, kMemOrderRelax);
    }

    /* Full interrupt-reflex reset. A manual-override takeover or handback supersedes the reflex, so
       the post-handback re-plan must not inherit a stale interrupt / stash / storm from before the
       takeover (spec 1 1.5/6.3). */
    void resetInterruptState() {
        m_hasStashed          = false;
        m_interruptPending    = false;
        m_interruptEscalated  = false;
        m_lastInterruptReason = nullptr;
        m_userCommandText.clear();
        m_interruptRingIdx    = 0;
        for (u32 k = 0; k < kInterruptMaxRetries; ++k) m_interruptTimes[k] = 0;
        return;
    }

    /* Raw keylog [keycode, action]: Enter toggles manual override, and while engaged
       WASD=plane, arrows=alt/yaw, Space=hover as body-FLU velocity (ENU'd in controlLoop). */
    void keyCallback(const KeyboardRawInputType::SharedPtr msg) {
        if (msg->data.size() < 2) return;

        int  key  = msg->data[0];
        bool down = (msg->data[1] == __scast(int, KeyAction::PRESSED));
        bool up   = (msg->data[1] == __scast(int, KeyAction::RELEASED));
        if (!down && !up) return;                            /* ignore auto-repeat, etc. */

        /* Must precede the override gate, since this key is the only way to engage it. */
        /* Press only, and routed through overrideCallback so key and topic share one path. */
        if (key == __scast(int, KeyCodeEnum::Enter)) {
            if (!down) return;
            auto toggled  = std::make_shared<std_msgs::msg::Bool>();
            toggled->data = !m_manualOverride.load(kMemOrderRelax);
            overrideCallback(toggled);
            return;
        }
        if (!m_manualOverride.load(kMemOrderRelax)) return;

        const f32 kV   = m_cfg.manualTeleopVelCmS / 100.0f;   /* m/s per axis. */
        constexpr f32 kYaw = 0.6f;                           /* rad/s; TUNE in sim+real. */
        f32 on = down ? 1.0f : 0.0f;

        if      (key == __scast(int, KeyCodeEnum::W))          m_manualFwd.store(  kV  * on, kMemOrderRelax);
        else if (key == __scast(int, KeyCodeEnum::S))          m_manualFwd.store( -kV  * on, kMemOrderRelax);
        else if (key == __scast(int, KeyCodeEnum::A))          m_manualLeft.store( kV  * on, kMemOrderRelax);
        else if (key == __scast(int, KeyCodeEnum::D))          m_manualLeft.store(-kV  * on, kMemOrderRelax);
        else if (key == __scast(int, KeyCodeEnum::UpArrow))    m_manualUp.store(   kV  * on, kMemOrderRelax);
        else if (key == __scast(int, KeyCodeEnum::DownArrow))  m_manualUp.store(  -kV  * on, kMemOrderRelax);
        else if (key == __scast(int, KeyCodeEnum::LeftArrow))  m_manualYaw.store(  kYaw* on, kMemOrderRelax);
        else if (key == __scast(int, KeyCodeEnum::RightArrow)) m_manualYaw.store( -kYaw* on, kMemOrderRelax);
        else if (key == __scast(int, KeyCodeEnum::Space))      zeroManualVel();   /* hover. */
        return;
    }

    /* ---- Task lifecycle helpers ------------------------------------------ */
    /* Median-filter the approach range. The depth model is noisy (SITL: bounces 2-7m near the
       target); a single high spike would hold approach speed high and overshoot INTO the target.
       Median over the last few readings rejects those spikes. */
    void pushApproachRange(f32 r) {
        m_approachRangeHist[m_approachRangeCount % kApproachRangeMedianWindow] = r;
        ++m_approachRangeCount;
    }
    f32 medianApproachRange() const {
        u32 n = (m_approachRangeCount < kApproachRangeMedianWindow)
                    ? m_approachRangeCount : kApproachRangeMedianWindow;
        if (n == 0u) return 0.0f;
        f32 tmp[kApproachRangeMedianWindow];
        for (u32 i = 0u; i < n; ++i) tmp[i] = m_approachRangeHist[i];
        for (u32 i = 1u; i < n; ++i) {              /* insertion sort; n <= window (5) */
            f32 key = tmp[i];
            i32 j   = __scast(i32, i) - 1;
            while (j >= 0 && tmp[j] > key) { tmp[j + 1] = tmp[j]; --j; }
            tmp[j + 1] = key;
        }
        return tmp[n / 2u];
    }

    void pushOrbitRange(f32 r) {
        m_orbitRangeHist[m_orbitRangeCount % kApproachRangeMedianWindow] = r;
        ++m_orbitRangeCount;
    }
    f32 medianOrbitRange() const {
        u32 n = (m_orbitRangeCount < kApproachRangeMedianWindow) ? m_orbitRangeCount : kApproachRangeMedianWindow;
        if (n == 0u) return 0.0f;
        f32 tmp[kApproachRangeMedianWindow];
        for (u32 i = 0u; i < n; ++i) tmp[i] = m_orbitRangeHist[i];
        for (u32 i = 1u; i < n; ++i) {
            f32 key = tmp[i];
            i32 j   = __scast(i32, i) - 1;
            while (j >= 0 && tmp[j] > key) { tmp[j + 1] = tmp[j]; --j; }
            tmp[j + 1] = key;
        }
        return tmp[n / 2u];
    }

    void activateTask(ActiveTask const& task) {
        Odometry      od;
        Vec3          relFlu, relEnu;
        CmdGo         g;
        CmdRotate     r;
        CmdOrbit      orb;
        CmdSearch     srch;
        CommandID     id;
        BackendStatus s;

        m_currTask = task;
        m_currTask.m_state = TaskState::RUNNING;
        m_hasActive = true;
        /* A new task landed -> the interrupt reassess is resolved. Storm/escalation state is NOT
           cleared here; only a clean completion clears it, so a task that lands and immediately
           re-trips stays escalated (spec 1 1.5/6.3). */
        m_hasStashed       = false;
        m_interruptPending = false;
        id = m_currTask.m_cmd.id();

        switch (id) {
        case CommandID::TAKEOFF:
            s = m_backend->takeoff();  /* non-blocking; backend goes STANDBY->HANDSHAKING. */
            if (s.code == BackendStatus::Code::REJECTED) {
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] TAKEOFF rejected (backend not STANDBY, io=%d).",
                    __scast(int, m_backend->state()));
                completeCurrent("takeoff_rejected");
                break;
            }
            m_flightState.store(FlightState::TAKEOFF, kMemOrderRelax);
            RCLCPP_INFO(this->get_logger(),
                "[FMU_NODE_DEBUG] TAKEOFF activated; backend handshaking, FMU streaming climb.");
            break;
        case CommandID::LAND:
            m_backend->land();  /* PX4: no-op; FMU streams the descent. */
            m_flightState.store(FlightState::LANDING, kMemOrderRelax);
            RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] LAND activated; FMU streaming descent.");
            break;
        case CommandID::GO:
            g   = m_currTask.m_cmd.m_extractCmd.m_goto;
            od  = m_backend->odometry();
            /* VLM gives relative FLU in cm -> world-ENU target. */
            relFlu = { g.x / 100.0f, g.y / 100.0f, g.z / 100.0f };
            relEnu = flu_to_enu(relFlu, od.yaw);
            m_goStartN = od.pos.x;
            m_goStartE = od.pos.y;
            m_goStartD = od.pos.z;
            m_targetN  = od.pos.x + relEnu.x;
            m_targetE  = od.pos.y + relEnu.y;
            m_targetD  = od.pos.z + relEnu.z;
            /* Freeze the start->target line for cross-track guidance. */
            m_goTotalDist = std::sqrt(relEnu.x * relEnu.x + relEnu.y * relEnu.y + relEnu.z * relEnu.z);
            if (m_goTotalDist > kGoCompletionRadiusM) {
                m_goDirN = relEnu.x / m_goTotalDist;
                m_goDirE = relEnu.y / m_goTotalDist;
                m_goDirD = relEnu.z / m_goTotalDist;
            } else {
                m_goDirN = m_goDirE = m_goDirD = 0.0f;
            }
            m_activeSpeed = (g.speed > 0.0f ? g.speed : m_cfg.defaultGoSpeedCmS) / 100.0f;
            RCLCPP_INFO(this->get_logger(),
                "[FMU_NODE_DEBUG] GO activated. relFLU=(%.2f,%.2f,%.2f) targetENU=(%.2f,%.2f,%.2f) dirENU=(%.2f,%.2f,%.2f) speed=%.2f",
                relFlu.x, relFlu.y, relFlu.z, m_targetN, m_targetE, m_targetD,
                m_goDirN, m_goDirE, m_goDirD, m_activeSpeed);
            break;
        case CommandID::ROTATE:
            r   = m_currTask.m_cmd.m_extractCmd.m_rotateInPlace;
            od  = m_backend->odometry();
            /* Integrate actual rotation in the commanded direction until the full magnitude is
               swept -- so 270 cw really turns 270 cw and 360 does a full turn (not shortest-path). */
            m_rotateRemainingRad = std::fabs(__scast(f32, r.angle_deg)) * kPi / 180.0f;
            if (m_rotateRemainingRad > kRotateMaxAngleRad) m_rotateRemainingRad = kRotateMaxAngleRad;
            m_rotateDir     = r.cw_or_ccw ? -1.0f : 1.0f;  /* cw decreases yaw (ENU CCW+) */
            m_rotatePrevYaw = od.yaw;
            RCLCPP_INFO(this->get_logger(),
                "[FMU_NODE_DEBUG] ROTATE activated. angle_deg=%d dir=%s startYaw=%.2f remainRad=%.2f",
                r.angle_deg, r.cw_or_ccw ? "cw" : "ccw", od.yaw, m_rotateRemainingRad);
            break;
        case CommandID::APPROACH:
            m_approachHaveLastAim      = false;
            m_approachBboxRig          = false;
            m_approachActivateUs       = nowUs();
            m_approachRangeCount       = 0;
            m_approachBudgetLatched    = false;
            m_approachTravelBudget     = 0.0f;
            m_approachTrackId          = -1;
            {
                /* bind the VLM-chosen track id against the SAME frame the prompt used. */
                std::shared_ptr<TrackedSnapshot> at = std::atomic_load(&m_lastPromptTracked);
                if (!at) at = m_perception->trackedSnapshot();
                i32 wantId = m_currTask.m_cmd.m_extractCmd.m_approach.target_id;
                if (at && at->snap.valid && wantId >= 0)
                    for (u32 i = 0; i < at->ids.count; ++i)
                        if (at->ids.id[i] == wantId) { m_approachTrackId = wantId; break; }
            }
            m_cannedApproachActivateUs = nowUs();
            od     = m_backend->odometry();
            relFlu = { kCannedApproachTargetFwdM, 0.0f, kCannedApproachTargetUpM };
            relEnu = flu_to_enu(relFlu, od.yaw);
            m_cannedApproachTargetEnu = { od.pos.x + relEnu.x, od.pos.y + relEnu.y, od.pos.z + relEnu.z };
            {   /* VLM bbox present -> freeze the anchor on the boxed object and drive the servo off it
                   through the synthetic rig, so a non-COCO target (house/window) needs no YOLO box. */
                CmdApproach const& ap = m_currTask.m_cmd.m_extractCmd.m_approach;
                Vec3 anchorEnu;
                if (bboxToEnuAnchor(ap.bbox, od, anchorEnu)) {
                    /* Floor the anchor altitude: a low/hallucinated bbox can project UNDERGROUND
                       (seen: ENU z=-1.87) and the go-to servo then flies the drone into the ground. */
                    if (anchorEnu.z < kApproachMinAnchorAltEnu) anchorEnu.z = kApproachMinAnchorAltEnu;
                    m_cannedApproachTargetEnu = anchorEnu;
                    std::snprintf(m_cannedApproachLabel, sizeof(FixedStringType), "%s",
                                  ap.target[0] ? ap.target : kCannedApproachTargetLabel);
                    m_approachBboxRig = true;
                    RCLCPP_INFO(this->get_logger(),
                        "[FMU_NODE_DEBUG] APPROACH bbox-anchored target=%s ENU=(%.2f,%.2f,%.2f) (VLM bbox, no YOLO).",
                        m_cannedApproachLabel, anchorEnu.x, anchorEnu.y, anchorEnu.z);
                }
            }
            RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] APPROACH activated target=%s track_id=%d.",
                m_currTask.m_cmd.m_extractCmd.m_approach.target, m_approachTrackId);
            break;
        case CommandID::FOLLOW: {
            /* Resolve the VLM's target ONCE against the SAME frame the prompt was built from
               (m_lastPromptTracked) so we bind exactly what it saw. Prefer the stable track_id;
               fall back to the array target_index. Nearest-centroid tracks it from there. */
            CmdFollow fol     = m_currTask.m_cmd.m_extractCmd.m_follow;
            m_followHaveLast  = false;
            m_followLastAimUs = nowUs();
            m_followLabel[0]  = '\0';
            m_followTrackId   = -1;
            std::shared_ptr<TrackedSnapshot> ft = std::atomic_load(&m_lastPromptTracked);
            if (!ft) ft = m_perception->trackedSnapshot();
            i32 di = -1;
            if (ft && ft->snap.valid) {
                if (fol.target_id >= 0)
                    for (u32 i = 0; i < ft->ids.count; ++i)
                        if (ft->ids.id[i] == fol.target_id) { di = static_cast<i32>(i); break; }
                if (di < 0 && fol.target_index >= 0 &&
                    static_cast<u32>(fol.target_index) < ft->snap.count)
                    di = fol.target_index;
            }
            /* Robustness: the 2B VLM often emits a track_id that is NOT present (e.g. 0/1/10), which
               would fail as follow_no_target and loop forever. If neither id nor index resolved, fall
               back to the detection NEAREST FRAME CENTRE -- the obvious intended follow target. Single-
               target follow then never needs a correct id; a crowd gets the centre person as a sane
               default. A valid id, when the VLM does supply one, is still honoured above. */
            if (di < 0 && ft && ft->snap.valid && ft->snap.count > 0) {
                f32 bestD = 1e18f; i32 bestI = -1;
                for (u32 i = 0; i < ft->snap.count; ++i) {
                    f32 ccx = 0.5f * static_cast<f32>(ft->snap.dets[i].bbox_xmin + ft->snap.dets[i].bbox_xmax);
                    f32 ccy = 0.5f * static_cast<f32>(ft->snap.dets[i].bbox_ymin + ft->snap.dets[i].bbox_ymax);
                    f32 dxp = ccx - kApproachCamera.cx, dyp = ccy - kApproachCamera.cy;
                    f32 dd  = dxp * dxp + dyp * dyp;
                    if (dd < bestD) { bestD = dd; bestI = static_cast<i32>(i); }
                }
                di = bestI;
                RCLCPP_INFO(this->get_logger(),
                    "[FMU_NODE_DEBUG] FOLLOW track_id=%d/index=%d unresolved -> centre-detection fallback idx=%d.",
                    fol.target_id, fol.target_index, di);
            }
            if (di >= 0) {
                TargetDetection const& d = ft->snap.dets[di];
                strncpy(m_followLabel, d.label, sizeof(m_followLabel) - 1);
                m_followLastU   = 0.5f * static_cast<f32>(d.bbox_xmin + d.bbox_xmax);
                m_followLastV   = 0.5f * static_cast<f32>(d.bbox_ymin + d.bbox_ymax);
                m_followTrackId = (static_cast<u32>(di) < ft->ids.count) ? ft->ids.id[di] : -1;
                m_followHaveLast = true;
                m_followHaveErr  = false;   /* fresh lock -> no prior errX to reject against. */
                RCLCPP_INFO(this->get_logger(),
                    "[FMU_NODE_DEBUG] FOLLOW activated track_id=%d target_index=%d label=%s centerPx=(%.0f,%.0f) standoff_cm=%d.",
                    m_followTrackId, fol.target_index, m_followLabel, m_followLastU, m_followLastV, fol.standoff_cm);
            } else {
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] FOLLOW activated but neither track_id=%d nor target_index=%d resolved -> hover until a lock.",
                    fol.target_id, fol.target_index);
            }
            break;
        }
        case CommandID::ORBIT:
            orb                = m_currTask.m_cmd.m_extractCmd.m_orbitTarget;
            od                 = m_backend->odometry();
            m_orbitSpeed       = (orb.speed > 0.0f) ? orb.speed / 100.0f : m_cfg.orbitDefaultSpeedMps;
            m_orbitDir         = orb.cw_or_ccw ? -1.0f : 1.0f;   /* ccw = +1 (math positive), cw = -1. SITL-verify. */
            m_orbitTargetRad   = std::fabs(orb.angle_deg) * kPi / 180.0f;
            m_orbitSweptRad    = 0.0f;
            m_orbitLatched     = false;
            m_orbitRangeCount  = 0;
            m_orbitAltEnu      = od.pos.z;
            m_orbitStartUs     = nowUs();
            m_orbitLastSeenUs  = nowUs();
            RCLCPP_INFO(this->get_logger(),
                "[FMU_NODE_DEBUG] ORBIT activated target=%s speed=%.2f angle=%.2f dir=%s (odometry circle, camera on target)",
                orb.target, m_orbitSpeed, m_orbitTargetRad, orb.cw_or_ccw ? "cw" : "ccw");
            break;
        case CommandID::SEARCH:
            srch                  = m_currTask.m_cmd.m_extractCmd.m_SearchTarget;
            od                    = m_backend->odometry();
            m_searchStartPos       = od.pos;
            m_searchOriginPos      = od.pos;
            m_searchReturning      = false;
            m_searchAltEnu         = (od.pos.z > 3.0f) ? 3.0f : od.pos.z;   /* hold a LOW search altitude:
                                     from ~5m up a ground person is tiny in frame and YOLO confidence collapses, so
                                     clamp the search to a height where people are actually detectable. */
            {
                /* Blind-search reach: a search issued while the drone sees NOTHING (DET=-) must cover
                   enough ground to bring a far target into YOLO range. The 2B VLM tends to pick 'small'
                   (reach ~2m), stranding the drone short of a person 12m+ away; the empty search then
                   feeds a hallucinated approach. When perception is empty at activation, promote to
                   LARGE (reach ~24m). Once anything is in view, the VLM-chosen size is respected. */
                std::shared_ptr<TrackedSnapshot> st = std::atomic_load(&m_lastPromptTracked);
                if (!st) st = m_perception->trackedSnapshot();
                bool blind = !(st && st->snap.valid && st->snap.count > 0);
                if (blind && srch.size < 2) {
                    RCLCPP_INFO(this->get_logger(),
                        "[FMU_NODE_DEBUG] SEARCH blind (no detections) -> promoting size %u to LARGE for reach.",
                        (unsigned)srch.size);
                    srch.size = 2;
                }
            }
            m_searchLaneHeadingRad = wrap_pi(od.yaw + __scast(f32, srch.start_heading_deg) * kPi / 180.0f);
            m_searchDir            = srch.cw_or_ccw ? -1.0f : 1.0f;   /* which side the lanes march. */
            m_searchCrossHeadingRad= wrap_pi(m_searchLaneHeadingRad + m_searchDir * 0.5f * kPi);
            m_searchStartUs        = nowUs();
            m_searchLegStartUs     = m_searchStartUs;
            {
                /* Floor the timeout: a too-short VLM timeout_sec (it emitted 10) gives up after ~one
                   scan, before the search advances far enough to reach the target. */
                u64 tmoS = (srch.timeout > 0) ? static_cast<u64>(srch.timeout) : 60ULL;
                if (tmoS < 45ULL) tmoS = 45ULL;
                m_searchTimeoutUs = tmoS * 1000000ULL;
            }
            m_searchCrossing       = false;
            m_searchLegCount       = 0;
            m_searchParams          = kSearchSizePresets[srch.size < 3 ? srch.size : kSearchDefaultSizeIdx];
            if (mb_cfgActive) {
                /* A loaded profile overrides the size preset lane geometry with the per-drone
                   tuned values (indoor lanes are far shorter); maxLanes stays from the VLM-chosen
                   size. No profile -> preset used verbatim, so SITL is byte-identical. */
                m_searchParams.laneLengthM  = m_cfg.searchLaneLengthM;
                m_searchParams.laneSpacingM = m_cfg.searchLaneSpacingM;
                m_searchParams.legTimeoutMs = m_cfg.searchLegTimeoutMs;
            }
            m_searchMaxLegs        = m_searchParams.maxLanes;
            /* advance-and-scan: begin with a 360 scan at the origin (look around before moving), then
               advance step_m and scan again, up to maxDist total. step/maxDist scale with size. The
               advance heading is m_searchLaneHeadingRad (= yaw + start_heading_deg, default forward). */
            m_searchScanning         = true;
            m_searchScanRemainingRad = 2.0f * kPi;
            m_searchScanPrevYaw      = od.yaw;
            m_searchTotalDistM       = 0.0f;
            switch (srch.size) {
                case 0:  m_searchStepM = 0.5f; m_searchMaxDistM = 8.0f;  break;   /* small: fine steps, tight area */
                case 2:  m_searchStepM = 3.0f; m_searchMaxDistM = 30.0f; break;   /* large: coarse steps, open area */
                default: m_searchStepM = 1.5f; m_searchMaxDistM = 18.0f; break;   /* medium (default) */
            }
            RCLCPP_INFO(this->get_logger(),
                "[FMU_NODE_DEBUG] SEARCH activated (advance-and-scan) target=%s alt=%.2f headingDeg=%d (0=fwd) "
                "dir=%s timeout_s=%d step=%.1fm maxDist=%.1fm",
                srch.target, m_searchAltEnu, srch.start_heading_deg, srch.cw_or_ccw ? "cw" : "ccw",
                srch.timeout, m_searchStepM, m_searchMaxDistM);
            break;
        case CommandID::HOVER:
            RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] HOVER activated -> holding station (persistent).");
            break;
        default:
            RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] task id=%d auto-completes.",
                __scast(int, id));
            break; /* STOP / others auto-complete in controlLoop. */
        }
    }

    void completeCurrent(const char* status) {
        strncpy(m_currTask.m_status, status, sizeof(m_currTask.m_status) - 1);
        m_currTask.m_state = TaskState::FINISHED_SUCCESS;
        m_chat.m_completedTasks.push_back(m_currTask);
        publishVlmContext();   /* refresh the dashboard executed-command list. */
        m_hasActive = false;
        /* A task completed cleanly -> the interrupt storm (if any) is resolved. Reset the
           detector so a later, unrelated trip starts a fresh count (spec 1 6.3). */
        m_interruptEscalated = false;
        for (u32 k = 0; k < kInterruptMaxRetries; ++k) m_interruptTimes[k] = 0;
        m_interruptRingIdx = 0;
        m_settleTicksRemaining = kGoSettleTicks;
        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
        RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] task complete status=%s total=%zu",
            status, m_chat.m_completedTasks.size());

        /* Deterministic close-out: the instant an APPROACH finishes, LAND -- do not hand back to a
           weak planner that may skip the land. Completes "approach the target and land near it"
           without a second dependence on the 2B. Land completion has id==LAND, so this never loops. */
        if (m_currTask.m_cmd.id() == CommandID::APPROACH) {
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] APPROACH finished (%s) -> auto-land.", status);
            ActiveTask landTask{};
            landTask.m_cmd = GenericCommand(CmdLand{});
            std::snprintf(landTask.m_thought, sizeof(landTask.m_thought), "approached target -> landing");
            activateTask(landTask);
        }
    }

    /* Interrupt core (spec 1 1.5/6.3): the one reflex every trigger shares -- STOP (hover), stash
       the active task, arm the reassess context, detect an interrupt storm, hold. Resume is
       implicit: the next VLM plan enqueues normally; the stash is surfaced in the prompt
       (buildDynamicPrompt), not replayed. Control-thread only. */
    void raiseInterrupt(const char* reason) {
        u64 now, oldest;

        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);   /* immediate hover/STOP. */
        if (m_hasActive) {
            m_stashedTask = m_currTask;
            m_hasStashed  = true;
            m_hasActive   = false;
        }
        m_lastInterruptReason = reason;
        m_interruptPending    = true;

        /* Storm: N interrupts inside the window means hovering and re-planning the same way keeps
           tripping -- escalate so the reassess reasons about the root cause. O(1): compare now to
           the time kInterruptMaxRetries interrupts ago (the slot about to be overwritten). */
        now    = nowUs();
        oldest = m_interruptTimes[m_interruptRingIdx];
        m_interruptTimes[m_interruptRingIdx] = now;
        m_interruptRingIdx = (m_interruptRingIdx + 1) % kInterruptMaxRetries;
        if (oldest != 0 && (now - oldest) <= __scast(u64, kInterruptStormWindowMs) * 1000ULL) {
            m_interruptEscalated = true;
        }

        RCLCPP_WARN(this->get_logger(),
            "[FMU_NODE_DEBUG] INTERRUPT (reason=%s): stashed=%s escalated=%d hover+reassess",
            reason, m_hasStashed ? m_stashedTask.m_thought : "none",
            __scast(int, m_interruptEscalated));
        return;
    }

    /* ---- VLM plumbing (invoked by the Phase-2 event-driven wake, not a poll) ---- */
    /* A2: publish the mission objective + executed-command history (with status) as JSON on
       /fmu/vlm_context. This is the SAME context buildDynamicPrompt() feeds the model -- the
       dashboard shows what the VLM was told, not just its reply. Obs-gated, event-driven
       (mission start + each task completion). */
    void publishVlmContext() {
        if (!mb_observability || !m_pubVlmContext) return;
        nlohmann::json j;
        j["objective"] = m_chat.m_initialCommand;
        j["history"]   = nlohmann::json::array();
        for (size_t i = 0; i < m_chat.m_completedTasks.size(); ++i) {
            ActiveTask const& t = m_chat.m_completedTasks[i];
            j["history"].push_back({
                {"cmd",     cmdName(t.m_cmd.id())},
                {"status",  std::string(t.m_status)},
                {"thought", std::string(t.m_thought)},
            });
        }
        std_msgs::msg::String msg;
        msg.data = j.dump();
        m_pubVlmContext->publish(msg);
    }

    std::string buildDynamicPrompt() {
        std::string prompt;
        char        buf[256];
        size_t      i;

        prompt  = std::string(kSystemPrompt) + "\n\n";
        prompt += "[COORDINATE FRAME]\nFLU (+X Forward, +Y Left, +Z Up)\n\n";
        prompt += "[MISSION OBJECTIVE]\n" + m_chat.m_initialCommand + "\n\n";

        Odometry od = m_backend->odometry();
        bool      airborne = od.pos.z > 0.3f;
        snprintf(buf, sizeof(buf),
            "[VEHICLE STATE]\nalt_up_m=%.2f speed_mps=%.2f airborne=%s\n%s\n\n",
            od.pos.z, std::sqrt(od.vel.x * od.vel.x + od.vel.y * od.vel.y),
            airborne ? "true" : "false",
            airborne ? "" : "NOT AIRBORNE -- your plan MUST start with {\"action\":\"takeoff\"}.");
        prompt += buf;

        /* Perception JSON (ARCH sec 6): label/bbox/median_depth from the latest
           PerceptionSnapshot. median_depth_cm can lag bbox by up to one depth
           cycle (PerceptionRuntime is two-rate) -- closes ROADMAP 3.4. */
        prompt += "[PERCEPTION]\n";
        /* Use the tracked snapshot so each detection carries its STABLE track_id, and freeze
           this exact frame (m_lastPromptTracked) so the verb binds the object the VLM saw --
           not a split-second-newer frame at activation. */
        std::shared_ptr<TrackedSnapshot> tracked = m_perception->trackedSnapshot();
        bool haveDet = tracked && tracked->snap.valid && tracked->snap.count > 0;
        bool coasted = false;
        if (haveDet) {
            std::atomic_store(&m_lastNonEmptyTracked, tracked);
            m_lastNonEmptyUs.store(nowUs(), kMemOrderRelax);
            m_everSawDetection.store(true, kMemOrderRelax);
        } else {
            auto lastNE = std::atomic_load(&m_lastNonEmptyTracked);
            if (lastNE && (nowUs() - m_lastNonEmptyUs.load(kMemOrderRelax)) <= kPerceptionCoastUs) {
                /* Blank current frame, but detection flickers and the tracker coasts a lost target for
                   ~15 frames. Feed the VLM the last-seen frame (marked stale) rather than "(no
                   detections)", which made it abandon a target that is actually right in front. */
                tracked = lastNE; haveDet = true; coasted = true;
            }
        }
        std::atomic_store(&m_lastPromptTracked, tracked);
        if (coasted)
            prompt += "(momentary detection gap: the target below was seen a fraction of a second ago and "
                      "is still in front of you -- do NOT start a new search; follow/approach it)\n";
        if (haveDet) {
            PerceptionSnapshot const& psnap = tracked->snap;
            for (u32 t = 0; t < psnap.count; ++t) {
                const TargetDetection& det = psnap.dets[t];
                i32 tid = (t < tracked->ids.count) ? tracked->ids.id[t] : -1;
                snprintf(buf, sizeof(buf),
                    "{\"track_id\":%d, \"index\":%d, \"label\":\"%s\", \"bbox\":[%d,%d,%d,%d], \"confidence\":%.2f, \"median_depth_cm\":%.1f}\n",
                    tid, t, det.label, det.bbox_xmin, det.bbox_ymin, det.bbox_xmax, det.bbox_ymax,
                    det.confidence, det.median_depth_cm);
                prompt += buf;
            }
        } else {
            prompt += "(no detections)\n";
        }
        prompt += "\n";

        if (m_interruptPending) {
            snprintf(buf, sizeof(buf),
                "[INTERRUPT]\nreason=%s\ninterrupted: %s\n\n",
                m_lastInterruptReason ? m_lastInterruptReason : "unknown",
                m_hasStashed ? m_stashedTask.m_thought : "");
            prompt += buf;
        }
        /* [USER] block (A3): the operator's spoken in-flight command, surfaced to the VLM so it
           reassesses against the running objective. One-shot: gated on the still-pending
           user_command interrupt, which activateTask() clears when the reassess plan lands. */
        if (m_interruptPending && m_lastInterruptReason &&
            std::strcmp(m_lastInterruptReason, "user_command") == 0 && !m_userCommandText.empty()) {
            snprintf(buf, sizeof(buf), "[USER]\nspoken command: %s\n\n", m_userCommandText.c_str());
            prompt += buf;
        }
        if (m_interruptEscalated) {
            prompt += "[ESCALATION]\n";
            prompt += "You have tripped repeated safety interrupts in a short window "
                      "(interrupt storm). Hovering and re-planning the same way is NOT "
                      "working. Reason carefully about the ROOT CAUSE of the repeated "
                      "trips, then produce a creative plan to leave this situation and "
                      "resume the mission -- do NOT re-issue the action that keeps "
                      "tripping.\n\n";
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] ESCALATION block added to reassess prompt (interrupt storm).");
        }

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

    void callLlamaServer(std::string_view userQuery, khCameraPipelineMsgType const& img,
                         std::string& out) {
        std::string               b64, content, dyn;
        bool                      imageAttached = false;
        size_t                    b64Bytes      = 0;
        OptionalHttpRequestFuture  fut;
        nlohmann::json            j;
        cv::Mat                   frame, resized;
        std::vector<uchar>        buffer;
        std::vector<int>          params;

        params = { cv::IMWRITE_JPEG_QUALITY, 75 };
        if (img) {                               /* text-only plan when no camera frame yet. */
            frame = cv_bridge::toCvShare(img, "bgr8")->image;
            if (!frame.empty()) {
                cv::resize(frame, resized, cv::Size{640, 640}, 0, 0, cv::INTER_LINEAR);
                cv::imencode(".jpg", resized, buffer, params);
                b64 = base64_encode(buffer.data(), buffer.size());
            }
        }

        dyn = buildDynamicPrompt();
        imageAttached = static_cast<bool>(img) && !b64.empty();
        b64Bytes      = b64.size();
        RCLCPP_INFO(this->get_logger(),
            "[FMU_NODE_DEBUG] VLM request: image=%s b64Bytes=%zu promptChars=%zu",
            imageAttached ? "yes" : "no", b64.size(), dyn.size());
        fut = m_vlmClient.send(dyn, userQuery, b64, /*requireTakeoffFirst=*/m_flightState.load(kMemOrderRelax) == FlightState::STANDBY);
        if (!fut.has_value()) {
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] VLM submit returned nullopt (HTTP client not ready).");
            if (mb_observability) appendVlmLog(imageAttached, b64Bytes, dyn, content);
            out = content;
            return;
        }
        auto res = fut->get();
        if (!res) {
            RCLCPP_WARN(this->get_logger(), "[FMU_NODE_DEBUG] VLM HTTP error: %s",
                httplib::to_string(res.error()).c_str());
        } else if (res->status != 200) {
            RCLCPP_WARN(this->get_logger(), "[FMU_NODE_DEBUG] VLM HTTP status=%d body=%.240s",
                res->status, res->body.c_str());
        } else {
            j = nlohmann::json::parse(res->body, nullptr, false);
            if (j.is_discarded() || !j.contains("choices")) {
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] VLM 200 but body not as expected: %.240s", res->body.c_str());
            } else {
                content = j["choices"][0]["message"]["content"];
                /* Only the char count was ever logged here -- made every parse failure
                   undebuggable without re-running and adding prints by hand. Log the real
                   text (bounded, RCLCPP_INFO handles embedded newlines fine). */
                RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] VLM raw response: %.2000s",
                    content.c_str());
                if (mb_observability && m_pubVlmText) {   /* A2: surface reasoning on /fmu/vlm_text. */
                    std_msgs::msg::String vmsg;
                    m_lastVlmText = content;
                    vmsg.data     = content;
                    m_pubVlmText->publish(vmsg);
                }
            }
        }
        if (mb_observability) appendVlmLog(imageAttached, b64Bytes, dyn, content);
        out = content;
    }

    void translateToBaseCommands(std::string_view flightPlan) {
        nlohmann::json plan;
        std::string    action, thought, arr, sizeStr, firstAction;
        GenericCommand cmd;
        ActiveTask     task;
        CmdGo          go;
        CmdApproach    approach;
        CmdFollow      follow;
        CmdRotate      rot;
        CmdOrbit       orbit;
        CmdSearch      search;
        Odometry       od;
        bool           airborne;

        arr  = extractJsonArray(flightPlan);  /* strip ```json fences / prose from the VLM. */
        plan = nlohmann::json::parse(arr, nullptr, false);
        if (plan.is_discarded() || !plan.is_array()) {
            RCLCPP_WARN(this->get_logger(), "[FMU_NODE_DEBUG] plan JSON parse failed / not array.");
            return;
        }

        if (plan.size() > kMaxPlanActions) {
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] VLM plan has %zu actions (cap=%u); overflow dropped by backpressure.",
                plan.size(), kMaxPlanActions);
        }

        /* 2026-08-10: found live -- a plan whose OWN thought text correctly said "not airborne,
           need to take off first" still emitted takeoff as its 3rd action, not its 1st. Nothing
           enforced the model's stated reasoning against its actual output order. Result: earlier
           queued movement commands (SEARCH/APPROACH/...) ran first while grounded and disarmed,
           and takeoff was never reached -- APPROACH in particular has no timeout on a flickering
           lost/reacquired target, so this hung forever. Reject the WHOLE plan (same path as a
           JSON-parse failure: discard, let queue-empty immediately re-wake the VLM) if not
           airborne and the first real action (skipping the leading {"thought":...} object, which
           has no "action" key) is not takeoff. Deliberately NOT "last must be land" -- that would
           break the normal multi-cycle pattern (search -> reassess -> approach -> land is several
           separate plans, not one) and would fight the interrupt-reassess path, where the drone
           is already airborne and forcing a fresh takeoff would be nonsensical -- conditioning on
           !airborne already excludes that case. See docs/NOTES.md. */
        od       = m_backend->odometry();
        airborne = od.pos.z > 0.3f;
        if (!airborne) {
            for (const auto& item : plan) {
                if (item.contains("action")) {
                    firstAction = item.value("action", std::string(""));
                    break;
                }
            }
            if (!firstAction.empty() && firstAction != "takeoff") {
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] plan rejected: not airborne and first action is '%s', not "
                    "takeoff -- discarding whole plan, re-asking VLM.", firstAction.c_str());
                return;
            }
        }

        /* Completion verdict (A3): the VLM judges its own completion on the FIRST array element
           ({"thought":..., "objective_complete": bool, "reason": ...}). Default false via .value()
           so any response missing the field behaves exactly as before -- no silent auto-land. When
           true, stand down deterministically (land if airborne, else stop) and process no further
           actions this plan. */
        if (!plan.empty() && plan[0].is_object() && plan[0].value("objective_complete", false)) {
            std::string vreason = plan[0].value("reason", std::string(""));
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] VLM verdict objective_complete=true (%s) -> stand down (%s).",
                vreason.c_str(), airborne ? "land" : "stop");
            ActiveTask done{};
            done.m_cmd   = airborne ? GenericCommand(CmdLand{}) : GenericCommand(CmdStop{});
            done.m_state = TaskState::PENDING;
            strncpy(done.m_thought, vreason.empty() ? "objective complete" : vreason.c_str(),
                    sizeof(done.m_thought) - 1);
            m_taskQueue->try_enqueue(done);
            m_missionActive.store(false, std::memory_order_release);   /* mission ends; don't re-solicit. */
            return;
        }

        for (const auto& item : plan) {
            if (!item.contains("action")) continue;
            action  = item["action"].get<std::string>();
            thought = item.value("thought", "");

            switch (commandIdFromAction(action)) {
            case CommandID::TAKEOFF:
                cmd = GenericCommand(CmdTakeoff{});
                break;
            case CommandID::LAND:
                cmd = GenericCommand(CmdLand{});
                break;
            case CommandID::STOP:
                cmd = GenericCommand(CmdStop{});
                break;
            case CommandID::HOVER:
                cmd = GenericCommand(CmdHover{});
                break;
            case CommandID::GO:
                go  = { item.value("x", 0.0f), item.value("y", 0.0f),
                        item.value("z", 0.0f), item.value("speed", 0.0f) };
                /* A zero-vector go does nothing. DROP it -- never enqueue, and never convert it to a
                   persistent hover, which would STARVE any follow/approach queued after it (that made
                   the drone hover forever instead of following). Skip and keep the rest of the plan. */
                if (go.x == 0.0f && go.y == 0.0f && go.z == 0.0f) {
                    RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] dropping zero-go no-op (kept plan tail).");
                    continue;
                }
                cmd = GenericCommand(go);
                break;
            case CommandID::ROTATE:
                rot = CmdRotate{};
                rot.angle_deg = item.value("angle_deg", 0);
                rot.cw_or_ccw = (item.value("direction", std::string("cw")) == "cw");
                cmd = GenericCommand(rot);
                break;
            case CommandID::APPROACH:
                approach = CmdApproach{};
                strncpy(approach.target, item.value("target_object", "").c_str(),
                    sizeof(approach.target) - 1);
                approach.target_id = item.value("track_id", -1);
                approach.speed = item.value("speed", 0.0f);
                if (item.contains("bbox") && item["bbox"].is_array() && item["bbox"].size() == 4)
                    for (int bi = 0; bi < 4; ++bi)
                        approach.bbox[bi] = static_cast<i16>(item["bbox"][bi].get<double>());
                cmd = GenericCommand(approach);
                break;
            case CommandID::FOLLOW:
                follow = CmdFollow{};
                follow.target_index = item.value("target_index", -1);
                follow.target_id    = item.value("track_id", -1);
                follow.standoff_cm  = item.value("standoff_cm", 0);
                follow.speed        = item.value("speed", 0);
                cmd = GenericCommand(follow);
                break;
            case CommandID::ORBIT:
                orbit = CmdOrbit{};
                strncpy(orbit.target, item.value("target_object", "").c_str(),
                    sizeof(orbit.target) - 1);
                orbit.radius    = item.value("radius_cm", 0.0f);   /* raw; dispatch converts cm->m.  */
                orbit.angle_deg = item.value("angle_deg", 0.0f);   /* raw; dispatch converts deg->rad. */
                orbit.speed     = item.value("speed", 0.0f);       /* raw; dispatch converts cm/s->m/s. */
                orbit.cw_or_ccw = (item.value("direction", std::string("ccw")) == "cw");
                if (item.contains("bbox") && item["bbox"].is_array() && item["bbox"].size() == 4)
                    for (int bi = 0; bi < 4; ++bi)
                        orbit.bbox[bi] = static_cast<i16>(item["bbox"][bi].get<double>());
                cmd = GenericCommand(orbit);
                break;
            case CommandID::SEARCH:
                search = CmdSearch{};
                strncpy(search.target, item.value("target_object", "").c_str(),
                    sizeof(search.target) - 1);
                search.target_id = item.value("track_id", -1);
                search.expected_time = item.value("expected_search_time_sec", 0);
                search.timeout       = item.value("timeout_sec", 0);
                search.start_heading_deg = item.value("start_heading_deg", 0);
                search.cw_or_ccw     = (item.value("direction", std::string("ccw")) == "cw");
                sizeStr = item.value("search_size", std::string("medium"));
                search.size = (sizeStr == "small") ? 0 : (sizeStr == "large") ? 2 : kSearchDefaultSizeIdx;
                cmd = GenericCommand(search);
                break;
            default:
                continue; /* unknown action (also CURVE/REASSESS -- internal, never emitted). */
            }

            task = ActiveTask{};
            task.m_cmd   = cmd;
            task.m_state = TaskState::PENDING;
            strncpy(task.m_thought, thought.c_str(), sizeof(task.m_thought) - 1);
            if (!m_taskQueue->try_enqueue(task)) {   /* bounded: reject-newest on full. */
                ++m_taskDropCount;
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] BACKPRESSURE queue full (cap=%u) -> dropped task (total=%llu).",
                    3u * kControlLoopRateHz, __scast(unsigned long long, m_taskDropCount));
            }
        }
    }

    /* Scenario is the SAME JSON the VLM emits, routed through the real       */
    /* translate path — no inverse function needed.                             */
    /* Replay a canned test scenario: pre-fill the queue with its scripted JSON (test/
       fmu_test_scenarios.hpp) and, for the fault-injection scenarios, arm the synthetic condition the
       control loop acts on (flood/obstacle/battery). None is a no-op (a normal VLM-driven run).
       The scenario DATA lives in test/*; only the node-owned member arming lives here.
       DEFINED out-of-line in fmu_node.cpp (below main) -- SITL/test wiring stays out of the header. */
    void runTestScenario(TestScenario test);

private:
    rclcpp::CallbackGroup::SharedPtr                m_cbGroup;
    rclcpp::Subscription<CameraPipelineMsgType>::SharedPtr  m_subImg;
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr    m_subOverride;  /* operator override toggle. */
    rclcpp::Subscription<KeyboardRawInputType>::SharedPtr   m_subKey;       /* raw keylog for manual flight. */
    rclcpp::Subscription<ASRTextType>::SharedPtr            m_subAsr;       /* voice objective / in-flight re-task. */
    /* Battery failsafe + manual-override state (control-thread latches + cross-thread atomics). */
    bool              mb_batteryReturn{false};   /* RTH latched: fly home, then land.     */
    bool              mb_batteryLand{false};     /* land latched (in-place or after RTH). */
    u64               m_taskDropCount{0};        /* backpressure drops (diagnostics).     */
    std::atomic<bool> m_manualOverride{false};
    std::atomic<f32>  m_manualFwd{0.0f}, m_manualLeft{0.0f}, m_manualUp{0.0f}, m_manualYaw{0.0f};
    rclcpp::TimerBase::SharedPtr                    m_controlTimer;

    std::unique_ptr<ActiveBackend>                  m_backend;

    std::unique_ptr<spsc_queue<ActiveTask>>         m_taskQueue;
    ActiveTask                                      m_currTask;
    bool                                            m_hasActive{false};
    u32                                             m_settleTicksRemaining{0};

    /* Interrupt core (spec 1 1.5): the pre-empted task is stashed, not auto-resumed -- the
       reassess owns whether to re-issue it. Written only on the control thread. */
    ActiveTask                                      m_stashedTask{};
    bool                                            m_hasStashed{false};
    std::string                                     m_userCommandText;        /* A3: [USER] block text (control-thread owned). */
    std::atomic<bool>                               m_asrPending{false};      /* ASR posted a transcript; controlLoop drains it. */
    std::string                                     m_asrPendingText;         /* transcript payload, guarded by m_asrMtx. */
    std::mutex                                      m_asrMtx;
    bool                                            m_interruptPending{false};
    const char*                                     m_lastInterruptReason{nullptr};

    /* Interrupt storm detector (spec 1 6.3): a fixed ring of the last kInterruptMaxRetries
       interrupt times; N within kInterruptStormWindowMs -> escalate the reassess. O(1). */
    u64                                             m_interruptTimes[kInterruptMaxRetries]{};
    u32                                             m_interruptRingIdx{0};
    bool                                            m_interruptEscalated{false};

    llamaClientConnection                           m_vlmClient;
    khCameraPipelineMsgType                                 m_currImg;
    HistoryBuffer                                   m_chat;
    std::unique_ptr<PerceptionRuntime>               m_perception;

    /* A2 observability (additive): image + HUD publishers, per-run VLM log path, HUD throttle. */
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr  m_pubAnnotated;     /* /fmu/perception/annotated. */
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr  m_pubDepthColormap; /* /fmu/perception/depth.     */
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr    m_pubHud;           /* /fmu/hud text status.      */
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr    m_pubVlmText;       /* /fmu/vlm_text reasoning.   */
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr    m_pubVlmContext;    /* /fmu/vlm_context obj+hist. */
    std::string                                           m_vlmLogPath;       /* per-run prompt/response log.*/
    std::string                                           m_lastVlmText;      /* latest VLM text (cache).   */
    u64                                                    m_lastHudUs{0};     /* ~5Hz HUD throttle gate.    */
    u64                                                    m_lastAnnUs{0};     /* ~10Hz annotated throttle.  */
    u64                                                    m_lastDepthUs{0};   /* ~10Hz depth throttle.      */
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr    m_pubRates;         /* /fmu/rates JSON.           */
    std::atomic<u32>                                       m_annPubs{0};       /* annotated publishes/win.   */
    std::atomic<u32>                                       m_depthPubs{0};     /* depth publishes/win.       */
    std::atomic<u32>                                       m_hudPubs{0};       /* hud publishes/win.         */
    u64                                                    m_lastRatesUs{0};   /* ~1Hz rates publish gate.   */
    u64                                                    m_lastSegIters{0};  /* prev seg iter count.       */
    u64                                                    m_lastDepthIters{0};/* prev depth iter count.     */
    int                                                    m_a2ImgW = static_cast<int>(kA2ImgW); /* A2 publish width;  debug env FMU_A2_IMG_W. */
    int                                                    m_a2ImgH = static_cast<int>(kA2ImgH); /* A2 publish height; debug env FMU_A2_IMG_H. */

    std::atomic<FlightState>  m_flightState{FlightState::STANDBY};
    std::atomic<bool>         m_missionActive{false};
    std::atomic<bool>         m_planning{false};
    std::future<void>         m_planFuture;
    /* Airborne command-storm test (--scenario-cross-flood): a canned cross flight, then a
       100-action flood injected from a producer-role async ~5s after reaching FLIGHT. */
    bool                      m_floodArmed{false};
    bool                      m_floodFired{false};
    u64                       m_floodAtUs{0};
    std::future<void>         m_floodFuture;
    /* Test-only battery fault injection (--scenario-battery-rth / -landnow): ~15s into FLIGHT,
       force a discrete reading (18% -> RTH, 8% -> land-in-place) to exercise the failsafe laws
       deterministically, far from home. m_batteryForce: -2 = inactive, else the forced %. */
    std::atomic<i32>          m_batteryForce{-2};
    bool                      m_batForceArmed{false};
    bool                      m_batForceFired{false};
    i32                       m_batForceValue{0};
    u64                       m_batForceAtUs{0};
    /* Test-only interrupt-safety injection (spec 1, --scenario-boundary / -storm / -approach-impact):
       a synthetic close-obstacle burst to trip the boundary, and a forced motion-gate fail. */
    bool                      m_obstacleArmed{false};
    bool                      m_obstacleFired{false};
    u64                       m_obstacleUntilUs{0};
    bool                      m_forceApproachImpact{false};
    u64                       m_lastPlanUs{0};
    u64                       m_missionStartUs{0};
    std::atomic<u64>          m_frameCount{0};

    /* GO world-ENU target + speed (control thread only). Cross-track guidance:
       dir/total frozen at activation define the start->target line; controlLoop
       decays speed along it and pulls back perpendicular drift, without ever
       rotating the commanded forward direction. */
    f32 m_targetN{0.0f}, m_targetE{0.0f}, m_targetD{0.0f}, m_activeSpeed{0.3f};
    f32 m_rotateRemainingRad{0.0f};  /* ROTATE: rotation still owed in the commanded dir (rad). */
    f32 m_rotatePrevYaw{0.0f};       /* ROTATE: yaw last tick, to integrate progress.          */
    f32 m_rotateDir{1.0f};           /* ROTATE: +1 = ccw, -1 = cw (ENU CCW+).                  */
    f32 m_goStartN{0.0f}, m_goStartE{0.0f}, m_goStartD{0.0f};
    f32 m_goDirN{0.0f}, m_goDirE{0.0f}, m_goDirD{0.0f}, m_goTotalDist{0.0f};

    /* APPROACH coast state (control thread only): last known good aim direction + its
       timestamp, so one briefly-lost detection doesn't immediately FAIL the task
       (spec 2026-08-05-visual-servoing-approach-design.md §6). Reset at activation. */
    Vec3 m_approachLastAimFlu{0.0f, 0.0f, 0.0f};
    u64  m_approachLastAimUs{0};
    u64  m_approachActivateUs{0};
    bool m_approachHaveLastAim{false};
    f32  m_approachRangeHist[kApproachRangeMedianWindow]{};
    u32  m_approachRangeCount{0};
    f32  m_approachLastRange{0.0f};
    Vec3 m_approachStartPos{0.0f, 0.0f, 0.0f};   /* drone pose when the travel budget was latched */
    f32  m_approachTravelBudget{0.0f};           /* range-standoff at latch; dead-reckon stop point */
    bool m_approachBudgetLatched{false};
    i32  m_approachTrackId{-1};   /* VLM-chosen stable id being approached, -1 = label mode. */

    /* FOLLOW state (control thread only). Resolved once at activation: label + the bbox center
       (px) that seeds nearest-centroid tracking. Reset at activation. */
    FixedStringType m_followLabel{"\0"};
    f32  m_followLastU{0.0f};
    f32  m_followLastV{0.0f};
    Vec3 m_followLastAimFlu{0.0f, 0.0f, 0.0f};
    u64  m_followLastAimUs{0};
    bool m_followHaveLast{false};
    i32  m_followTrackId{-1};                             /* VLM-chosen stable id being followed. */
    f32  m_followLastErrX{0.0f};                          /* last accepted horizontal error (box-jump reject). */
    bool m_followHaveErr{false};                          /* seeded after the first accepted follow tick.       */
    std::shared_ptr<TrackedSnapshot> m_lastPromptTracked; /* frame the last VLM prompt was built from. */
    std::shared_ptr<TrackedSnapshot> m_lastNonEmptyTracked; /* last prompt frame that actually HAD a detection.*/
    std::atomic<u64>  m_lastNonEmptyUs{0};
    std::atomic<bool> m_everSawDetection{false};

    /* ORBIT state (control thread only). At the start we median a few depth reads into one fixed car
       position (the circle center); after that the circle is flown from ODOMETRY around that fixed
       point, so the path carries no depth jitter and cannot wobble. The camera turns separately to
       keep the real car in view. Reset at activation. */
    Vec3 m_orbitCenterEnu{0.0f, 0.0f, 0.0f};  /* locked car position, world ENU (the circle center).   */
    f32  m_orbitRadius{0.0f};                 /* circle radius = distance to the car when locked (m).   */
    f32  m_orbitSpeed{0.0f};                  /* tangential speed around the circle, m/s.               */
    f32  m_orbitDir{1.0f};                    /* +1 = ccw, -1 = cw. SITL-verify sign.                   */
    f32  m_orbitTargetRad{0.0f};              /* total angle to sweep around the car, rad.              */
    f32  m_orbitSweptRad{0.0f};               /* angle swept so far (from odometry), rad.               */
    Vec3 m_orbitPrevPos{0.0f, 0.0f, 0.0f};    /* drone position last tick, for swept-angle accounting.  */
    f32  m_orbitPrevYaw{0.0f};                /* drone yaw last tick, for visual-servo swept-angle.     */
    f32  m_orbitAltEnu{0.0f};                 /* altitude to hold during the orbit (Up+).               */
    bool m_orbitLatched{false};               /* false until the center is fixed from the median range. */
    f32  m_orbitRangeHist[kApproachRangeMedianWindow]{};  /* startup range samples, to median.          */
    u32  m_orbitRangeCount{0};
    u64  m_orbitStartUs{0};                   /* activation time, for the acquire timeout.              */
    u64  m_orbitLastSeenUs{0};                /* last tick the target was in view.                      */

    /* SEARCH state (control thread only): a leg/scan sub-FSM at fixed altitude. Legs are straight
       crossings of a circle about the start pose; a 360 look-around runs at each far edge, then the
       heading turns ~150 deg so the next crossing fans 30 deg around. Reset at activation. */
    Vec3 m_searchStartPos{0.0f, 0.0f, 0.0f};  /* pose at the start of the current phase (lane/cross).*/
    f32  m_searchAltEnu{0.0f};                /* altitude to hold (Up+).                           */
    f32  m_searchLaneHeadingRad{0.0f};        /* current lane heading, ENU yaw; flips 180 per lane. */
    f32  m_searchCrossHeadingRad{0.0f};       /* fixed sideways march heading between lanes.        */
    f32  m_searchDir{1.0f};                   /* +1 / -1: which side the lanes march. VLM-set.      */
    u64  m_searchStartUs{0};                  /* activation time, for the overall timeout.         */
    u64  m_searchLegStartUs{0};               /* current phase start, for the per-phase timeout.   */
    u64  m_searchTimeoutUs{0};                /* overall timeout from the command.                 */
    u32  m_searchLegCount{0};                 /* lanes flown so far.                               */
    u32  m_searchMaxLegs{0};                  /* lane cap so the pattern terminates.               */
    bool m_searchCrossing{false};             /* true = flying the sideways step between two lanes. */
    Vec3 m_searchOriginPos{0.0f, 0.0f, 0.0f}; /* true SEARCH-activation pose; unlike m_searchStartPos
                                                  this is never overwritten by a lane transition, so
                                                  it survives to the return-to-start leg on exhaustion.*/
    bool m_searchReturning{false};            /* true = SEARCH failed, flying back to m_searchOriginPos
                                                  before completing (rather than stranding the drone
                                                  wherever the last lane happened to end).            */
    /* advance-and-scan sub-FSM (replaces the lawnmower): 360 checkpoint scan, then step forward. */
    bool m_searchScanning{false};             /* true = doing the 360 checkpoint scan, false = advancing.*/
    f32  m_searchScanRemainingRad{0.0f};      /* angle left in the current 360 scan.                    */
    f32  m_searchScanPrevYaw{0.0f};           /* prev yaw, to accumulate scan progress.                 */
    f32  m_searchTotalDistM{0.0f};            /* total forward distance advanced, vs m_searchMaxDistM.  */
    f32  m_searchStepM{4.0f};                 /* distance between checkpoints.                          */
    f32  m_searchMaxDistM{16.0f};             /* give up after this much forward reach.                 */
    bool        mb_observability{false}; /* A2 dashboard off unless FMU_OBSERVABILITY set; gates all
                                          image/HUD/VLM-log work so a plain run keeps every core. */
    DroneConfig m_cfg;                 /* runtime tunables; every field defaults to the compiled
                                          constexpr, so a no-profile run is byte-identical to before.
                                          Loaded once from DRONE_CONFIG in the ctor (ROADMAP 9.14). */
    bool        mb_cfgActive{false};   /* true only when a DRONE_CONFIG profile was loaded; gates the
                                          SEARCH preset overlay so SITL keeps exact preset behavior.  */
    SearchSizeParams m_searchParams{kSearchSizePresets[kSearchDefaultSizeIdx]};  /* resolved once at
                                                  activation from CmdSearch::size; every leg/timeout
                                                  calc below reads this, never the raw preset table,
                                                  so a size choice stays consistent for one SEARCH. */

    /* Canned no-YOLO detection rig (block 5.1 verification, spec §7): when enabled,
       controlLoop synthesizes a PerceptionSnapshot for a point fixed relative to the
       drone's pose at APPROACH activation (see activateTask), instead of reading the
       real vision engines. */
    bool m_useCannedApproachRig{false};
    u64  m_cannedApproachActivateUs{0};
    Vec3 m_cannedApproachTargetEnu{0.0f, 0.0f, 0.0f};
    char m_cannedApproachLabel[32]{"canned_target"};   /* synthetic-det label for the rig; APPROACH sets it to the VLM target when bbox-anchored. */
    bool m_approachBboxRig{false};                      /* this APPROACH is driven by a frozen VLM-bbox anchor (rig on, no YOLO). Reset each activation. */
};
