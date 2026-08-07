#pragma once
#include <util2/C/base_type.h>
#include "perception/detection_query.hpp"   /* CameraIntrinsics */

/*
    FMU-only tuning. Everything PX4/ROS-wire (topic names, QoS, offboard stream
    rate/warmup, NED setpoint constants) now lives in px4_backend/px4_backend_base.hpp,
    the single source of truth for platform-specific config. Do NOT redefine those
    here — the FMU pulls them in transitively via px4_backend.hpp.
*/

/* ---- Loop rates ---------------------------------------------------------- */
constexpr u32 kMillisecondsInOneSecond = 1000;

constexpr u32 kControlLoopRateHz       = 20;
constexpr u32 kControlLoopPeriodMs     = kMillisecondsInOneSecond / kControlLoopRateHz;


/* ---- Completion / flight tuning (planner-side; frame-neutral) ------------ */
constexpr f32 kGoCompletionRadiusM   = 0.20f;   /* GO done when within 20cm.   */
constexpr f32 kRotateCompletionDeg   = 5.0f;    /* ROTATE done within 5 deg.   */
constexpr f32 kPi                    = 3.14159265358979f;
constexpr f32 kRotateCompletionRad   = kRotateCompletionDeg * kPi / 180.0f;
constexpr f32 kRotateYawGainHz       = 1.5f;    /* P gain: yawrate = gain * yawErr (rad/s per rad). */
constexpr f32 kRotateMaxYawRate      = 0.8f;    /* clamp commanded yawrate (rad/s); gentle turn.     */
constexpr f32 kDefaultGoSpeedCmS     = 30.0f;   /* fallback cruise speed.      */
constexpr f32 kGoApproachGainHz      = 0.5f;    /* position gain (1/s): decel begins at cruise/gain m from target. */
constexpr f32 kGoCrossTrackGainHz    = 1.0f;    /* pulls back toward the start->target line; corrects drift without rotating the forward command. */

/* ---- Takeoff / land profile (ENU, Up+) -- the FMU state machine owns these.
   Backend-neutral: the FMU streams these ENU setpoints; each backend converts
   to its own wire frame (PX4: ENU->NED in px4_backend.cpp). */
constexpr f32 kTakeoffTargetAltEnu = 2.0f;    /* climb target ~2m up (Up+).     */
constexpr f32 kTakeoffClimbVelEnu  = 2.0f;    /* climb at 2 m/s (Up+).          */
constexpr f32 kLandDescendVelEnu   = -0.5f;   /* descend at 0.5 m/s (Down=-Up). */
constexpr f32 kGroundContactEnu    = 0.1f;    /* landed when Up <= ~0.1.        */
constexpr f32 kFlareStartAltEnu     = 0.6f;   /* begin the landing flare (decel) below this Up alt. */
constexpr f32 kFlareTouchdownVelEnu = -0.12f; /* min descent speed at contact (Down=-Up); soft touch. */

/* Momentum-settle dwell between tasks: a just-completed leg leaves real
   residual velocity (worst right after TAKEOFF's climb) that a zero-velocity
   COMMAND doesn't instantly cancel. Holding zero for a short window before the
   next leg locks in its fixed direction keeps that residual out of the next
   leg's line/cross-track math. */
constexpr u32 kGoSettleMs    = 500;
constexpr u32 kGoSettleTicks = kGoSettleMs / kControlLoopPeriodMs;

constexpr u32 kDefaultPromptHistorySize = 256;

/* Event-driven VLM wake: minimum spacing between planning cycles. Prevents the
   queue-empty trigger from hammering the server when the VLM returns an empty or
   unparseable plan (idle re-plan poll). */
constexpr u32 kPlanCooldownMs = 2000;
constexpr u64 kPlanCooldownUs = static_cast<u64>(kPlanCooldownMs) * 1000ULL;

/* Grace period for the camera to start delivering frames before the VLM planner
   falls back to a text-only prompt. Keeps a dead/absent camera from bricking the
   drone while still preferring a vision-grounded plan when one is available. */
constexpr u32 kVisionWarmupMs = 25000;   /* first camera frame lands ~15s after FMU start (DDS+gst+keyframe); wait past that. Once a frame arrives the plan fires immediately -- this is only the dead-camera fallback ceiling. */
constexpr u64 kVisionWarmupUs = static_cast<u64>(kVisionWarmupMs) * 1000ULL;

/* ---- Perception (vision lib) integration ----------------------------------
   Two-rate by design (docs/ROADMAP.md 4.1.8): depth measures ~3x over its
   real-time target on this class of CPU while segmentation meets its target,
   so PerceptionRuntime runs them as two independently-paced loops rather
   than one blocking call. Thread counts are capped so ORT cannot starve the
   20Hz control loop / other llm_to_action nodes sharing this process. */
constexpr const char* kVisionSegModelPath   = "/root/models/vision/vision/yolo26n-seg-384.onnx";
constexpr const char* kVisionDepthModelPath = "/root/models/vision/vision/yolo26n-depth-384.onnx";
constexpr int kVisionSegThreads   = 2;
constexpr int kVisionDepthThreads = 2;
constexpr u32 kVisionSegLoopMs    = 33;   /* ~30 Hz target; measured: meets it. */
constexpr u32 kVisionDepthLoopMs  = 80;   /* measured ~75ms/frame; not a real 40Hz refresh. */

/* ---- APPROACH visual servo (ROADMAP 5.1, spec 2026-08-05-visual-servoing-approach-design.md) --
   Recomputed every control tick from the live camera detection; no world point is stored, so
   nothing here can drift (spec D4). Gains use the same "Hz" (1/s) convention as the GO
   tunables. All first-guess values -- to be swept in SITL (spec §10, §9 R1). */
constexpr f32 kApproachStandoffM     = 2.00f;   /* stop this far from the target. Bigger than the
                                                    servo law strictly needs -- real depth readings
                                                    jitter/freeze on this CPU (SITL, real YOLO), so
                                                    this is slack against a misjudged range, not just
                                                    a stopping point. 1.0m still let range hover right
                                                    at the threshold without a clean below-standoff
                                                    reading, so the drone sat close-range yaw-chasing
                                                    instead of stopping -- clipped the target (SITL). */
constexpr f32 kApproachSpeedDefault  = 80.0f;   /* cm/s, if CmdApproach.speed == 0. Faster cruise so
                                                    the brake ramp below is actually visible against
                                                    it (30cm/s cruise vs near-zero at the end reads as
                                                    "flying slow the whole time", not "decelerating"). */
constexpr f32 kApproachFwdGainHz     = 0.35f;   /* (range-standoff) -> forward speed. Lower than cruise
                                                    speed needs, on purpose: crossover (where this starts
                                                    undercutting the speed ceiling) lands ~2.8m out instead
                                                    of ~1m, so braking is a visible ramp, not a last-instant
                                                    snap -- and gives noisy real depth more distance to
                                                    self-correct before standoff. */
constexpr f32 kApproachYawGain       = 1.0f;    /* horiz bbox error -> yaw-rate.                 */
constexpr f32 kApproachVertGain      = 0.5f;    /* vert bbox error -> vertical velocity.         */
constexpr f32 kApproachLateralDamp   = 0.5f;    /* perpendicular measured-velocity damping (R1). */
constexpr f32 kApproachCoastSpeedMps = 0.15f;   /* speed while coasting on a briefly-lost target
                                                    (not in the spec's tunable table -- same
                                                    first-guess/SITL-tune status as the rest). */
constexpr u32 kApproachLostTimeoutMs = 3000;    /* coast window before FAIL on lost target; real
                                                    seg/depth inference on this CPU lags the 500ms
                                                    canned-rig tuning by seconds, not ms. */
constexpr u64 kApproachLostTimeoutUs = static_cast<u64>(kApproachLostTimeoutMs) * 1000ULL;
constexpr u32 kApproachFreshMs        = 200;    /* a detection older than this is not trusted for
                                                    closing speed -- real depth readings on this CPU
                                                    can freeze for 1s+ under load; acting on a frozen
                                                    range means never decelerating -> collision (seen
                                                    in SITL). Stale-but-not-yet-lost falls back to the
                                                    same slow coast as a fully lost target. */
constexpr u64 kApproachFreshUs        = static_cast<u64>(kApproachFreshMs) * 1000ULL;

/* Camera profile used by the APPROACH servo -- the concrete constant lives once in
   detection_query.hpp (kGzX500GimbalCam) so it is not repeated here and in the unit test. */
constexpr CameraIntrinsics kApproachCamera = kGzX500GimbalCam;

/* ---- Canned APPROACH detection rig (ROADMAP 5.1 verification, spec §7) -------------------
   No-YOLO closed-loop test: synthesizes a PerceptionSnapshot by projecting a target through
   the drone's live pose. The target itself is body-relative, fixed at APPROACH activation
   (not a hardcoded world point) -- SITL spawn heading is not exactly North, so a fixed ENU
   point can land behind the camera depending on that heading. kCannedApproachRigKillAfterMs
   is this session's concrete choice for the spec's underspecified "operator kills the
   detection mid-approach" step -- deterministic and scriptable instead of interactive (this
   system has no mid-flight interactive control channel). */
constexpr f32          kCannedApproachTargetFwdM   = 3.0f;   /* body-forward offset at activation. */
constexpr f32          kCannedApproachTargetUpM    = -1.0f;  /* relative to activation altitude.   */
constexpr const char* kCannedApproachTargetLabel  = "canned_target";
constexpr u32         kCannedApproachRigKillAfterMs = 15 * kMillisecondsInOneSecond;
constexpr u64         kCannedApproachRigKillAfterUs =
    static_cast<u64>(kCannedApproachRigKillAfterMs) * 1000ULL;
