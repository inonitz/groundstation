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
constexpr f32 kRotateMaxAngleRad     = 720.0f * kPi / 180.0f;  /* cap a single ROTATE's magnitude. */
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
constexpr f32 kFlareStartAltEnu     = 1.0f;   /* begin the landing flare (decel) below this Up alt (raised 0.6->1.0: slow sooner). */
constexpr f32 kFlareTouchdownVelEnu = -0.12f; /* min descent speed at contact (Down=-Up); soft touch. */

/* ---- Battery failsafe (SITL-tuned; kBatteryReadingUnknown==-1 is skipped) --- */
constexpr i32 kBatteryReturnPct = 20;   /* <= this -> return-to-origin, then land (latched). */
constexpr i32 kBatteryLandPct   = 10;   /* <= this -> land in place now (latched).           */

/* ---- Manual operator override (ARCH 11) ---------------------------------- */
constexpr const char* kFmuOverrideTopic = "/fmu/in/override";  /* std_msgs/Bool takeover toggle. */
constexpr f32 kManualTeleopVelCmS = 50.0f;   /* per-axis manual speed (cm/s); TUNE in sim+real. */

/* ---- Task-queue backpressure --------------------------------------------- */
/* Bounded try_enqueue vs the fixed queue cap; on full, reject-newest + log every
   drop (SPSC-safe: the control thread must never enqueue). Cap plan length too. */
constexpr u32 kMaxPlanActions = 3 * kControlLoopRateHz;   /* == queue capacity. */

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
constexpr const char* kVisionSegModelPath   = "/root/models/vision/yolo26n-seg-384.onnx";
constexpr const char* kVisionDepthModelPath = "/root/models/vision/yolo26n-depth-384.onnx";
constexpr int kVisionSegThreads   = 2;
constexpr int kVisionDepthThreads = 2;
constexpr u32 kVisionSegLoopMs    = 33;   /* ~30 Hz target; measured: meets it. */
constexpr u32 kVisionDepthLoopMs  = 80;   /* measured ~75ms/frame; not a real 40Hz refresh. */

/* ---- A2 observability (2026-08-10): image topics, HUD topic, per-run VLM prompt log ----
   Additive tooling for the live demo -- new publishers + a debug log, no behavior change.
   Topic names match the A2 dashboard mockup (docs/active/2026-08-10-a2-dashboard-mockup.html)
   so the Foxglove/rviz layout and the mockup line up. kVlmPromptLogDir is a compile-time
   constant (this codebase uses zero getenv); only the per-run FILENAME is computed once at
   FMU construction, the same idiom sim_core.sh uses for BAG_DIR timestamps. */
constexpr const char* kVlmViewTopic       = "/fmu/perception/annotated"; /* annotated frame: bboxes+labels. */
constexpr const char* kDepthColormapTopic = "/fmu/perception/depth";     /* depth colormap (normalized+applyColorMap). */
constexpr const char* kFmuHudTopic        = "/fmu/hud";                   /* std_msgs/String human-readable status. */
constexpr const char* kVlmTextTopic       = "/fmu/vlm_text";             /* std_msgs/String: latest VLM reasoning text. */
constexpr const char* kVlmContextTopic    = "/fmu/vlm_context";          /* std_msgs/String JSON: objective + executed-command history. */
constexpr const char* kFmuRatesTopic      = "/fmu/rates";               /* std_msgs/String JSON: perception refresh + publish rates. */
constexpr const char* kVlmPromptLogDir    = "/root/groundstation/vlm_logs"; /* per-run vlm_prompts_<stamp>.jsonl live here. */
constexpr u32         kHudThrottleMs      = 200;   /* ~5 Hz HUD line + /fmu/hud publish. */
constexpr u64         kHudThrottleUs      = static_cast<u64>(kHudThrottleMs) * 1000ULL;
constexpr u32         kA2ImgW             = 320;   /* A2 dashboard downscale width  (lean transport). */
constexpr u32         kA2ImgH             = 240;   /* A2 dashboard downscale height (lean transport). */
constexpr u32         kVlmImageSide       = 640;   /* square side the VLM sees (callLlamaServer resize); VLM bbox coords live in this space. */
/* Central default bbox (VLM 640-space) = "the structure straight ahead". Used when the VLM omits the
   bbox on orbit/approach (the 2B is inconsistent), so "orbit the building in front" is deterministic. */
constexpr i16         kCenterBboxX0       = 220;
constexpr i16         kCenterBboxY0       = 180;
constexpr i16         kCenterBboxX1       = 420;
constexpr i16         kCenterBboxY1       = 380;
constexpr u32         kImgThrottleMs      = 100;   /* ~10 Hz cap on annotated + depth image publish. */
constexpr u64         kImgThrottleUs      = static_cast<u64>(kImgThrottleMs) * 1000ULL;

/* ---- APPROACH visual servo (ROADMAP 5.1, spec 2026-08-05-visual-servoing-approach-design.md) --
   Recomputed every control tick from the live camera detection; no world point is stored, so
   nothing here can drift (spec D4). Gains use the same "Hz" (1/s) convention as the GO
   tunables. All first-guess values -- to be swept in SITL (spec §10, §9 R1). */
constexpr f32 kApproachStandoffM     = 2.50f;   /* stop this far from the target. Bigger than the
                                                    servo law strictly needs -- real depth readings
                                                    jitter/freeze on this CPU (SITL, real YOLO), so
                                                    this is slack against a misjudged range, not just
                                                    a stopping point. 1.0m still let range hover right
                                                    at the threshold without a clean below-standoff
                                                    reading, so the drone sat close-range yaw-chasing
                                                    instead of stopping -- clipped the target (SITL).
                                                    Raised 3.0->4.0: depth over-reads ~2m close up, so a
                                                    3m aim still parked the drone on the car; the boundary
                                                    looming net backstops any overshoot inside standoff. */
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
constexpr f32 kApproachMinAnchorAltEnu = 0.8f;  /* NEVER approach below this ENU alt: a low/hallucinated
                                                   bbox projected through depth can anchor UNDERGROUND
                                                   (seen: z=-1.87) and fly the drone into the dirt ->
                                                   PX4 disarm. Floors both the bbox anchor and the servo
                                                   descent. SITL ground is ENU 0; 0.8 m keeps clearance. */
constexpr f32 kApproachLateralDamp   = 0.5f;    /* perpendicular measured-velocity damping (R1). */
constexpr f32 kApproachCoastSpeedMps = 0.15f;   /* speed while coasting on a briefly-lost target
                                                    (not in the spec's tunable table -- same
                                                    first-guess/SITL-tune status as the rest). */
constexpr u32 kApproachLostTimeoutMs = 3000;    /* coast window before FAIL on lost target; real
                                                    seg/depth inference on this CPU lags the 500ms
                                                    canned-rig tuning by seconds, not ms. */
constexpr u64 kApproachLostTimeoutUs = static_cast<u64>(kApproachLostTimeoutMs) * 1000ULL;
constexpr u32 kApproachRangeMedianWindow = 5;    /* median-filter depth range over N samples; the
                                                    depth model is noisy near the target. */
constexpr f32 kApproachCoastHoldMarginM  = 0.5f; /* if target lost within standoff+this, HOLD
                                                    instead of coasting blind into it. */
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

/* FOLLOW: same visual servo as APPROACH but it HOLDS the standoff and never completes; it
   runs until re-assess or stop (spec agent1). Bbox centering reuses kApproachYawGain /
   kApproachVertGain. Forward gain drives range back to the standoff and is allowed to go
   negative -- the drone backs off when the target closes inside the standoff. */
constexpr f32 kFollowStandoffM      = 2.00f;   /* fallback hold distance (m) when config unset. */
constexpr f32 kFollowFwdGain        = 0.35f;   /* (range-standoff) -> forward speed; sign kept.  */
constexpr u32 kFollowLostTimeoutMs  = 3000;    /* coast window before hovering on a lost target.  */
constexpr u64 kFollowLostTimeoutUs  = static_cast<u64>(kFollowLostTimeoutMs) * 1000ULL;
constexpr u32 kFollowSweepMs        = 4000u;   /* on loss, sweep toward last-seen for this long.  */
constexpr u64 kFollowSweepUs        = static_cast<u64>(kFollowSweepMs) * 1000ULL;
constexpr f32 kFollowSweepYawMaxRps = 0.6f;    /* cap the loss-recovery sweep yaw-rate (rad/s).   */
constexpr u32 kFollowCoastMs        = 800u;    /* on a lost detection, HOLD (coast) this long before
                                                  sweeping -- bridges seg flicker so brief blinks do
                                                  not make the drone yaw-sweep on every gap.          */
constexpr u64 kFollowCoastUs        = static_cast<u64>(kFollowCoastMs) * 1000ULL;
constexpr f32 kFollowEdgeSweepThresh= 0.55f;   /* only sweep-to-last-seen if the target was THIS far off
                                                  centre when lost (i.e. genuinely exiting the frame). A
                                                  centred flicker holds instead of yawing away from a
                                                  target that is still right there.                    */
constexpr f32 kFollowYawGain        = 5.0f;    /* follow bbox-centre yaw gain (snappier than approach's 1.0
                                                  so a moving target stays centred, not trailed by ~0.6). */
constexpr f32 kFollowYawMaxRps      = 1.5f;    /* cap follow yaw-rate so a large error never snaps violently.*/
constexpr u32 kPerceptionCoastMs    = 1500u;   /* feed the VLM the last-seen detection across a blank frame
                                                  for this long, instead of lying "(no detections)".        */
constexpr u64 kPerceptionCoastUs    = static_cast<u64>(kPerceptionCoastMs) * 1000ULL;
constexpr u32 kPerceptionWarmupMs   = 6000u;   /* wait up to this for seg's FIRST detection before the very
                                                  first plan, so we never plan on a warm-up blank frame.    */
constexpr u64 kPerceptionWarmupUs   = static_cast<u64>(kPerceptionWarmupMs) * 1000ULL;

/* ---- Canned APPROACH detection rig (ROADMAP 5.1 verification, spec §7) -------------------
   No-YOLO closed-loop test: synthesizes a PerceptionSnapshot by projecting a target through
   the drone's live pose. The target itself is body-relative, fixed at APPROACH activation
   (not a hardcoded world point) -- SITL spawn heading is not exactly North, so a fixed ENU
   point can land behind the camera depending on that heading. kCannedApproachRigKillAfterMs
   is this session's concrete choice for the spec's underspecified "operator kills the
   detection mid-approach" step -- deterministic and scriptable instead of interactive (this
   system has no mid-flight interactive control channel). */
constexpr f32          kCannedApproachTargetFwdM   = 7.0f;   /* body-forward offset at activation; MUST exceed kApproachStandoffM so the drone flies a real approach, and stay reachable within kCannedApproachRigKillAfterMs at the slow braking approach speed. */
constexpr f32          kCannedApproachTargetUpM    =  0.0f;  /* level with the drone. A below-target point drops out the bottom of the frame as the drone closes, so the synthetic rig (a point, not a car-sized box) loses it just short of the stop and FAILs. Real YOLO approaches keep the box in frame; the canned point must be level. */
constexpr const char* kCannedApproachTargetLabel  = "canned_target";
constexpr u32         kCannedApproachRigKillAfterMs = 120 * kMillisecondsInOneSecond;  /* was 30s: a bbox-anchored approach to a far/high window (~10m + climb at the slow braking speed) needs ~60s+ to REACH; 30s dropped the fixed anchor mid-approach -> approach_lost -> it landed short. */
constexpr u64         kCannedApproachRigKillAfterUs =
    static_cast<u64>(kCannedApproachRigKillAfterMs) * 1000ULL;

/* ---- Interrupt & reactive safety (spec 2026-08-07-spec-1; ROADMAP 1.5/6.1/6.3/6.4) ------
   Emergency boundary is a velocity-scaled standoff: trip = base + scale*speed, so faster
   closing trips earlier. Depth is slow and can freeze on this CPU, so a snapshot older than
   the age cap is treated as "unknown" -- never trip on stale depth. APPROACH motion-gate:
   "reached" is only trusted when yaw-rate + vertical velocity are within nominal -- a real
   collision spikes both while range still reads plausible off the impact frame. Interrupt
   storm (6.3): if kInterruptMaxRetries interrupts fire within kInterruptStormWindowMs the
   drone is stuck in a reflex loop -> escalate the reassess so the model reasons about the
   root cause instead of re-issuing the same tripping action. First guesses -- sweep in SITL. */
constexpr f32 kBoundaryBaseM            = 0.6f;   /* base standoff (m) at zero closing speed.    */
constexpr f32 kBoundaryVelScale         = 0.5f;   /* extra standoff (m) per m/s closing speed.   */
constexpr u32 kBoundaryMaxSnapshotAgeMs = 500;    /* snapshot older than this -> nearest unknown. */
constexpr f32 kBoundaryLoomFillFrac     = 0.40f;  /* bbox-area/frame above this = imminent collision
                                                     regardless of depth (it over-reads/drops out close
                                                     up). ~0.40 trips a car near 1m, well inside standoff;
                                                     a car at the 4m standoff fills ~0.05, so a clean
                                                     approach never trips it. Tune in SITL. */
constexpr f32 kBoundaryDiagRangeM       = 1.5f;   /* boundary diagnostic logs only when something is within this range (near a trip) or looming. Kept tight: monocular depth hallucinates ~4m of "free space" in a featureless scene, which would otherwise flood the log every tick and scroll the real takeoff/burst lines out of the tmux capture. Tune in SITL. */
constexpr f32 kApproachNominalYawrate   = 1.0f;   /* rad/s; at/above = off-nominal (impact).      */
constexpr f32 kApproachNominalVertVel   = 0.6f;   /* m/s; at/above = altitude collapse (impact).  */
constexpr u32 kInterruptMaxRetries      = 3;      /* N interrupts in the window -> escalate.      */
constexpr u32 kInterruptStormWindowMs   = 5000;   /* rolling window for the storm detector.       */

/* ---- ORBIT (ROADMAP 1.1.6): circle a tracked target. At the start a few depth reads are medianed
   into ONE fixed car position (the circle center); the circle is then flown from odometry around that
   fixed point, so the path carries no depth jitter and cannot wobble. The camera turns separately (a
   gentle image-centering) to keep the real car in view. SITL-tune; pending loader (ROADMAP 9.14). */
constexpr f32 kOrbitDefaultSpeedMps = 0.30f;   /* tangential speed around the circle if speed==0 (m/s).  */
constexpr f32 kOrbitRadialGainHz    = 0.5f;    /* (radius - dist) -> radial speed: hold the circle.      */
constexpr f32 kOrbitYawGain         = 1.0f;    /* look-angle error (rad) -> turn rate: aim at locked center.*/
constexpr f32 kOrbitAimTrimGain     = 0.30f;   /* small vision trim on top of the odometry aim (no hard chase).*/
constexpr f32 kOrbitMinRadiusM      = 3.0f;    /* floor on the orbit radius: never fly closer than this to the locked centre (collision guard), even if the VLM asks for a tiny radius_cm. */
constexpr f32 kOrbitMaxRadialMps    = 0.25f;    /* cap on the visual-servo orbit's forward/back (range-hold) speed. */
constexpr f32 kOrbitMinTangentialMps= 0.6f;    /* floor on the orbit strafe speed so it circles in reasonable time. */
constexpr f32 kOrbitFixedRadiusM    = 7.0f;    /* HARDCODED orbit: centre is this far straight ahead of orbit-start AND the radius, so the drone starts ON the circle (never flies inward). */
constexpr f32 kOrbitFixedAltM       = 4.0f;    /* HARDCODED orbit: minimum altitude (ENU) to hold -- safely above terrain, cannot descend into it. */
constexpr f32 kOrbitAimGateM        = 2.0f;    /* vision aim-trim only when the nearest structure is within this of the locked range (else it is a different object -- ignore it). */
constexpr f32 kOrbitCorrErrXGate    = 0.40f;   /* correct the centre only when the structure is within this |errX| (well-centred = it IS the building, not a spurious side object). */
constexpr f32 kOrbitCenterCorrAlpha = 0.04f;   /* low-pass rate for continuously correcting the orbit centre toward the OBSERVED building each tick (slow => converges, no chase/divergence). */

/* ---- SEARCH (ROADMAP 1.1.7): a parallel-track (lawnmower) sweep at fixed altitude. Fly a straight
   lane, step sideways by the lane spacing, fly the next lane back the other way, repeat -- parallel
   lanes covering a rectangle. Detection runs every tick. Distances come from odometry (drifts on
   Tello), so a per-phase timeout also advances the pattern. SITL-tune; pending loader (ROADMAP 9.14). */
constexpr f32 kSearchSweepSpeedMps  = 0.50f;   /* cruise speed along a lane / cross step (m/s).         */

/* 2026-08-10: three fixed size presets instead of one flat grid, chosen per-search by the VLM
   (CmdSearch::size) rather than the system auto-measuring the room -- that measurement doesn't
   exist yet. MEDIUM is byte-for-byte the old flat constants, so an unspecified/old-format plan
   behaves exactly as before. legTimeoutMs must comfortably exceed laneLengthM / kSearchSweepSpeedMps
   or the leg times out before ever reaching its own intended length -- LARGE's timeout is NOT the
   old flat 20s scaled up, it is sized for LARGE's own lane length. */
struct SearchSizeParams {
    f32 laneLengthM;
    f32 laneSpacingM;
    u32 maxLanes;
    u32 legTimeoutMs;
};
constexpr SearchSizeParams kSearchSizePresets[3] = {
    /* small  */ { 3.0f,  1.0f, 4, 10000 },
    /* medium */ { 6.0f,  2.0f, 6, 20000 },   /* == the old flat kSearchLaneLengthM/Spacing/MaxLanes. */
    /* large  */ { 10.0f, 3.0f, 8, 30000 },
};
constexpr u32 kSearchDefaultSizeIdx = 1;       /* medium -- old behavior when size is unspecified.     */
constexpr u32 kSearchReturnTimeoutMs = 70000;  /* return-to-start leg after SEARCH is exhausted (spec:
                                                a failed SEARCH must not strand the drone away from
                                                where it started). 2026-08-10: one flat bound covering
                                                even the LARGE preset's worst case (maxLanes*spacing
                                                diagonal with laneLengthM, 8*3.0/10.0 -> ~26m at
                                                kSearchSweepSpeedMps ~= 52s) with real margin, rather
                                                than a 3rd per-size constant to keep track of.         */
/* kSearchLegTimeoutMs is now per-size (SearchSizeParams above); kept no non-size-indexed constant
   around to avoid a stale value someone reads instead of the real one. */
constexpr f32 kSearchMinConfidence  = 0.25f;   /* reject weak/phantom hits; keep searching below this. 0.25: a person at ~10m only scores 25-53%, and 0.35 dropped real red hits so the search never stopped. */
