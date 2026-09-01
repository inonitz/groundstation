/*
    tello_slam_hold -- the C2/C3 hover-hold node for the Tello, driven by stella_vslam.

    Owns a TelloBackend (the tello_teleop pattern), subscribes stella's `slam/pose`
    and `slam/tracking_state`, turns the up-to-scale map pose into a metric position
    error, and commands a gentle body velocity to hold station. On tracking loss it
    runs the bounded degrade-then-land recovery. This is the executable that closes
    the position loop the Tello cannot close on its own.

    It reuses three pure headers unchanged, each unit-tested offline:
      - slam_pose_bridge.hpp   map(up-to-scale) -> metric ENU + scale-from-height
      - hover_hold_control.hpp P-dominant + clamped-I hold controller
      - slam_recovery_fsm.hpp  TRACKING -> LOST_HOLD -> (SEARCH_ROTATE) -> LANDING

    FRAME MAPPING (validated on the real Tello in C1, run axistest_20260812).
    stella's map is the camera-optical frame: +x = right, +y = down, +z = forward.
    A forward-facing Tello at roughly level attitude therefore has its horizontal
    ground plane in map (x, z) and its vertical along -y. The bridge is agnostic to
    which fields are horizontal / vertical, so this node feeds it:
        map-horizontal-x = pose.x   (right)
        map-horizontal-y = pose.z   (forward)
        slam-vertical    = -pose.y   (up; y is down)
    The bridge then returns metric ENU with East = right-at-init, North =
    forward-at-init, Up from the Tello's own tof height (never the up-to-scale z).

    HEADING CAVEAT. The world frame is pinned to the map heading at engage (yaw0 = 0),
    so the ENU->body mapping below (forward = +North, left = -East) is exact only
    while the drone holds the heading it engaged at -- which is precisely the
    hover-hold case this node tests. Rotating the world error by a live SLAM heading
    (so the hold survives a yaw) needs the pose QUATERNION convention validated too;
    C1 logged position only, so that rotation is deliberately deferred, wired as a
    single seam (worldErrToBody, headingRad = 0) rather than guessed. Do NOT engage a
    hold after a large yaw until that seam is validated.

    TUNING + DIAGNOSTICS. The controller gains are env-tunable so authority can be
    found on the drone without a rebuild:
        TELLO_HOLD_KP   proportional gain      (default 0.8  1/s)
        TELLO_HOLD_KI   integral trim          (default 0.15 1/s2)
        TELLO_HOLD_MAXV output speed clamp     (default 0.4  m/s)  -- teleop needed
                        ~0.8 to fight indoor drift, so raise this if the hold is weak.
    While holding, the node prints a [hold] diagnostic ~2x/s: the ENU error, the live
    scale, and the actual body velocity command. That line tells a WEAK hold (correct
    sign, tiny/capped velocity) from a SIGN/FRAME bug (velocity pushing the way the
    error grows) -- the exact A-vs-C question a pilot cannot resolve by eye.

    Controls (AsyncKeyHook, same evdev model as tello_teleop):
      T  takeoff            L  land              Esc  land + quit
      H  engage hold (capture the current SLAM position as the setpoint)
      G  release hold (back to a plain zero-velocity hover)

    Build: tello_slam_hold target in the tello_backend CMake, guarded on rclcpp so a
    ROS-less box still builds the rest of the tree.
*/
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <thread>

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <std_msgs/msg/bool.hpp>

#include "tello_backend/tello_backend.hpp"
#include "keyboard/async_key.hpp"
#include "keyboard/key_codes.hpp"

#include "slam_pose_bridge.hpp"
#include "hover_hold_control.hpp"
#include "slam_recovery_fsm.hpp"


/* Topics stella publishes (slam2.hpp). */
static constexpr const char* kPoseTopic  = "slam/pose";
static constexpr const char* kStateTopic = "slam/tracking_state";

/* A pose older than this (no new SLAM sample) is treated as tracking-lost even if the
   last tracking_state said alive -- stella can stop publishing pose the instant it
   pauses, and the recovery must fire on the silence, not wait for a Bool that never
   comes. One-third of a second is ~9 dropped samples at the ~27 Hz measured in C1. */
static constexpr f32 kPoseStaleS = 0.33f;

/* Height hold: a gentle P on the Tello tof, clamped, holds the engage altitude while
   the horizontal controller holds XY. Vertical is metric and trustworthy (tof/baro),
   so a simple proportional term is enough. */
static constexpr f32 kHeightKp    = 0.6f;   /* (m/s) per metre of height error. */
static constexpr f32 kHeightMaxV  = 0.3f;   /* m/s vertical clamp.              */

/* Yaw rate for the SEARCH rotate-scan degrade. Unused while this node holds (it is
   not a SEARCH task), but wired so the FSM's ROTATE_SCAN has a concrete command. */
static constexpr f32 kScanYawRadps = 0.6f;

static std::atomic<bool> g_running{true};


static f32 env_f32(const char* name, f32 fallback) {
    const char* v = std::getenv(name);
    return v ? std::strtof(v, nullptr) : fallback;
}


enum class HoldMode { GROUND, MANUAL, HOLD };


/* Owns the backend, the bridge/controller/FSM, and the latest SLAM sample. The ROS
   timer calls step() at a fixed rate; the pose/state callbacks only stash data, so
   control runs on a steady cadence even when SLAM goes silent. */
struct SlamHold {
    TelloBackend&   drone;
    BridgeAlignment align{};
    HoverHoldController ctrl{};
    RecoveryFsm     fsm{};

    std::mutex      m_mtx;              /* guards the stashed sample + mode. */
    Vec3            m_lastMapRaw{};     /* raw stella pose (x=right,y=down,z=fwd). */
    bool            m_havePose{false};
    std::chrono::steady_clock::time_point m_lastPoseAt{};
    bool            m_trackBool{false}; /* latest slam/tracking_state.       */

    HoldMode        m_mode{HoldMode::GROUND};
    bool            m_haveSetpoint{false};
    Vec3            m_setEnu{};          /* metric ENU hold target.           */
    f32             m_setHeightM{0.0f};  /* engage altitude (m).              */
    std::chrono::steady_clock::time_point m_lastStepAt{};
    bool            m_landing{false};
    u32             m_diag{0};           /* diagnostic-print throttle counter. */

    explicit SlamHold(TelloBackend& d) : drone(d) {
        ctrl.m_cfg.mk_kp     = env_f32("TELLO_HOLD_KP",   ctrl.m_cfg.mk_kp);
        ctrl.m_cfg.mk_ki     = env_f32("TELLO_HOLD_KI",   ctrl.m_cfg.mk_ki);
        ctrl.m_cfg.mk_maxVel = env_f32("TELLO_HOLD_MAXV", ctrl.m_cfg.mk_maxVel);
        std::printf("[hold] gains: kp=%.2f ki=%.2f maxVel=%.2f m/s "
                    "(override with TELLO_HOLD_KP/KI/MAXV)\n",
                    ctrl.m_cfg.mk_kp, ctrl.m_cfg.mk_ki, ctrl.m_cfg.mk_maxVel);
    }

    void onPose(const geometry_msgs::msg::PoseStamped::SharedPtr msg) {
        std::lock_guard<std::mutex> lk(m_mtx);
        auto& p = msg->pose.position;
        m_lastMapRaw = { __scast(f32, p.x), __scast(f32, p.y), __scast(f32, p.z) };
        m_havePose   = true;
        m_lastPoseAt = std::chrono::steady_clock::now();
    }

    void onState(const std_msgs::msg::Bool::SharedPtr msg) {
        std::lock_guard<std::mutex> lk(m_mtx);
        m_trackBool = msg->data;
    }

    /* Engage: capture the current SLAM position as the setpoint on the NEXT good
       sample. Reset the controller + FSM so no stale integral or state leaks in. */
    void engageHold() {
        std::lock_guard<std::mutex> lk(m_mtx);
        if (m_mode == HoldMode::GROUND) return;      /* must be airborne first. */
        m_mode         = HoldMode::HOLD;
        m_haveSetpoint = false;
        ctrl.reset();
        fsm.reset();
        bridgeInitYaw(align, 0.0f);                  /* world heading := engage heading. */
        std::printf("[hold] ENGAGE -- capturing setpoint on next SLAM sample.\n");
    }

    void releaseHold() {
        std::lock_guard<std::mutex> lk(m_mtx);
        if (m_mode == HoldMode::HOLD) {
            m_mode = HoldMode::MANUAL;
            drone.set_body_velocity({ 0.0f, 0.0f, 0.0f }, 0.0f);
            std::printf("[hold] RELEASE -- plain hover.\n");
        }
    }

    void setMode(HoldMode m) { std::lock_guard<std::mutex> lk(m_mtx); m_mode = m; }

    /* Fixed-rate control tick. Reads the stashed sample, runs bridge + FSM +
       controller, and commands the backend. */
    void step() {
        std::lock_guard<std::mutex> lk(m_mtx);

        auto now = std::chrono::steady_clock::now();
        f32  dt  = m_lastStepAt.time_since_epoch().count() == 0
                   ? 0.033f
                   : std::chrono::duration<f32>(now - m_lastStepAt).count();
        m_lastStepAt = now;
        if (dt <= 0.0f || dt > 0.5f) dt = 0.033f;    /* clamp a stall/first tick. */

        if (m_mode != HoldMode::HOLD) return;        /* only HOLD drives control. */

        f32  poseAgeS = m_havePose
                        ? std::chrono::duration<f32>(now - m_lastPoseAt).count()
                        : 1.0e3f;
        bool alive    = m_trackBool && m_havePose && poseAgeS < kPoseStaleS;

        /* Metric height from the Tello ranger; feeds both the scale estimate and the
           vertical hold. tof is cm. */
        f32 heightM = __scast(f32, drone.tof_cm()) * 0.01f;

        /* Map stella's optical frame into the bridge's (horizontal-x, horizontal-y,
           vertical) convention: x=right, z=forward, up=-y. */
        f32 mapX     = m_lastMapRaw.x;
        f32 mapY     = m_lastMapRaw.z;
        f32 slamVert = -m_lastMapRaw.y;

        bridgeUpdateScale(align, slamVert, heightM);
        Vec3 enu = bridgeMapToMetricEnu(align, mapX, mapY, heightM);

        if (!m_haveSetpoint && alive) {
            m_setEnu       = enu;
            m_setHeightM   = heightM;
            m_haveSetpoint = true;
            std::printf("[hold] setpoint E=%.2f N=%.2f U=%.2f m\n",
                        m_setEnu.x, m_setEnu.y, m_setHeightM);
        }

        RecoveryAction act = fsm.tick(alive, /*inSearch=*/false, dt);
        bool diag = (++m_diag % 15u == 0u);          /* ~2x/s at 30 Hz. */

        switch (act) {
        case RecoveryAction::NOMINAL: {
            if (!m_haveSetpoint) { drone.set_body_velocity({0,0,0}, 0.0f); break; }
            /* World XY error, ENU. */
            f32 errE = m_setEnu.x - enu.x;
            f32 errN = m_setEnu.y - enu.y;
            /* ENU error -> body FLU at the engage heading (yaw0 = 0): forward is
               +North, left is -East. See the HEADING CAVEAT above. */
            Vec3 bodyErr = worldErrToBody(errE, errN, /*headingRad=*/0.0f);
            Vec3 v       = ctrl.update(bodyErr, dt);
            v.z          = heightHold(m_setHeightM, heightM);
            drone.set_body_velocity(v, 0.0f);
            if (diag) {
                f32 sc = align.mb_haveScale ? align.m_scale.value() : 1.0f;
                /* err is WORLD ENU (m); vcmd is BODY FLU (m/s). At engage heading,
                   a correct hold has sign(F)=sign(errN) and sign(L)=sign(-errE). */
                std::printf("[hold] HOLD alive=%d err(E=%+.2f N=%+.2f)m scale=%.2f h=%.2f "
                            "vcmd(F=%+.2f L=%+.2f U=%+.2f)m/s\n",
                            __scast(int, alive), errE, errN, sc, heightM, v.x, v.y, v.z);
            }
            break;
        }
        case RecoveryAction::ZERO_VELOCITY:
            ctrl.reset();
            drone.set_body_velocity({ 0.0f, 0.0f, 0.0f }, 0.0f);
            if (diag)
                std::printf("[hold] LOST-HOLD zero-vel (alive=%d poseAge=%.2fs trackBool=%d) "
                            "-- holding for re-track before land\n",
                            __scast(int, alive), poseAgeS, __scast(int, m_trackBool));
            break;
        case RecoveryAction::ROTATE_SCAN:                /* not reached (inSearch=false). */
            drone.set_body_velocity({ 0.0f, 0.0f, 0.0f }, kScanYawRadps);
            break;
        case RecoveryAction::LAND:
            if (!m_landing) {
                m_landing = true;
                std::printf("[hold] recovery LAND -- SLAM did not recover in the hold window.\n");
                std::thread([this]{ drone.land(); }).detach();
                m_mode = HoldMode::GROUND;
            }
            break;
        }
    }

    /* Map a world ENU XY error to a body FLU (forward, left) error. headingRad is the
       drone heading relative to the engage heading; 0 for the pure hold. The seam
       where a live SLAM heading plugs in once its quaternion convention is validated. */
    static Vec3 worldErrToBody(f32 errE, f32 errN, f32 headingRad) {
        f32 c = std::cos(headingRad);
        f32 s = std::sin(headingRad);
        f32 fwd  =  errN * c + errE * s;    /* +North rotated into body forward. */
        f32 left = -errE * c + errN * s;    /* -East  rotated into body left.    */
        return { fwd, left, 0.0f };
    }

    static f32 heightHold(f32 targetM, f32 measM) {
        f32 v = kHeightKp * (targetM - measM);
        if (v >  kHeightMaxV) v =  kHeightMaxV;
        if (v < -kHeightMaxV) v = -kHeightMaxV;
        return v;
    }
};


int main(int argc, char** argv) {
    rclcpp::init(argc, argv);

    TelloBackend drone;
    std::printf("[slam_hold] connecting to Tello (join its Wi-Fi first)...\n");
    if (!drone.start()) {
        std::printf("[slam_hold] FAILED to bind/handshake the Tello.\n");
        rclcpp::shutdown();
        return 1;
    }
    std::printf("[slam_hold] connected. T=takeoff L=land  H=engage-hold G=release  Esc=quit\n");

    auto node = std::make_shared<rclcpp::Node>("tello_slam_hold");
    SlamHold hold(drone);

    /* SLAM pose is BEST_EFFORT/high-rate; tracking_state is a low-rate flag. */
    rclcpp::QoS poseQos(10);  poseQos.best_effort();
    auto poseSub = node->create_subscription<geometry_msgs::msg::PoseStamped>(
        kPoseTopic, poseQos,
        [&hold](geometry_msgs::msg::PoseStamped::SharedPtr m){ hold.onPose(m); });
    auto stateSub = node->create_subscription<std_msgs::msg::Bool>(
        kStateTopic, 10,
        [&hold](std_msgs::msg::Bool::SharedPtr m){ hold.onState(m); });

    auto timer = node->create_wall_timer(
        std::chrono::milliseconds(33), [&hold]{ hold.step(); });   /* ~30 Hz control. */

    AsyncKeyHook keys;
    if (!keys.create()) {
        std::printf("[slam_hold] FAILED to install keyboard hook (need /dev/input access).\n");
        drone.stop();
        rclcpp::shutdown();
        return 1;
    }
    auto onKey = [&hold, &drone](KeyCodeEnum key, KeyAction act) {
        const bool down = (act == KeyAction::PRESSED || act == KeyAction::REPEATED);
        if (!down) return;
        switch (key) {
            case KeyCodeEnum::T:
                hold.setMode(HoldMode::MANUAL);
                std::thread([&drone]{ drone.takeoff(); }).detach();
                break;
            case KeyCodeEnum::L:
                hold.setMode(HoldMode::GROUND);
                std::thread([&drone]{ drone.land(); }).detach();
                break;
            case KeyCodeEnum::H: hold.engageHold();  break;
            case KeyCodeEnum::G: hold.releaseHold(); break;
            case KeyCodeEnum::Escape: g_running.store(false); break;
            default: break;
        }
    };
    for (KeyCodeEnum k : { KeyCodeEnum::T, KeyCodeEnum::L, KeyCodeEnum::H,
                           KeyCodeEnum::G, KeyCodeEnum::Escape }) {
        keys.bindKey(k, onKey);
    }

    while (g_running.load() && rclcpp::ok()) {
        rclcpp::spin_some(node);
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }

    std::printf("[slam_hold] shutting down: landing + stopping.\n");
    keys.destroy();
    drone.stop();
    rclcpp::shutdown();
    return 0;
}
