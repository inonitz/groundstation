#pragma once
#include <atomic>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>
#include <memory>
#include <future>
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


/* Shared-scalar access order (matches the proven baseline). */
static constexpr std::memory_order rlx = std::memory_order_relaxed;

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
    APPROACH = 9,   /* parsed + queueable (3.6); servo control law is block 5.1, not yet built --
                       auto-completes via activateTask's default case, same as ORBIT/SEARCH today. */
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
               bool useSpeedPlan = false, bool useApproachPlan = false) {
        m_chat.m_initialCommand = objective;
        m_missionStartUs = nowUs();
        /* Only VLM-driven runs wake the planner; canned runs pre-fill the queue and
           must NOT poll a (possibly absent) VLM server after they drain. */
        bool cannedRun = useCannedPlan || useCrossPlan || useSpeedPlan || useApproachPlan;
        m_missionActive.store(!cannedRun, std::memory_order_release);
        if (useCrossPlan) {
            injectCannedCrossPlan();
        } else if (useSpeedPlan) {
            injectCannedSpeedPlan();
        } else if (useApproachPlan) {
            injectCannedApproachPlan();
        } else if (useCannedPlan) {
            injectCannedPlan();
        }
        RCLCPP_INFO(this->get_logger(),
            "[FMU_NODE_DEBUG] Mission started (canned=%d cross=%d speed=%d approach=%d). queued~=%zu. objective: %.*s",
            __scast(int, useCannedPlan), __scast(int, useCrossPlan), __scast(int, useSpeedPlan),
            __scast(int, useApproachPlan),
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
        u64 c = m_frameCount.fetch_add(1, rlx) + 1;
        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 2000,
            "[FMU_NODE_DEBUG] camera frame rx: %ux%u encoding=%s count=%lu",
            msg->width, msg->height, msg->encoding.c_str(), (unsigned long)c);
    }

    /* ---- 20Hz control + deterministic completion ------------------------- */
    /* Pure planner side: reads an Odometry snapshot + IOState, issues verbs.   */
    /* Frame is canonical ENU (East, North, Up+); backend converts NED at wire. */
    /* Perpendicular component of measVel relative to forwardUnit (assumed unit length).
       Subtracting a fraction of this from the commanded ENU velocity damps the pursuit-arc
       residual left after switching to a measured (not dead-reckoned) bearing (spec §9 R1). */
    static Vec3 lateralComponent(Vec3 measVel, Vec3 forwardUnit) {
        f32 along = measVel.x * forwardUnit.x + measVel.y * forwardUnit.y + measVel.z * forwardUnit.z;
        return { measVel.x - along * forwardUnit.x,
                 measVel.y - along * forwardUnit.y,
                 measVel.z - along * forwardUnit.z };
    }

    /* Projects kCannedApproachTargetEnu through the drone's live pose into a synthetic
       PerceptionSnapshot and publishes it via PerceptionRuntime::injectSynthetic. Forward-
       projection inverse of detectionByLabel's back-projection: world point -> body-FLU
       vector -> pixel. Not visible (behind the camera or outside the frame) -> publish a
       valid-but-empty snapshot, exactly what a real camera reports when nothing matches. */
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

        relEnu = { kCannedApproachTargetEnu.x - od.pos.x,
                   kCannedApproachTargetEnu.y - od.pos.y,
                   kCannedApproachTargetEnu.z - od.pos.z };
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
        f32         speedCeil, spF, yawRate, vUp, magV;
        u64         tnow;

        od = m_backend->odometry();
        n  = od.pos.x;
        e  = od.pos.y;
        d  = od.pos.z;
        st = m_flightState.load(rlx);

        /* HIGH-verbosity heartbeat (every 500ms) — one glance shows the whole rig. */
        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 500,
            "[FMU_NODE_DIAGNOSTICS] fs=%d io=%d posENU=(%.2f,%.2f,%.2f) measVelENU=(%.2f,%.2f,%.2f) yaw=%.2f yawrate=%.2f active=%d qsize=%zu",
            __scast(int, st), __scast(int, m_backend->state()),
            n, e, d, od.vel.x, od.vel.y, od.vel.z, od.yaw, od.yawrate,
            __scast(int, m_hasActive), m_taskQueue->size_approx());

        if (st == FlightState::TAKEOFF) {
            m_backend->set_velocity(Vec3{0.0f, 0.0f, kTakeoffClimbVelEnu}, 0.0f);  /* stream the climb (Up+) */
            if (m_backend->state() == IOState::FAULT) {
                RCLCPP_WARN(this->get_logger(),
                    "[FMU_NODE_DEBUG] TAKEOFF faulted (backend IOState=FAULT). Aborting task.");
                m_flightState.store(FlightState::STANDBY, rlx);
                completeCurrent("takeoff_faulted");
                return;
            }
            if (d >= kTakeoffTargetAltEnu) {
                RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] TAKEOFF->FLIGHT altENU=%.2f", d);
                m_flightState.store(FlightState::FLIGHT, rlx);
                completeCurrent("takeoff_ok");
            }
            return;
        }

        if (st == FlightState::LANDING) {
            m_backend->set_velocity(Vec3{0.0f, 0.0f, kLandDescendVelEnu}, 0.0f);  /* stream the descent (Down) */
            if (d <= kGroundContactEnu) {
                m_backend->force_disarm();
                RCLCPP_INFO(this->get_logger(), "[FMU_NODE_DEBUG] LANDING->STANDBY altENU=%.2f (force_disarm)", d);
                m_flightState.store(FlightState::STANDBY, rlx);
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
            } else if (id == CommandID::APPROACH) {
                if (m_useCannedApproachRig) updateCannedApproachRig(od);

                appr = m_currTask.m_cmd.m_extractCmd.m_approach;
                tnow = nowUs();
                snap = m_perception->snapshot();
                tr   = (snap) ? detectionByLabel(*snap, appr.target, kApproachCamera, tnow)
                              : TargetRelative{};

                if (!tr.found || tr.age_us > kApproachLostTimeoutUs) {
                    if (m_approachHaveLastAim &&
                        (tnow - m_approachLastAimUs) <= kApproachLostTimeoutUs) {
                        aimFlu = { m_approachLastAimFlu.x * kApproachCoastSpeedMps,
                                   m_approachLastAimFlu.y * kApproachCoastSpeedMps,
                                   m_approachLastAimFlu.z * kApproachCoastSpeedMps };
                        velEnu = flu_to_enu(aimFlu, od.yaw);
                        m_backend->set_velocity(velEnu, 0.0f);
                        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 250,
                            "[FMU_NODE_DIAGNOSTICS] APPROACH coasting target=%s (lost).", appr.target);
                    } else {
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                        RCLCPP_WARN(this->get_logger(),
                            "[FMU_NODE_DEBUG] APPROACH lost target=%s past coast window -> FAIL.",
                            appr.target);
                        completeCurrent("approach_lost_failed");
                    }
                } else {
                    m_approachLastAimFlu  = tr.dirFlu;
                    m_approachLastAimUs   = tnow;
                    m_approachHaveLastAim = true;

                    if (tr.range < kApproachStandoffM) {
                        m_backend->set_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
                        RCLCPP_INFO(this->get_logger(),
                            "[FMU_NODE_DEBUG] APPROACH reached target=%s range=%.2f",
                            appr.target, tr.range);
                        completeCurrent("approach_ok");
                    } else {
                        speedCeil = (appr.speed > 0.0f ? appr.speed : kApproachSpeedDefault) / 100.0f;
                        spF       = kApproachFwdGainHz * (tr.range - kApproachStandoffM);
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
        if (m_planning.load(rlx)) return;
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

        m_planning.store(true, rlx);
        RCLCPP_INFO(this->get_logger(),
            "[FMU_NODE_DEBUG] VLM wake: requesting plan (vision=%d).", static_cast<int>(static_cast<bool>(img)));
        m_planFuture = std::async(std::launch::async, [this, img]() {
            std::string plan;
            callLlamaServer(m_chat.m_initialCommand, img, plan);
            RCLCPP_INFO(this->get_logger(),
                "[FMU_NODE_DEBUG] VLM plan received (%zu chars).", plan.size());
            translateToBaseCommands(plan);
            m_lastPlanUs = nowUs();
            m_planning.store(false, rlx);
        });
    }

    u64 nowUs() const { return __scast(u64, this->get_clock()->now().nanoseconds() / 1000); }

    /* ---- Task lifecycle helpers ------------------------------------------ */
    void activateTask(ActiveTask const& task) {
        Odometry      od;
        Vec3          relFlu, relEnu;
        CmdGo         g;
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
            m_flightState.store(FlightState::TAKEOFF, rlx);
            RCLCPP_INFO(this->get_logger(),
                "[FMU_NODE_DEBUG] TAKEOFF activated; backend handshaking, FMU streaming climb.");
            break;
        case CommandID::LAND:
            m_backend->land();  /* PX4: no-op; FMU streams the descent. */
            m_flightState.store(FlightState::LANDING, rlx);
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
        case CommandID::APPROACH:
            m_approachHaveLastAim      = false;
            m_cannedApproachActivateUs = nowUs();
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
        snprintf(buf, sizeof(buf),
            "[VEHICLE STATE]\nalt_up_m=%.2f speed_mps=%.2f\n\n",
            od.pos.z, std::sqrt(od.vel.x * od.vel.x + od.vel.y * od.vel.y));
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

        arr  = extractJsonArray(flightPlan);  /* strip ```json fences / prose from the VLM. */
        plan = nlohmann::json::parse(arr, nullptr, false);
        if (plan.is_discarded() || !plan.is_array()) {
            RCLCPP_WARN(this->get_logger(), "[FMU_NODE_DEBUG] plan JSON parse failed / not array.");
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
            } else if (action == "approach") {
                approach = CmdApproach{};
                strncpy(approach.target, item.value("target_object", "").c_str(),
                    sizeof(approach.target) - 1);
                approach.speed = item.value("speed", 0.0f);
                cmd = GenericCommand(approach);
                /* Queueable now (3.6); no control-law branch yet -- auto-completes like
                   ORBIT/SEARCH until block 5.1 lands the real servo. */
            } else {
                continue; /* Phase 1: only takeoff/land/stop/go/approach executed. */
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
    u64                       m_lastPlanUs{0};
    u64                       m_missionStartUs{0};
    std::atomic<u64>          m_frameCount{0};

    /* GO world-ENU target + speed (control thread only). Cross-track guidance:
       dir/total frozen at activation define the start->target line; controlLoop
       decays speed along it and pulls back perpendicular drift, without ever
       rotating the commanded forward direction. */
    f32 m_targetN{0.0f}, m_targetE{0.0f}, m_targetD{0.0f}, m_activeSpeed{0.3f};
    f32 m_goStartN{0.0f}, m_goStartE{0.0f}, m_goStartD{0.0f};
    f32 m_goDirN{0.0f}, m_goDirE{0.0f}, m_goDirD{0.0f}, m_goTotalDist{0.0f};

    /* APPROACH coast state (control thread only): last known good aim direction + its
       timestamp, so one briefly-lost detection doesn't immediately FAIL the task
       (spec 2026-08-05-visual-servoing-approach-design.md §6). Reset at activation. */
    Vec3 m_approachLastAimFlu{0.0f, 0.0f, 0.0f};
    u64  m_approachLastAimUs{0};
    bool m_approachHaveLastAim{false};

    /* Canned no-YOLO detection rig (block 5.1 verification, spec §7): when enabled,
       controlLoop synthesizes a PerceptionSnapshot for a fixed world point instead of
       reading the real vision engines. */
    bool m_useCannedApproachRig{false};
    u64  m_cannedApproachActivateUs{0};
};
