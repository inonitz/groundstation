# SLAM + DJI Tello bring-up plan (2026-08-09)

The actionable path from a green SITL POC to real-Tello autonomy. This supersedes the scattered
notes from the planning session. The objective tree and status live in [ROADMAP.md](../ROADMAP.md)
(SLAM = 7.1, Tello = 2.3); this doc is the execution order.

## Where we are

The SITL feature suite is green (20 tests, see the ROADMAP matrix). The VLM plans and the
deterministic FMU executes. What blocks real flight is position.

The Tello has no horizontal position. `TelloBackend::odometry_impl()` returns `pos={0,0,h}`. SDK 1.3
telemetry is velocity, height, and attitude only -- no x/y. Dead-reckoning `vgx`/`vgy` drifts, and
the error is sensor bias, not the integration rule, so a better integrator does not fix it. It is a
short stopgap at best.

Monocular stella_vslam (`source/slam/slam2.hpp`) is the real path. It is camera-only and mostly
built: it compiles and links, the 42.9 MB ORB vocabulary and a config are present, the pose code is
written but the rviz publish is commented out, and `rx_node.cpp` already decodes the Tello H264 feed
into an image. The open question is whether it tracks, and that is what we front-load.

## Gating

Nothing here touches the FMU control loop until the spec-1 + spec-2 feature commit lands. Two tracks
run in parallel before that, and neither edits the FMU.

## Track 1 -- camera calibration (operator, ground, no flight)

Print a checkerboard of known square size. Stream the Tello video and capture 20-40 frames that
cover the image at varied angles and distances. Run OpenCV `calibrateCamera` (or the ROS
`camera_calibration` GUI). Read out intrinsics, distortion, and reprojection error (aim under ~1 px).
Write them into `dependencies/stella_config.yaml`, and fix the resolution to the real Tello
(~960x720), not the sim's 1280x720. Roughly 30-60 minutes with the tooling ready.

## Track 2 -- stella_vslam SITL bring-up (overseer)

Uncomment the pose publish. Align the camera topic to the Gazebo sim. Run it and confirm `slam/pose`
tracks and the map builds. This is a separate node with no FMU edit. It answers the one real risk:
does stella track at all?

## Phase 2 -- after the feature commit, FMU clean

Wire `slam/pose` into the FMU as the Tello's position, and add return-to-start. Scale-free pose is
fine for a return via relocalization; a metric return needs a scale anchor, and the Tello ToF or
baro altitude is the obvious one.

Wire the voice interrupt and completion in the same phase. Route the ASR transcript to
`raiseInterrupt("user_command")` and stash the text. `buildDynamicPrompt` appends a `[USER]` block,
so a spoken "done, land" stands the drone down. Add the completion-verdict block (below) to the
reassess prompt at the same time.

## Phase 3 -- hardware, next Tello session

Swap the sim config for the calibrated Tello config. Bring stella up on the real drone and tune.
Flights are 10-15 minutes on a charged battery. Keep people clear of the flight area. If real-camera
tracking is shaky, fall back to a dumb visual anchor.

## Mission termination -- layered

There is no deterministic "objective achieved" detector today. The fix is defense in depth.

1. A completion verdict in every reassess. The reassess prompt emits a structured
   `{"objective_complete": bool, "reason": "..."}` first, grounded in the executed history that is
   already in the prompt. If complete, it lands or stops; otherwise it plans. This is prompt work,
   not new plumbing, and reliability scales with model size.
2. Human-voice completion, the authoritative backstop. The operator says "done, land" and the
   `[USER]` block stands the drone down. This rides on the Phase 2 voice work.
3. The battery failsafe, the hard floor. Already shipped.

## Rejected and shelved

OpenVINS (`slam1.hpp`) needs a high-rate IMU the Tello lacks. Dead-reckoning as the primary source
drifts on sensor bias. Moving depth onto the GPU beside the Vulkan VLM has no easy
hardware-agnostic path, so it stays on the CPU -- the VLM owns the GPU, perception owns the CPU, and
the split is clean.

## Debt carried forward (not blocking)

`fmu_node.hpp` is ~2044 lines with every law inline in `controlLoop()`; extract per law post-POC.
`async_key.cpp` is ~701. Test capture is fragile -- tee FMU stdout to a file so events are not lost
to tmux scrollback. The tuning constants are compile-time `constexpr` and must become loadable
runtime config before one binary can serve both SITL and the real Tello (ROADMAP 9.14,
[docs/scheduled/2026-08-08-runtime-drone-config-constants.md](../scheduled/2026-08-08-runtime-drone-config-constants.md)).

## Verification gates

Track 2 passes when `slam/pose` tracks in Gazebo before any FMU wiring. Phase 2 passes when the pose
feeds the FMU and return-to-start works in sim, and when a spoken "done, land" stands the drone down.
Phase 3 passes when tracking holds on the real camera indoors with CPU headroom beside perception,
and tracking-loss falls back to the anchor -- all before any outdoor flight, with people kept clear.
