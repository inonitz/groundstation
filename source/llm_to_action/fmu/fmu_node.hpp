#pragma once
#include <atomic>
#include <chrono>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>
#include <memory>
#include <future>
#include <cstdlib>
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

#include "gstreamer_udp_cam_rx/rx_node_base.hpp"  /* UDPCamMsgType, khUDPCamMsgType, camera topic */
#include "fmu_node_base.hpp"
#include "llm_base.hpp"
#include "llamaclient.hpp"
#include "plan_parse.hpp"
#include "generic_backend/active_backend.hpp"  /* ActiveBackend (FMU_BACKEND select) + BackendStatus/IOState/Odometry/Vec3 */
#include "perception_runtime.hpp"  /* PerceptionRuntime + global TargetDetection/PerceptionSnapshot (vision lib) */
#include "perception/detection_query.hpp"  /* detectionByLabel, CameraIntrinsics, TargetRelative */
#include <std_msgs/msg/bool.hpp>
#include "keyboard/keyboard_node_base.hpp"  /* kOutKeyboardRawTopic, KeyboardRawInputType (Int32MultiArray) */
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
    APPROACH = 9,
    MAX_ID   = 10
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

/* Command definition only (ROADMAP 3.6 / spec 2026-08-05-visual-servoing-approach-design.md §4c).
   No control-law branch yet -- that is block 5.1 (detectionByLabel + the yaw-center/range-decel
   servo). Until then this auto-completes via activateTask's default case, same as ORBIT/SEARCH. */
struct CmdApproach {
    FixedStringType target{"\0"};
    f32             speed{0.0f};
};

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
    GenericCommand(CmdApproach const& cmd) : m_rawBytes{__scast(u8, CommandID::APPROACH), {0}, {0}} {
        memcpy(&m_rawBytes.m_cmdBytes, &cmd, sizeof(CmdApproach));
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

/* TargetDetection / PerceptionSnapshot now come from the vision lib (global
   namespace, vision/perception_types.hpp via perception_runtime.hpp) --
   telemetry stays the only stub left here. */
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

        m_cbGroup = this->create_callback_group(rclcpp::CallbackGroupType::Reentrant);
        subOpts.callback_group = m_cbGroup;

        m_taskQueue = std::make_unique<spsc_queue<ActiveTask>>(3 * kControlLoopRateHz);

        m_subImg = this->create_subscription<UDPCamMsgType>(
            kOutUDPCameraRawFrameTopic, 10,
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

        /* All platform wire I/O lives in the backend. make_active_backend hides
           the per-backend ctor asymmetry (PX4 needs this Node + callback group;
           Tello, being ROS-free, ignores them) behind one uniform call, so the
           FMU stays non-templated and no ROS leaks into a ROS-free backend. */
        m_backend = make_active_backend(this, m_cbGroup);
        m_backend->start();

        /* Two-rate perception (ARCH sec 9): PerceptionRuntime owns its own seg/depth
           threads and publishes an atomic PerceptionSnapshot; buildDynamicPrompt()
           reads it. Thread counts are capped (fmu_node_base.hpp) so ORT cannot starve
           this control loop. */
        m_perception = std::make_unique<PerceptionRuntime>(
            kVisionSegModelPath, kVisionDepthModelPath,
            kVisionSegThreads, kVisionDepthThreads,
            kVisionSegLoopMs, kVisionDepthLoopMs,
            [this]() { return std::atomic_load(&m_currImg); });
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

        /* max_tokens caps generation. A plan is ~200 tokens; the old 32768 (65536/2)
           let a no-EOS runaway ramble for minutes and wedge the planner. 512 bounds
           it to ~4s. temp 0.2 matches the server and reduces degenerate loops. */
        m_vlmClient.create(kSystemPrompt, 0.2f, 512);
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

    /* Bootstrap: arm the mission. Phase 1 may inject a canned plan instead of VLM. */
    void start(std::string_view objective, bool useCannedPlan = false, bool useCrossPlan = false,
               bool useSpeedPlan = false, bool useApproachPlan = false, bool useApproachRealPlan = false,
               bool useRotatePlan = false, bool useLandFlarePlan = false,
               bool useTerrainLandPlan = false, bool useFloodPlan = false,
               bool useCrossFloodPlan = false, bool useBatteryRthPlan = false,
               bool useBatteryLandNowPlan = false, bool usePatrolPlan = false) {
        m_chat.m_initialCommand = objective;
        m_missionStartUs = nowUs();
        /* Only VLM-driven runs wake the planner; canned runs pre-fill the queue and
           must NOT poll a (possibly absent) VLM server after they drain. */
        bool cannedRun = useCannedPlan || useCrossPlan || useSpeedPlan || useApproachPlan || useApproachRealPlan || useRotatePlan || useLandFlarePlan || useTerrainLandPlan || useFloodPlan || useCrossFloodPlan || useBatteryRthPlan || useBatteryLandNowPlan || usePatrolPlan;
        m_missionActive.store(!cannedRun, std::memory_order_release);
        if (useCrossPlan) {
            injectCannedCrossPlan();
        } else if (useSpeedPlan) {
            injectCannedSpeedPlan();
        } else if (useApproachRealPlan) {
            injectCannedApproachRealPlan();
        } else if (useApproachPlan) {
            injectCannedApproachPlan();
        } else if (useRotatePlan) {
            injectCannedRotatePlan();
        } else if (useLandFlarePlan) {
            injectCannedLandFlarePlan();
        } else if (useTerrainLandPlan) {
            injectCannedTerrainLandPlan();
        } else if (useFloodPlan) {
            injectCannedFloodPlan();
        } else if (useCrossFloodPlan) {
            injectCannedCrossFloodPlan();
        } else if (useBatteryRthPlan) {
            injectCannedBatteryRthPlan();
        } else if (useBatteryLandNowPlan) {
            injectCannedBatteryLandNowPlan();
        } else if (usePatrolPlan) {
            injectCannedPatrolPlan();
        } else if (useCannedPlan) {
            injectCannedPlan();
        }
        RCLCPP_INFO(this->get_logger(),
            "[FMU_NODE_DEBUG] Mission started (canned=%d cross=%d speed=%d approach=%d approach_real=%d rotate=%d land_flare=%d terrain_land=%d). queued~=%zu. objective: %.*s",
            __scast(int, useCannedPlan), __scast(int, useCrossPlan), __scast(int, useSpeedPlan),
            __scast(int, useApproachPlan), __scast(int, useApproachRealPlan),
            __scast(int, useRotatePlan), __scast(int, useLandFlarePlan), __scast(int, useTerrainLandPlan),
            m_taskQueue->size_approx(), __scast(int, objective.size()), objective.data()
        );
        return;
    }

private:
    template <typename T>
    using spsc_queue = moodycamel::ReaderWriterQueue<T, sizeof(T)>;

    /* ---- Subscriptions --------------------------------------------------- */
    void imgCallback(khUDPCamMsgType msg) {
        std::atomic_store(&m_currImg, msg);
        u64 c = m_frameCount.fetch_add(1, kMemOrderRelax) + 1;
        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 2000,
            "[FMU_NODE_DEBUG] camera frame rx: %ux%u encoding=%s count=%lu",
            msg->width, msg->height, msg->encoding.c_str(), (unsigned long)c);
    }

    /* ---- APPROACH helpers ------------------------------------------------- */
    /* Perpendicular component of measVel relative to forwardUnit (assumed unit length);
       damps the pursuit-arc residual left after switching to a measured bearing (spec §9 R1). */
    static Vec3 lateralComponent(Vec3 measVel, Vec3 forwardUnit) {
        f32 along = measVel.x * forwardUnit.x + measVel.y * forwardUnit.y + measVel.z * forwardUnit.z;
        return { measVel.x - along * forwardUnit.x,
                 measVel.y - along * forwardUnit.y,
                 measVel.z - along * forwardUnit.z };
    }

    /* Projects m_cannedApproachTargetEnu (fixed at APPROACH activation, see activateTask)
       through the drone's live pose into a synthetic PerceptionSnapshot and publishes it via
       PerceptionRuntime::injectSynthetic. Forward-projection inverse of detectionByLabel's
       back-projection: world point -> body-FLU vector -> pixel. Not visible (behind the
       camera or outside the frame) -> publish a valid-but-empty snapshot, exactly what a
       real camera reports when nothing matches. */
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
        std::snprintf(synth.dets[0].label, sizeof(FixedStringType), "%s", kCannedApproachTargetLabel);
        synth.dets[0].bbox_xmin = static_cast<i32>(u - 20.0f);   /* synthetic 40x40px bbox.   */
        synth.dets[0].bbox_ymin = static_cast<i32>(v - 20.0f);
        synth.dets[0].bbox_xmax = static_cast<i32>(u + 20.0f);
        synth.dets[0].bbox_ymax = static_cast<i32>(v + 20.0f);
        synth.dets[0].confidence = 1.0f;
        synth.dets[0].median_depth_cm =
            std::sqrt(relFlu.x * relFlu.x + relFlu.y * relFlu.y + relFlu.z * relFlu.z) * 100.0f;
        m_perception->injectSynthetic(synth);
    }

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
        TargetRelative tr;
        std::shared_ptr<PerceptionSnapshot> snap;
        Vec3        velEnu, aimFlu, fwdDir, lat;
        f32         speedCeil, spF, yawRate, vUp, magV, appTrav, appRem;
        u64         tnow;

        od = m_backend->odometry();
        {
            i32 bf = m_batteryForce.load(kMemOrderRelax);   /* test-only fault injection; -2 = off */
            m_telemetry.battery_pct = (bf >= -1) ? bf : m_backend->battery_pct();
        }
        n  = od.pos.x;
        e  = od.pos.y;
        d  = od.pos.z;
        st = m_flightState.load(kMemOrderRelax);

        /* Battery failsafe = ultimate safety net: pre-empts the plan AND the pilot. */
        if (batteryFailsafeTick()) return;

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

        /* Airborne command-storm (spec-3): once we've been in FLIGHT ~5s, inject the flood
           from a producer-role async (mirrors the VLM's std::async path) so the SPSC contract
           holds -- the control thread only LAUNCHES it here, it never enqueues. */
        if (m_floodArmed && !m_floodFired && st == FlightState::FLIGHT) {
            if (m_floodAtUs == 0)             m_floodAtUs = nowUs() + 5ULL * 1000000ULL;
            else if (nowUs() >= m_floodAtUs) {
                m_floodFired  = true;
                m_floodFuture = std::async(std::launch::async, [this]() { injectCannedFloodPlan(); });
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
            m_backend->set_velocity(Vec3{0.0f, 0.0f, kTakeoffClimbVelEnu}, 0.0f);  /* stream the climb (Up+) */
            if (m_backend->state() == IOState::FAULT) {
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] TAKEOFF faulted (backend IOState=FAULT). Aborting task.");
                m_flightState.store(FlightState::STANDBY, kMemOrderRelax);
                completeCurrent("takeoff_faulted");
                return;
            }
            if (d >= kTakeoffTargetAltEnu) {
                RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] TAKEOFF->FLIGHT altENU=%.2f", d);
                m_flightState.store(FlightState::FLIGHT, kMemOrderRelax);
                completeCurrent("takeoff_ok");
            }
            return;
        }

        if (st == FlightState::LANDING) {
            /* slow-descent from full-speed to slow-touchdown as altitude nears the ground */
            f32 vLand = kLandDescendVelEnu;
            if (d < kFlareStartAltEnu) {
                f32 t = (d - kGroundContactEnu) / (kFlareStartAltEnu - kGroundContactEnu);
                if (t < 0.0f) t = 0.0f; else if (t > 1.0f) t = 1.0f;  /* 1 at flare start, 0 at contact */
                vLand = kFlareTouchdownVelEnu + t * (kLandDescendVelEnu - kFlareTouchdownVelEnu);
            }
            /* stream vLand so the flare taper is verifiable from the log (spec-4 Part B). */
            RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                "[FMU_NODE_DIAGNOSTICS] LAND altENU=%.2f vLand=%.3f", d, vLand);
            m_backend->set_velocity(Vec3{0.0f, 0.0f, vLand}, 0.0f);  /* stream the (flared) descent (Down) */
            if (d <= kGroundContactEnu) {
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

                    sp = kGoApproachGainHz * remain;
                    if (sp > m_activeSpeed) sp = m_activeSpeed;

                    vN = m_goDirN * sp - kGoCrossTrackGainHz * crN;
                    vE = m_goDirE * sp - kGoCrossTrackGainHz * crE;
                    vD = m_goDirD * sp - kGoCrossTrackGainHz * crD;
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
                    f32 yawRate = m_rotateDir * kRotateYawGainHz * m_rotateRemainingRad;
                    if (yawRate >  kRotateMaxYawRate) yawRate =  kRotateMaxYawRate;
                    else if (yawRate < -kRotateMaxYawRate) yawRate = -kRotateMaxYawRate;
                    m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, yawRate);
                    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                        "[FMU_NODE_DIAGNOSTICS] ROTATE remainRad=%.3f cmdYawrate=%.3f measYaw=%.2f measYawrate=%.2f",
                        m_rotateRemainingRad, yawRate, od.yaw, od.yawrate);
                }
            } else if (id == CommandID::APPROACH) {
                if (m_useCannedApproachRig) updateCannedApproachRig(od);

                appr = m_currTask.m_cmd.m_extractCmd.m_approach;
                tnow = nowUs();
                snap = m_perception->snapshot();
                tr   = (snap) ? detectionByLabel(*snap, appr.target, kApproachCamera, tnow)
                              : TargetRelative{};
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
                        appRem  = kApproachStandoffM;   /* until latched, treat the stop point as far */
                        if (m_approachBudgetLatched) {
                            dx      = od.pos.x - m_approachStartPos.x;
                            dy      = od.pos.y - m_approachStartPos.y;
                            dz      = od.pos.z - m_approachStartPos.z;
                            appTrav = std::sqrt(dx * dx + dy * dy + dz * dz);
                            appRem  = m_approachTravelBudget - appTrav;
                        }
                        if (m_approachBudgetLatched && appRem <= 0.0f) {
                            /* Reached the dead-reckoned stop point with the target briefly lost.
                               Odometry says we are there, so stop -- don't wait for a re-lock. */
                            m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                            RCLCPP_INFO(this->get_logger(),
                                "[FMU_NODE_DEBUG] APPROACH reached target=%s traveled=%.2f/%.2f (lost at stop)",
                                appr.target, appTrav, m_approachTravelBudget);
                            completeCurrent("approach_ok");
                        } else if (appRem <= kApproachCoastHoldMarginM) {
                            /* Lost the target while already near the stop point: HOLD, do not coast
                               forward -- coasting blind into a close target is how it hits it. */
                            m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                            RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                                "[FMU_NODE_DIAGNOSTICS] APPROACH hold near stop point target=%s (lost, rem~%.2f).",
                                appr.target, appRem);
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
                        m_approachTravelBudget  = m_approachLastRange - kApproachStandoffM;
                        if (m_approachTravelBudget < 0.0f) m_approachTravelBudget = 0.0f;
                        m_approachBudgetLatched = true;
                        RCLCPP_INFO(this->get_logger(),
                            "[FMU_NODE_DEBUG] APPROACH range locked R0=%.2f travelBudget=%.2f",
                            m_approachLastRange, m_approachTravelBudget);
                    }
                    appTrav = 0.0f;
                    appRem  = kApproachStandoffM;   /* until latched, treat the stop point as far */
                    if (m_approachBudgetLatched) {
                        dx      = od.pos.x - m_approachStartPos.x;
                        dy      = od.pos.y - m_approachStartPos.y;
                        dz      = od.pos.z - m_approachStartPos.z;
                        appTrav = std::sqrt(dx * dx + dy * dy + dz * dz);
                        appRem  = m_approachTravelBudget - appTrav;
                    }

                    if ((m_approachBudgetLatched && appRem <= 0.0f) ||
                        (m_approachLastRange > 0.0f && m_approachLastRange < kApproachStandoffM)) {
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                        RCLCPP_INFO(this->get_logger(),
                            "[FMU_NODE_DEBUG] APPROACH reached target=%s traveled=%.2f/%.2f range=%.2f",
                            appr.target, appTrav, m_approachTravelBudget, m_approachLastRange);
                        completeCurrent("approach_ok");
                    } else {
                        speedCeil = (appr.speed > 0.0f ? appr.speed : kApproachSpeedDefault) / 100.0f;
                        /* Brake on remaining dead-reckoned travel once latched; before the latch,
                           creep slowly forward while collecting range samples for R0. */
                        spF       = m_approachBudgetLatched
                                        ? kApproachFwdGainHz * appRem
                                        : kApproachCoastSpeedMps;
                        if (spF < 0.0f) spF = 0.0f;
                        if (spF > speedCeil) spF = speedCeil;
                        yawRate = -kApproachYawGain * tr.errX;
                        vUp     = -kApproachVertGain * tr.errY;
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
                            "[FMU_NODE_DIAGNOSTICS] APPROACH target=%s range=%.2f errX=%.2f errY=%.2f "
                            "cmdVelENU=(%.2f,%.2f,%.2f) yawRate=%.2f",
                            appr.target, tr.range, tr.errX, tr.errY,
                            velEnu.x, velEnu.y, velEnu.z, yawRate);
                    }
                }
            } else {
                RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] task id=%d not movement -> auto-complete.",
                    __scast(int, id));
                completeCurrent("noop_ok");
            }
            return;
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
        khUDPCamMsgType img;
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

    /* ---- Battery failsafe + manual override ------------------------------ */
    /* Returns true if the failsafe pre-empted this tick. battery_pct < 0
       (kBatteryReadingUnknown) means no trustworthy reading -> skip; a real 0 is
       empty and triggers. Latches so a wobbling reading can't oscillate the state. */
    bool batteryFailsafeTick() {
        i32 pct = m_telemetry.battery_pct;
        if (pct < 0)          return false;   /* UNKNOWN sentinel: never a false alarm. */
        if (mb_batteryReturn || mb_batteryLand) return false;   /* EITHER failsafe latched -> committed to a landing; don't re-evaluate (land-in-place must not then escalate to RTH). */

        if (pct <= kBatteryLandPct && !mb_batteryLand) {      /* critical -> land where we are. */
            mb_batteryLand = true;
            m_hasActive    = false;
            { ActiveTask stale; while (m_taskQueue->try_dequeue(stale)) { } }  /* drop the rest of the plan (consumer side); leftover actions must not run after we land. */
            m_flightState.store(FlightState::LANDING, kMemOrderRelax);
            m_missionActive.store(false, std::memory_order_release);
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] FAILSAFE battery %d%% -> LAND in place.", pct);
            return true;
        }
        if (pct <= kBatteryReturnPct && !mb_batteryReturn) {  /* low -> return to origin, then land. */
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

    /* Raw keylog [keycode, action]. While override is engaged, movement keys map to
       a constant body-FLU velocity (converted to ENU in controlLoop). WASD=plane,
       arrows=alt/yaw, Space=hover. Ignored when not overridden. */
    void keyCallback(const KeyboardRawInputType::SharedPtr msg) {
        if (msg->data.size() < 2 || !m_manualOverride.load(kMemOrderRelax)) return;

        constexpr f32 kV   = kManualTeleopVelCmS / 100.0f;   /* m/s per axis. */
        constexpr f32 kYaw = 0.6f;                           /* rad/s; TUNE in sim+real. */
        int  key  = msg->data[0];
        bool down = (msg->data[1] == __scast(int, KeyAction::PRESSED));
        bool up   = (msg->data[1] == __scast(int, KeyAction::RELEASED));
        if (!down && !up) return;                            /* ignore auto-repeat, etc. */
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

    void activateTask(ActiveTask const& task) {
        Odometry      od;
        Vec3          relFlu, relEnu;
        CmdGo         g;
        CmdRotate     r;
        CommandID     id;
        BackendStatus s;

        m_currTask = task;
        m_currTask.m_state = TaskState::RUNNING;
        m_hasActive = true;
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
            m_activeSpeed = (g.speed > 0.0f ? g.speed : kDefaultGoSpeedCmS) / 100.0f;
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
            m_approachActivateUs       = nowUs();
            m_approachRangeCount       = 0;
            m_approachBudgetLatched    = false;
            m_approachTravelBudget     = 0.0f;
            m_cannedApproachActivateUs = nowUs();
            od     = m_backend->odometry();
            relFlu = { kCannedApproachTargetFwdM, 0.0f, kCannedApproachTargetUpM };
            relEnu = flu_to_enu(relFlu, od.yaw);
            m_cannedApproachTargetEnu = { od.pos.x + relEnu.x, od.pos.y + relEnu.y, od.pos.z + relEnu.z };
            RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] APPROACH activated target=%s.",
                m_currTask.m_cmd.m_extractCmd.m_approach.target);
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
        m_hasActive = false;
        m_settleTicksRemaining = kGoSettleTicks;
        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
        RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] task complete status=%s total=%zu",
            status, m_chat.m_completedTasks.size());
    }

    /* ---- VLM plumbing (invoked by the Phase-2 event-driven wake, not a poll) ---- */
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
        std::shared_ptr<PerceptionSnapshot> snap = m_perception->snapshot();
        if (snap && snap->valid && snap->count > 0) {
            for (u32 t = 0; t < snap->count; ++t) {
                const TargetDetection& det = snap->dets[t];
                snprintf(buf, sizeof(buf),
                    "{\"label\":\"%s\", \"bbox\":[%d,%d,%d,%d], \"confidence\":%.2f, \"median_depth_cm\":%.1f}\n",
                    det.label, det.bbox_xmin, det.bbox_ymin, det.bbox_xmax, det.bbox_ymax,
                    det.confidence, det.median_depth_cm);
                prompt += buf;
            }
        } else {
            prompt += "(no detections)\n";
        }
        prompt += "\n";

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
        if (img) {                               /* text-only plan when no camera frame yet. */
            frame = cv_bridge::toCvShare(img, "bgr8")->image;
            if (!frame.empty()) {
                cv::resize(frame, resized, cv::Size{640, 640}, 0, 0, cv::INTER_LINEAR);
                cv::imencode(".jpg", resized, buffer, params);
                b64 = base64_encode(buffer.data(), buffer.size());
            }
        }

        dyn = buildDynamicPrompt();
        RCLCPP_INFO(this->get_logger(),
            "[FMU_NODE_DEBUG] VLM request: image=%s b64Bytes=%zu promptChars=%zu",
            (img && !b64.empty()) ? "yes" : "no", b64.size(), dyn.size());
        fut = m_vlmClient.send(dyn, userQuery, b64);
        if (!fut.has_value()) {
            RCLCPP_WARN(this->get_logger(),
                "[FMU_NODE_DEBUG] VLM submit returned nullopt (HTTP client not ready).");
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
            }
        }
        out = content;
    }

    void translateToBaseCommands(std::string_view flightPlan) {
        nlohmann::json plan;
        std::string    action, thought, arr;
        GenericCommand cmd;
        ActiveTask     task;
        CmdGo          go;
        CmdApproach    approach;
        CmdRotate      rot;

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
            } else if (action == "rotate") {
                rot = CmdRotate{};
                rot.angle_deg = item.value("angle_deg", 0);
                rot.cw_or_ccw = (item.value("direction", std::string("cw")) == "cw");
                cmd = GenericCommand(rot);
            } else if (action == "approach") {
                approach = CmdApproach{};
                strncpy(approach.target, item.value("target_object", "").c_str(),
                    sizeof(approach.target) - 1);
                approach.speed = item.value("speed", 0.0f);
                cmd = GenericCommand(approach);
                /* Queueable now (3.6); no control-law branch yet -- auto-completes like
                   ORBIT/SEARCH until block 5.1 lands the real servo. */
            } else {
                continue; /* Phase 1: takeoff/land/stop/go/rotate/approach executed. */
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

    /* Canned plan is the SAME JSON the VLM emits, routed through the real       */
    /* translate path — no inverse function needed.                             */
    /* Backpressure stress (1.4): enqueue far more actions than the queue cap in ONE
       plan -- the worst-case oversized-plan storm (a verbose/hallucinating VLM). Expect
       qsize to cap at the queue size and exactly (N - cap) BACKPRESSURE drops. Uses
       'stop' (hover) actions: the test is about the queue, not the flight. */
    void injectCannedFloodPlan() {
        constexpr u32 kFloodActions = 100;
        std::string plan = "[";
        for (u32 i = 0; i < kFloodActions; ++i) {
            if (i) plan += ",";
            plan += "{\"thought\":\"flood\",\"action\":\"stop\"}";
        }
        plan += "]";
        RCLCPP_WARN(this->get_logger(),
            "[FMU_NODE_DEBUG] FLOOD test: injecting %u actions vs queue cap %u.",
            kFloodActions, 3u * kControlLoopRateHz);
        translateToBaseCommands(plan);
    }

    void injectCannedPlan() {
        static const char* kCannedPlanJson = R"([
            {"thought":"canned takeoff",    "action":"takeoff"},
            {"thought":"canned go forward", "action":"go", "x":100, "y":0, "z":0, "speed":30},
            {"thought":"canned land",       "action":"land"}
        ])";
        translateToBaseCommands(kCannedPlanJson);
    }

    /* Canned ROTATE regression (spec-4 Part B): a <180 turn then a >=180 turn, opposite
       directions -- proves the accumulated-angle law sweeps the FULL commanded magnitude in
       the commanded direction (200 ccw does NOT collapse to a shortest-path 160 cw). Runs the
       SAME translate path the VLM uses. */
    void injectCannedRotatePlan() {
        static const char* kCannedRotatePlanJson = R"([
            {"thought":"canned takeoff",    "action":"takeoff"},
            {"thought":"canned rotate cw",  "action":"rotate", "direction":"cw",  "angle_deg":90},
            {"thought":"canned rotate ccw", "action":"rotate", "direction":"ccw", "angle_deg":200},
            {"thought":"canned land",       "action":"land"}
        ])";
        translateToBaseCommands(kCannedRotatePlanJson);
    }

    /* Canned LAND-flare regression (spec-4 Part B): climb to ~2m then land, so the LANDING
       branch runs its full flare taper -- vLand must ramp from kLandDescendVelEnu toward
       kFlareTouchdownVelEnu as altitude drops, not sit at a constant -0.5. */
    void injectCannedLandFlarePlan() {
        static const char* kCannedLandFlarePlanJson = R"([
            {"thought":"canned takeoff", "action":"takeoff"},
            {"thought":"canned land",    "action":"land"}
        ])";
        translateToBaseCommands(kCannedLandFlarePlanJson);
    }

    /* Canned terrain-land test: fly laterally over the real Rubicon TERRAIN world then land, so the
       takeoff-origin height differs from the ground height at the landing spot. Exposes that
       landing keys on od.pos.z (height above the EKF/takeoff origin), not above-ground-level --
       a flat world hides it because there origin height == ground height everywhere. */
    void injectCannedTerrainLandPlan() {
        static const char* kCannedTerrainLandPlanJson = R"([
            {"thought":"canned takeoff",        "action":"takeoff"},
            {"thought":"canned go forward 2m",  "action":"go", "x":200,  "y":0, "z":0, "speed":30},
            {"thought":"canned land",           "action":"land"}
        ])";
        translateToBaseCommands(kCannedTerrainLandPlanJson);
    }

    /* Canned, no-YOLO closed-loop APPROACH test (ROADMAP 5.1 verification, spec §7): enables
       the synthetic detection rig, then runs the SAME translate path the VLM uses. */
    void injectCannedApproachPlan() {
        static const char* kCannedApproachPlanJson = R"([
            {"thought":"canned takeoff",  "action":"takeoff"},
            {"thought":"canned approach", "action":"approach",
             "target_object":"canned_target", "speed":30},
            {"thought":"canned land",     "action":"land"}
        ])";
        m_useCannedApproachRig = true;
        translateToBaseCommands(kCannedApproachPlanJson);
    }

    /* Skips the VLM planner but NOT perception -- real PerceptionRuntime (real ONNX
       models) supplies the detection, same query path a VLM-driven run would use.
       Targets "car" (COCO label) since the SITL world has a Rubicon jeep at spawn. */
    void injectCannedApproachRealPlan() {
        static const char* kCannedApproachRealPlanJson = R"([
            {"thought":"canned takeoff",  "action":"takeoff"},
            {"thought":"canned approach", "action":"approach",
             "target_object":"car", "speed":30},
            {"thought":"canned land",     "action":"land"}
        ])";
        translateToBaseCommands(kCannedApproachRealPlanJson);
    }

    /* Body-frame (FLU) axis test: each of forward/left/back/right is flown OUT
       then immediately UNDONE, one axis at a time, before the next axis starts.
       Every "return" leg re-anchors from fresh od.yaw + od.pos at that leg's own
       activation (not an assumed prior target) -- isolates flu_to_ned correctness
       from GO controller error, and isolates each axis's error from the others
       since a bad return doesn't carry into the next axis's outbound leg. */
    void injectCannedCrossPlan() {
        static const char* kCannedCrossPlanJson = R"([
            {"thought":"canned takeoff",             "action":"takeoff"},
            {"thought":"canned go forward",          "action":"go", "x":100,  "y":0,    "z":0, "speed":30},
            {"thought":"canned return to start",     "action":"go", "x":-100, "y":0,    "z":0, "speed":30},
            {"thought":"canned go left",             "action":"go", "x":0,    "y":100,  "z":0, "speed":30},
            {"thought":"canned return to start",     "action":"go", "x":0,    "y":-100, "z":0, "speed":30},
            {"thought":"canned go back",             "action":"go", "x":-100, "y":0,    "z":0, "speed":30},
            {"thought":"canned return to start",     "action":"go", "x":100,  "y":0,    "z":0, "speed":30},
            {"thought":"canned go right",            "action":"go", "x":0,    "y":-100, "z":0, "speed":30},
            {"thought":"canned return to start",     "action":"go", "x":0,    "y":100,  "z":0, "speed":30},
            {"thought":"canned land",                "action":"land"}
        ])";
        translateToBaseCommands(kCannedCrossPlanJson);
    }

    /* Airborne backpressure test (spec-3, ROADMAP 1.4): fly the canned cross, then ~5s after
       reaching FLIGHT a 100-action flood is injected mid-air (see controlLoop). Proves an
       in-flight command storm is absorbed safely -- the queue stays bounded, excess is
       dropped, and the maneuver in progress is NOT hijacked (FIFO: the storm queues BEHIND
       the live plan, so the drone finishes its legs + lands before the no-op stops run). */
    void injectCannedCrossFloodPlan() {
        injectCannedCrossPlan();   /* takeoff + cross legs + land, enqueued at startup. */
        m_floodArmed = true;       /* controlLoop fires the flood once airborne. */
        RCLCPP_WARN(this->get_logger(),
            "[FMU_NODE_DEBUG] AIRBORNE FLOOD armed: flooding ~5s after reaching FLIGHT.");
    }

    /* Outbound excursion for the battery-behaviour tests: takeoff, fly ~8m straight out (so RTH
       has a real distance to cover and land-in-place is genuinely far from home), then land. */
    void injectCannedOutboundPlan() {
        static const char* kCannedOutboundPlanJson = R"([
            {"thought":"canned takeoff",    "action":"takeoff"},
            {"thought":"canned fly out 8m", "action":"go", "x":800, "y":0, "z":0, "speed":40},
            {"thought":"canned land",       "action":"land"}
        ])";
        translateToBaseCommands(kCannedOutboundPlanJson);
    }

    /* Battery RTH behaviour test (spec-3, ROADMAP 6.2): fly out, then force a drop to 18% far
       from home -> the <=20% law returns the drone to origin, where it lands and disarms. */
    void injectCannedBatteryRthPlan() {
        injectCannedOutboundPlan();
        m_batForceArmed = true; m_batForceValue = 18;
        RCLCPP_WARN(this->get_logger(),
            "[FMU_NODE_DEBUG] BATTERY-RTH armed: forcing 18%% ~15s after reaching FLIGHT.");
    }

    /* Battery land-in-place test (spec-3, ROADMAP 6.2): fly out, then force a sudden crash to
       8% far from home -> the <=10% law lands the drone WHERE IT IS (no return to origin). */
    void injectCannedBatteryLandNowPlan() {
        injectCannedOutboundPlan();
        m_batForceArmed = true; m_batForceValue = 8;
        RCLCPP_WARN(this->get_logger(),
            "[FMU_NODE_DEBUG] BATTERY-LANDNOW armed: forcing 8%% ~15s after reaching FLIGHT.");
    }

    /* Real-drain battery test (spec-3, ROADMAP 6.2): fly out ~6m then loop a 4m box (stays
       6-10m from origin, never sitting at home), while the PX4 pack drains for real. Whenever
       OUR <=20% failsafe fires -- a drain-dependent, "random" point along the patrol -- RTH
       brings it home. Many legs; the failsafe pre-empts and drains the rest. Run with PX4's own
       low-battery action DISABLED (COM_LOW_BAT_ACT=0) so it can't hijack the descent. */
    void injectCannedPatrolPlan() {
        std::string plan = "[";
        plan += R"({"thought":"canned takeoff","action":"takeoff"},)";
        plan += R"({"thought":"fly out 6m","action":"go","x":600,"y":0,"z":0,"speed":40},)";
        for (int i = 0; i < 5; ++i) {   /* 5 loops of a 4m box, keeps it ~6-10m out for ~200s */
            plan += R"({"thought":"patrol","action":"go","x":0,"y":400,"z":0,"speed":40},)";
            plan += R"({"thought":"patrol","action":"go","x":400,"y":0,"z":0,"speed":40},)";
            plan += R"({"thought":"patrol","action":"go","x":0,"y":-400,"z":0,"speed":40},)";
            plan += R"({"thought":"patrol","action":"go","x":-400,"y":0,"z":0,"speed":40},)";
        }
        plan += R"({"thought":"canned land","action":"land"}])";
        RCLCPP_INFO(this->get_logger(),
            "[FMU_NODE_DEBUG] PATROL plan: fly out + box loops; real battery drain drives the failsafe.");
        translateToBaseCommands(plan);
    }

    /* Low vs high commanded speed, forward+return, back to back. Same guidance
       law, same axis, only m_activeSpeed differs -- isolates whether curvature
       scales with commanded speed (actuator-lag/overshoot signature) or is
       roughly constant regardless (points elsewhere, e.g. the settle window). */
    void injectCannedSpeedPlan() {
        static const char* kCannedSpeedPlanJson = R"([
            {"thought":"canned takeoff",              "action":"takeoff"},
            {"thought":"canned go forward LOW speed",  "action":"go", "x":100,  "y":0, "z":0, "speed":15},
            {"thought":"canned return to start",       "action":"go", "x":-100, "y":0, "z":0, "speed":15},
            {"thought":"canned go forward HIGH speed", "action":"go", "x":100,  "y":0, "z":0, "speed":80},
            {"thought":"canned return to start",       "action":"go", "x":-100, "y":0, "z":0, "speed":80},
            {"thought":"canned land",                  "action":"land"}
        ])";
        translateToBaseCommands(kCannedSpeedPlanJson);
    }

private:
    rclcpp::CallbackGroup::SharedPtr                m_cbGroup;
    rclcpp::Subscription<UDPCamMsgType>::SharedPtr  m_subImg;
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr    m_subOverride;  /* operator override toggle. */
    rclcpp::Subscription<KeyboardRawInputType>::SharedPtr   m_subKey;       /* raw keylog for manual flight. */
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

    llamaClientConnection                           m_vlmClient;
    khUDPCamMsgType                                 m_currImg;
    HistoryBuffer                                   m_chat;
    VehicleTelemetry                                m_telemetry;
    std::unique_ptr<PerceptionRuntime>               m_perception;

    std::atomic<FlightState>  m_flightState{FlightState::STANDBY};
    std::atomic<bool>         m_missionActive{false};
    std::atomic<bool>         m_planning{false};
    std::future<void>         m_planFuture;
    /* Airborne command-storm test (--canned-cross-flood): a canned cross flight, then a
       100-action flood injected from a producer-role async ~5s after reaching FLIGHT. */
    bool                      m_floodArmed{false};
    bool                      m_floodFired{false};
    u64                       m_floodAtUs{0};
    std::future<void>         m_floodFuture;
    /* Test-only battery fault injection (--canned-battery-rth / -landnow): ~15s into FLIGHT,
       force a discrete reading (18% -> RTH, 8% -> land-in-place) to exercise the failsafe laws
       deterministically, far from home. m_batteryForce: -2 = inactive, else the forced %. */
    std::atomic<i32>          m_batteryForce{-2};
    bool                      m_batForceArmed{false};
    bool                      m_batForceFired{false};
    i32                       m_batForceValue{0};
    u64                       m_batForceAtUs{0};
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

    /* Canned no-YOLO detection rig (block 5.1 verification, spec §7): when enabled,
       controlLoop synthesizes a PerceptionSnapshot for a point fixed relative to the
       drone's pose at APPROACH activation (see activateTask), instead of reading the
       real vision engines. */
    bool m_useCannedApproachRig{false};
    u64  m_cannedApproachActivateUs{0};
    Vec3 m_cannedApproachTargetEnu{0.0f, 0.0f, 0.0f};
};
