# Agent 5 — SLAM stabilization & recovery (owner: agent + human)

**Date: 2026-08-11** · Deadline: Wed evening 2026-08-12.

**Mission**: make SLAM close the Tello position loop and give it localization + minimum recovery for a
real "search & fly to the hatted man" run. All greenfield.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + LOCKS + commit rules),
then `CLAUDE.md`, `docs/code-guidelines.md`, `docs/writing-style.md`,
`docs/active/sitl-B1-task5-agent-prompt.md` (prior stella SITL prompt, reference). Study:
`source/slam/slam2.hpp` (publishes `slam/pose` + clouds; `tracker_is_paused` gate at `155`;
`slam1.hpp` is dead — ignore); `tello_backend.cpp` `odometry_impl` (`151`, returns `pos={0,0,height}`)
+ `tello_backend_base.hpp` state schema (velocity vgx/vgy/vgz + height, NO XY); `scripts/test/slam/`
(SITL comparator `compare_ground_truth.py`).

**Verified reality (trust code, not docs)**: nothing consumes `slam/pose` for control today; the Tello
reports no XY position; the ARCHITECTURE doc's "Simpson's-rule dead-reckoning" driver does NOT exist.

**Your place in the plan**: blocked-by Agent 4 (calibration) + the human's manual control. C1 is a
go/no-go gate for C2/C3.

## C1 — Assess on the REAL Tello first (go/no-go; needs manual control)

- Bring up `stella_vslam_monocular` on the Tello `camera/stream` (the `--tello` gstreamer RX feed);
  use Agent 4's calibrated `stella_config_tello.yaml`. Fly a path + a return-to-start loop.
- Measure (no EKF2 ground truth on Tello, unlike SITL): pose rate, **tracking fraction** (pose present
  vs `tracker_is_paused`), **scale consistency** (SLAM z vs metric Tello height), **return-to-start
  error**. SITL only de-risks the bridge code; the quality verdict is from reality.
- **If stella can't hold tracking indoors after calibration, STOP and report** — C2/C3 depend on it.

## C2 — Stabilization test (build; impl + test same bucket)

- **`slam/pose`→Tello odometry bridge**: consume `slam/pose` (map frame, up-to-scale); align map→ENU at
  init (initial yaw/gravity); **resolve monocular scale from the metric Tello height Z**; write XY into
  the Tello `odometry().pos` (today hard-zeroed).
- **Hover-hold controller**: XY position error → `set_velocity` (Tello takes only velocity setpoints,
  `tello_backend.cpp:143-149`). Note: `stop`/hover on the Tello is NOT a no-op like SITL — it must
  actively cancel drift.
- **Measure XY drift SLAM-on (hold) vs SLAM-off (drift)** during a hover. Package a self-contained test
  script (yours alone, no lock).

## C3 — DR + fusion + recovery (minimum recovery is required for the Tello demo)

- Simpson-integrate `vgx/vgy/vgz` from flight start → DR XY pose; expose via `odometry()`.
- Complementary-fuse: SLAM corrects DR bias while alive; DR free-runs when tracking is paused.
- Surface a **tracking-state topic** from `slam2.hpp` (not published today) so the FMU knows when to
  trust SLAM vs DR.
- On loss: hold on DR, seed relocalization with the DR pose, **relocalize against the live in-RAM map**
  (no disk save/load — the session map is already in memory). Re-anchor on success.

## Locks (docs/LOCKS.md)

`source/slam/slam2.hpp`, `tello_backend.cpp`, `tello_backend.hpp`, `tello_backend_base.hpp`,
`dependencies/stella_config_tello.yaml` (with Agent 4). Your new stabilization test script is yours alone.

## Constraints

No git writes — suggest `agent5: slam->odometry bridge` etc. per unit. Prose per `docs/writing-style.md`.

## Report
_(append C1 tracking numbers / C2 drift on-vs-off / C3 recovery result + blockers below)_

### 2026-08-12 — session report (agent5)

**Status one-liner.** stella tracks fine on the real Tello (C1 pass on textured forward scenes). The
hover-hold node is built and instrumented but NOT yet validated on hardware. That validation is the open
blocker.

#### DONE (landed)
- **C1 go/no-go: PASS on textured surfaces.** stella_vslam on the real Tello held clean tracking across
  multi-minute handheld + flown runs: 99–100% uptime, 0 BLIND seconds, ~27 Hz. On a textured forward
  scene stella is solid. The venue's glass/concrete remains the open risk, screened before flight by
  `feature_scout.py`.
- **Frame mapping decoded and validated on hardware** (run axistest_20260812, correlating the raw
  `slam/pose` trace to a scripted forward/right/up motion). stella's map is the CAMERA-OPTICAL frame:
  `+x = right, +y = down, +z = forward`. So a level forward-facing Tello has its horizontal ground plane
  in map `(x, z)` and vertical along `-y`. This is the one mapping I refused to guess; it is now pinned.
- **Pure control headers, all offline-unit-tested** (`runtests.sh`, 4/4 pass): map→ENU alignment,
  scale-from-height with a running median, an optional OneEuro filter behind an on/off toggle, the
  P-dominant + clamped-integral hover-hold PID, and the degrade-then-land recovery FSM.
- **`slam/tracking_state` (Bool) published from `slam2.hpp`** every worker cycle (`= !tracker_is_paused`).
  Built and links in the real SLAM binary.
- **`tello_slam_hold` node built + linked** under the Tello backend config. Instrumented this session
  (per-tick `[hold]` diagnostic) with env-tunable gains. Turnkey harness shipped: `feature_scout.py`
  (venue ORB pre-screen), `c1test.sh`/`digest.sh` (go/no-go), `test3.sh` (hover-hold + land-on-loss),
  `TESTING.md`.

#### WIP (open blocker)
- **Hover-hold is NOT validated. First bare-floor flights did not visibly stabilize.** I am mid-way
  through a weak-authority-vs-sign-bug diagnosis (see gotchas). The node now logs, twice a second, the
  ENU error, the live scale, and the actual body velocity command, so the next flight's `hold_*.log`
  resolves it. Awaiting the human's diagnostic run.
- **Recovery land-on-loss**: coded and offline-tested, hardware-unconfirmed.

#### TODO (not started)
- **Unit A**: `TelloBackend.setSlamPose` + write last-known XY into `odometry().pos` (hold-last when
  paused, `pos.z` stays height). Deferred — only FMU-APPROACH consumes it.
- **ArUco fallback INTEGRATION**: `scripts/tello/slam/aruco_pose.py` exists standalone and its self-test
  passes, but nothing consumes it. Wire it as a second pose source behind a switch (SLAM primary, ArUco
  on loss) AFTER the hover-hold validates. The hover controller is deliberately source-agnostic, so this
  is a wiring job, not a rewrite. Caveat: the tag must be a PHYSICAL printed marker in the FORWARD
  camera's view — on-screen fails (rolling shutter × refresh), and a floor tag is invisible (forward-only
  camera).
- **FMU integration** of the bridge (`slam/pose` → `fmu_node.hpp`) — deferred until other agents finish.
  Header B is ROS-free for exactly this reuse.
- **Smoothing on/off A/B and drift on-vs-off** (external-camera metres via `measure_drift.py`) — only
  meaningful once the hold holds.

#### Design notes + gotchas (the reasoning that only lives in my head)
- **The VPS-vs-SLAM surface confusion that FAKED earlier "good" holds — read this first.** The Tello VPS
  looks DOWN (internal downward camera + optical flow); stella looks FORWARD (the streamed 960×720
  camera). They see DIFFERENT surfaces. Early tests flew over floor chair-mats and the drone held station
  beautifully — but that was the VPS locking onto the mats, NOT SLAM. stella never saw the floor mats; it
  tracked the room ahead. Lesson: floor mats test the VPS, not SLAM, and mask the very drift SLAM must
  cancel. The honest test flies over BARE floor (VPS blinded, `vgx/vgy` read a false zero) so any hold is
  pure SLAM. Bare floor also matches the venue (glass/concrete → VPS dead). NEVER validate SLAM over a
  textured floor.
- **`feature_scout.py`'s "POOR" verdict disagrees with reality.** The live ORB overlay repeatedly read
  POOR while the actual measure node showed 100% tracking uptime. The scout is a strict optimistic-ceiling
  screen; trust the measure node (`[TELLO_SLAM]`), not the scout overlay, for the go/no-go.
- **`return/peak` in the C1 digest is NOT drift-in-metres and NOT a hold metric.** It is an up-to-scale
  return-to-start proxy for a manually flown path. A high value just means the pilot did not fly back to
  the takeoff point. Physical drift needs a fixed-camera clip + `measure_drift.py`.
- **The weak-authority-vs-sign-bug diagnosis (current).** The hover-hold caps output at 0.4 m/s, but
  `tello_teleop.cpp` warns that 0.4 m/s is only 40/100 stick — "not enough authority to fight the
  airframe's own drift indoors" (it defaults teleop to 0.8). So the leading hypothesis is too little
  authority (raise `TELLO_HOLD_MAXV`). The alternative is a frame/sign error pushing the wrong way. The
  `[hold]` diagnostic settles it: correct sign but tiny/capped `vcmd` → weak; `vcmd` pushing the way the
  error grows → sign bug. Gains are env-tunable (`TELLO_HOLD_KP/KI/MAXV`) so authority can be swept live
  with no rebuild.
- **HEADING is pinned at engage (`yaw0 = 0`).** The ENU→body mapping (`forward = +North, left = -East`)
  is exact ONLY while the drone holds the heading it engaged at — the pure hover-hold case. Rotating the
  hold through a yaw needs the pose QUATERNION convention validated, and C1 logged position only. The
  rotation is wired as a single seam (`worldErrToBody`, `headingRad = 0`) but deferred. Do NOT engage a
  hold after a large yaw until that seam is validated.
- **C3 dead-reckoning is DROPPED, not deferred.** `vgx/vgy` are VPS-derived and read a false zero exactly
  when the VPS is blind (the same low-texture condition that kills SLAM). Integrating them would report
  real drift as zero. So there is no DR/fusion path on the Tello. Tracking loss goes to bounded-hold-then-
  land (LOST_HOLD ~2 s → LAND on tof/baro), never to DR. The spec's C3 "Simpson-integrate vgx/vgy" step
  above is superseded by this — kept for history, but do not build it.
- **Scale is resolved live, not fixed.** Monocular is up-to-scale (~1 m real ≈ 0.6 map units in the C1
  run, and inconsistent across axes). The node computes scale per-frame as `tof_height / (-y)`,
  median-smoothed, rather than trusting any constant. tof works over any surface (ToF ranger), so height
  and thus scale stay valid even when the VPS flow is blind.
- **Build reality.** `tello_slam_hold` builds ONLY under a Tello backend config
  (`-DGROUNDSTATION_BUILD_EXECUTABLE=ON -DGROUNDSTATION_BUILD_BACKEND_TELLO=ON`); the shared build is
  normally PX4, so a plain build skips it. This session reconfigured shared → Tello, built the one target,
  and flipped the cache back to PX4 so other agents' builds are undisturbed. The Tello output dir differs
  from the shared/bin dir, so the fresh binary was copied into `build/release/shared/tello/bin/` where
  `test3.sh` looks. Pure CMake, no ament. `slam2.hpp`'s compiled default config is the PX4 airframe — the
  run scripts set `STELLA_CONFIG_PATH` to `config/stella_config_tello.yaml` explicitly.

#### Suggested commits (house style — human runs all git writes)
1. `agent5: slam pose->ENU bridge + hover-hold PID + recovery FSM (pure headers, offline-tested)`
2. `agent5: publish slam/tracking_state (Bool) from slam2.hpp every worker cycle`
3. `agent5: tello_slam_hold node (slam/pose -> hold -> land-on-loss) + CMake target, no ament`
4. `agent5: C1 go/no-go harness + Test 3 hover launcher + venue pre-screen + docs`

#### Files changed
- Modified: `docs/NOTES.md`, `docs/LOCKS.md`, `source/slam/slam2.hpp`,
  `source/llm_to_action/tello_backend/CMakeLists.txt`, this spec.
- New headers: `source/slam/slam_pose_bridge.hpp`, `source/slam/hover_hold_control.hpp`,
  `source/slam/slam_recovery_fsm.hpp`.
- New offline tests: `source/slam/test/{slam_pose_bridge,hover_hold_control,slam_recovery_fsm,hover_hold_sim}_test.cpp`.
- New node: `source/llm_to_action/tello_backend/test/tello_slam_hold.cpp`.
- New scripts: `scripts/tello/slam/{feature_scout.py, run.sh, c1test.sh, test3.sh, measure_tello_slam.py, digest.sh, runtests.sh, aruco_pose.py, README.md, TESTING.md}`.
- `scripts/tello/slam/runs/` is generated logs — gitignore, do not commit.

### 2026-08-12 — Demo 3 ownership: GO/NO-GO (agent5)

Manager assigned Demo 3 (physical stretch): takeoff → FOLLOW the blue-hat/red-shirt person in place →
~30 s later voice "land" = emergency fast-path. My verdict on the SLAM-dependent parts:

**Run Demo 3 SLAM-FREE. NO-GO on anything leaning on the SLAM hover-hold.**

1. **Hover-hold "while FOLLOW runs" — NO-GO, and not a buildable mode by the deadline.**
   - Not validated on hardware (the active blocker; bare-floor flights did not stabilize, mid weak-vs-sign
     diagnosis).
   - Architecture: FOLLOW lives in `fmu_node`; the hover-hold is a standalone binary (`tello_slam_hold`)
     that owns its OWN `TelloBackend`. Two command clients cannot drive one Tello at once. Combining them
     needs the FMU to consume `slam/pose` directly — an integration that does not exist (deferred TODO).
   - It is also unnecessary: FOLLOW of a STATIONARY person already station-keeps — the servo centers the
     person on pixels, so the drone holds position with NO SLAM. The hover-hold only matters when IDLE with
     no target, which "follow in place" is not.

2. **"land" emergency fast-path — GO on the SLAM side.** Native Tello `land()` descends on its own
   baro/tof: no SLAM, no position, reliable. The node already lands on `L` and on recovery-timeout. The
   override ROUTING (keyboard `/fmu/in/override`, voice via the ASR seam) is FMU + Manager's wiring, not
   mine; as long as "land" reaches `drone.land()` / FMU disarm, it lands SLAM-free.

**So Demo 3 hinges on Agent 1's FOLLOW being VERIFIED ON THE TELLO (currently unverified) + the land
routing — NOT on the SLAM hover-hold.** If idle SLAM station-keep is deemed required, that piece is NO-GO
for tomorrow.
