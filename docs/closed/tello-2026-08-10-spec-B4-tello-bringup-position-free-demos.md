# B4 — Tello bring-up + position-free demos (T1 / T2)

**Status:** scheduled / not started. **Created:** 2026-08-10. **Revised:** 2026-08-09 (session review —
see Revision log). **Branch:** none needed to start — see "Where this runs" below.
**Owner:** operator + agent. **Depends:** none — start immediately, in the current checkout.
**ROADMAP:** 2.3. **Lock:** `scripts/tello/` (new, no contention) + `source/llm_to_action/gstreamer_udp_cam_rx/rx_node.cpp`
(new contention this revision — see Scope; verified via `docs/LOCKS.md` that no other spec running today
touches this file, so no lock entry is needed yet, but add one if that changes). **No `fmu_node.hpp` touch.**

## Objective
Fly the real drone with what needs no position. This is the guaranteed hardware deliverable if SLAM
slips. See `docs/tello_backend_notes.md` for ports/init/keepalive/calibration facts (re-verified against
the current checkout below — some of that doc's "prototype fixes needed" are already done in code).

## Where this runs (2026-08-09 clarification)
No new branch or repo clone is needed to start this today. The two-branch split
(`feature-llm-driver` showcase / `feature-slam-tello` risk path) only matters once B-track work
actually collides with A-track's file scope — and B4 doesn't: it touches `scripts/tello/` (new) and
`rx_node.cpp` (untouched by any spec running today). Work directly in this checkout, same as A1-A4,
coordinating only through `docs/LOCKS.md` same as everyone else. The clone-to-`/root/groundstation_slam`
idea (discussed this session) is for later B-track work that *does* collide with the showcase — B3
touches `fmu_node.hpp`, the same file A3 is using — not for B4/B2, which have no such collision.

## Grounding — re-verified against this checkout, 2026-08-09 (corrects the original spec)
`docs/tello_backend_notes.md`'s "Prototype fixes needed" section is partly stale:
- **Already fixed, not a live risk:** the UDP bind collision — `tello_backend.cpp:169` uses
  `ctello::GetState()` (ctello's own state socket), not a manual `bind(8890)`. The `ReceiveResponse`
  timeout — `tello_backend.cpp:47-56` already bounds the wait (comment explicitly references and avoids
  the naive `while(!ReceiveResponse())` the notes doc warned about).
- **Still a real, unaddressed risk — new finding this session:** the camera RX path is platform-locked
  to the wrong protocol. `source/llm_to_action/gstreamer_udp_cam_rx/rx_node.cpp:24-25` hardcodes
  `udpsrc ... caps="application/x-rtp, ..." ! rtph264depay ! avdec_h264 ! ...` — an **RTP** pipeline,
  correct for Gazebo's simulated camera but wrong for the real Tello, which sends **raw H.264, not
  RTP** (confirmed in `docs/tello_backend_notes.md` and in `tello_backend/test/tello_teleop.cpp`'s own
  header comment: *"Camera: OpenCV VideoCapture over FFMPEG on the raw H264 stream -- test-harness
  only; the real path is gstreamer"* — i.e. the source code itself flags `rx_node.cpp` as the real path,
  and that real path does not currently handle Tello's stream format). `rx_node` is what
  `sim_core.sh`'s `CMD_RX` launches and what feeds `m_currImg` into the FMU/VLM — it is **not**
  optional for T1 ("yaw-scan & describe" needs the VLM to actually see frames). `tello_teleop.cpp`'s
  own `VideoCapture`/FFMPEG path is a separate manual test harness and does not feed the FMU; it does
  not substitute for fixing `rx_node`. **This is now in scope for B4** (see below) — the original spec
  missed it because it only checked the notes doc, not the actual RX pipeline code.
- **Build gap — new finding this session:** `build.sh` unconditionally sets
  `-DGROUNDSTATION_BUILD_BACKEND_PX4=ON` in its `CMAKE_ARGLIST` (see `build.sh:8-18`) and never sets
  `GROUNDSTATION_BUILD_BACKEND_TELLO` — running `./build.sh <cfg> <lib> configure/build` as documented
  will **only ever produce the PX4 binary**, never a Tello one, regardless of arguments. This is the
  concrete instance of the debt already tracked at ROADMAP 9.6 ("reconcile build.sh vs build.ps1
  backend/test divergence"). The top-level `CMakeLists.txt` option (`GROUNDSTATION_BUILD_BACKEND_TELLO`,
  line 42) works correctly — the option just isn't reachable through `build.sh`. Workaround for today
  (do not edit `build.sh` — that's the 9.6 fix, out of scope here): configure a separate build tree
  directly, mirroring `build.sh`'s own flags with the backend swapped, so it doesn't collide with the
  existing PX4 build at `build/release/shared`:
  ```bash
  mkdir -p build/release/tello
  cmake -S . -B build/release/tello -G Ninja \
      -DCMAKE_EXPORT_COMPILE_COMMANDS=1 \
      -DGROUNDSTATION_BUILD_EXECUTABLE=ON \
      -DGROUNDSTATION_BUILD_TESTS=OFF \
      -DGROUNDSTATION_BUILD_BENCHMARKS=OFF \
      -DGROUNDSTATION_BUILD_BACKEND_TELLO=ON \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=1 \
      -DGIT_SUBMODULE=ON
  cd build/release/tello && cmake --build . --target all -j"$(($(nproc)-2>0?$(nproc)-2:1))"
  ```
  Produces `build/release/tello/bin/llm_to_action_fmu_tello` (target name confirmed at
  `source/llm_to_action/fmu/CMakeLists.txt:33-36`: `${PROJECT_NAME}_fmu_${backend_name}`).

## Scope
- **In:**
  1. **Fix `rx_node.cpp` to be platform-aware** (new this revision, blocking for T1): the pipeline
     string needs a Tello variant (`udpsrc port=11111 ! h264parse ! avdec_h264 ! videoconvert !
     video/x-raw,format=BGR ! ...`, no `rtph264depay`) selected alongside the existing PX4/Gazebo RTP
     pipeline. Verified `source/llm_to_action/gstreamer_udp_cam_rx/CMakeLists.txt`: `gstreamer_rx` is
     ONE node/binary, not built per-backend (no `FMU_BACKEND_*` compile definitions reach this target)
     -- so this cannot be a compile-time `#if defined(...)` branch the way `active_backend.hpp` does it.
     Use a runtime CLI arg instead, e.g. `llm_to_action_gstreamer_rx --tello` selecting the pipeline
     string at startup -- this matches the existing launch convention in this codebase (the FMU binary
     already takes `$FMU_CANNED_FLAG` as an argv mode-selector in `sim_core.sh`'s `CMD_FMU`), so it's
     consistent, not a new pattern. `scripts/tello/run.sh` (below) passes the flag; `sim_core.sh`'s
     `CMD_RX` is untouched (no flag = existing PX4/Gazebo behavior, default-preserving).
  2. Tello run config at the real camera resolution (~960x720, per `docs/scheduled/2026-08-10-spec-B2-tello-camera-calibration.md`, not the sim's 1280x720).
  3. A bring-up smoke test: `command`→`streamon`, 16-field state parse, camera decode (now via the
     fixed `rx_node`), 20Hz `rc` keepalive beats the 15s auto-land — already satisfied by the FMU's
     existing 20Hz control loop calling `set_body_velocity` every tick (`kControlLoopRateHz`,
     `fmu_node_base.hpp`); confirm this empirically during bring-up rather than assuming.
  4. `scripts/tello/` (new directory, doesn't exist yet): a `run.sh` playing the same role as
     `scripts/test/lib/sim_core.sh` but for real hardware — no Gazebo/PX4 panes, just the Tello-backend
     FMU binary + `gstreamer_rx` + keyboard node, pointed at the drone's fixed IP (`192.168.10.1`).
  5. Two demos: **T1** yaw-scan & describe (needs the RX fix), **T2** safety stack (failsafe / override
     / emergency stop).
- **Out:** APPROACH/ORBIT/SEARCH/GO — they drift without position (that path is B1->B3->B5).

## Files
- Modify: `source/llm_to_action/gstreamer_udp_cam_rx/rx_node.cpp` (platform-aware pipeline).
- Create: `scripts/tello/run.sh`, `scripts/tello/README.md` (mirrors `scripts/test/README.md`'s
  workflow doc, adapted for real hardware — no `filter.sh`/tmux-capture concept needed for a manual
  flight; note battery life and re-arm/land steps).
- Create: a replay-fixture test per ROADMAP 2.3.6 (see Tests below).

## Tests to create
- **[AUTO / desk]** record a real flight's input/telemetry/frames once, replay as a fixture to assert
  the 16-field parse, odometry integration (`vgx`/`vgy` -> m/s, per `tello_backend.cpp:155-156`), and
  camera decode (post-fix) with no re-flying (ROADMAP 2.3.6).
- **[HUMAN]** the flights themselves (bring-up smoke test, T1, T2) — real hardware, not automatable.

## Acceptance
Clean bring-up on hardware (`rc` keepalive holds past 15s, telemetry parses, video decodes through the
real FMU pipeline, not just the teleop harness); T1 and T2 fly; the replay fixture guards the
parser/odometry off-desk.

## Change-impact (per `docs/code-guidelines.md`)
- **What this changes:** `rx_node.cpp`'s pipeline selection — additive (a Tello branch alongside the
  existing PX4/Gazebo one), does not change the PX4/SITL pipeline's behavior.
- **Breaks existing behavior:** no, if the PX4 branch is left byte-for-byte as-is and only a new
  conditional path is added.
- **Tests that re-run as-is:** all 20 SITL scenarios (A1) — they all exercise the PX4/Gazebo pipeline
  branch, untouched.
- **Tests that are new:** the replay fixture above; a one-time manual confirmation that Tello video now
  decodes through `rx_node` (not just `tello_teleop`).

## Agent notes / operator notes
Batteries last ~10-13 min — charge several before starting. The RX platform-awareness fix should land
and get smoke-tested (does a frame decode at all?) **before** attempting T1, since T1 depends on it
directly; T2 (safety stack: failsafe/override/emergency stop) does not need vision and can be attempted
independently/first if the RX fix is still in progress.

## Revision log
- 2026-08-09: removed stale gremlin warnings (bind collision and `ReceiveResponse` timeout are already
  fixed in code, verified by file:line); added the real current blocker found this session — `rx_node`'s
  gstreamer pipeline is RTP-only (Gazebo), not raw-H264 (real Tello), and T1 needs it fixed first;
  added the `build.sh` PX4-only gap (ROADMAP 9.6) with a concrete workaround build command and the
  confirmed Tello binary name; clarified no branch/clone is needed to start this today; added
  change-impact section.
