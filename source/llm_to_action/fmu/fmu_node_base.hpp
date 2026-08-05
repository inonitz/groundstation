#pragma once
#include <util2/C/base_type.h>

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
