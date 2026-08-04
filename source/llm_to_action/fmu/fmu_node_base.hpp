#pragma once
#include <util2/C/base_type.h>


/* ---- Loop rates ---------------------------------------------------------- */
constexpr u32 kMillisecondsInOneSecond = 1000;

constexpr u32 kControlLoopRateHz       = 20;
constexpr u32 kControlLoopPeriodMs     = kMillisecondsInOneSecond / kControlLoopRateHz;

/* DJI Tello cannot ingest setpoints above ~20Hz; publish at 30Hz for margin.  */
/* NOTE (Phase 2): this publish loop moves into the per-platform DroneBackend.  */
constexpr u32 kOffboardPublishRateHz   = 30;
constexpr u32 kOffboardPublishPeriodMs = kMillisecondsInOneSecond / kOffboardPublishRateHz;

/* PX4 rejects an OFFBOARD switch unless setpoints have been streaming for ~1s. */
/* Stream this many before sending set_mode(OFFBOARD)+arm. 40 @ 30Hz ~= 1.33s.  */
constexpr u64 kOffboardWarmupSetpoints = 40;


/* ---- Topics -------------------------------------------------------------- */
/* Camera type + topic (camera/stream) come from rx_node_base.hpp — do not     */
/* redefine here. Odometry is PX4-specific for now.                            */
/* TODO (Phase 2): make the odom topic per-platform — the Tello will NOT       */
/* publish /fmu/out/vehicle_odometry; its driver republishes nav_msgs/Odometry.*/
constexpr const char* kInOdometryTopic     = "/fmu/out/vehicle_odometry";
/* PX4 arming/nav-state feedback — the engage handshake retries until this      */
/* confirms ARMED + OFFBOARD. Firing blind on a timer armed the vehicle before  */
/* the estimator was ready -> motors spun, no climb, auto-disarm.               */
/* NOTE: PX4 message versioning appends _vN (VehicleStatus.msg MESSAGE_VERSION=4) */
/* -> the real topic is vehicle_status_v4, NOT vehicle_status. Odometry is v0 so   */
/* it has no suffix. Bump this if px4_msgs VehicleStatus version changes.          */
constexpr const char* kInVehicleStatusTopic = "/fmu/out/vehicle_status_v4";


/* ---- Completion / flight tuning (all sim-tunable) ------------------------ */
constexpr f32 kGoCompletionRadiusM   = 0.20f;   /* GO done when within 20cm.   */
constexpr f32 kRotateCompletionDeg   = 5.0f;    /* ROTATE done within 5 deg.   */
constexpr f32 kDefaultGoSpeedCmS     = 30.0f;   /* fallback cruise speed.      */

/* NED: down is positive, so "up 1.5m" is -1.5. Reconcile vs old 2m default.  */
constexpr f32 kTakeoffTargetAltNed   = -2.0f;   /* match proven speech_to_action profile (was -1.5). */
constexpr f32 kTakeoffClimbVelNed    = -2.0f;   /* climb at 2 m/s. Weak -1.0 lingered in ground effect -> tipped on uneven terrain before gaining height. Matches speech_to_action. */
constexpr f32 kLandDescendVelNed     =  0.5f;   /* descend at 0.5 m/s.         */
constexpr f32 kGroundContactAltNed   = -0.1f;   /* consider landed near ~0.    */

constexpr u32 kDefaultPromptHistorySize = 256;
