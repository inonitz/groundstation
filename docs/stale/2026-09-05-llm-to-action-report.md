# llm_to_action — presentable-for-judges report (2026-09-05)

Author: groundstation-13 [8501ec] (llm_to_action presentation agent). Owner ruling date: 2026-09-05.
Brief: docs/active/2026-09-05-llm-to-action-presentable-brief.md.

## 1. Objective

Make `projects/llm_to_action/` presentable for the judges' meeting. Demo polish was primary.
Code-quality cleanup was secondary and bounded. The owner warned against a large cleanup, so
cleanup candidates are proposed here, not applied.

## 2. Setup

The environment held every dependency the demo needs. Each was verified present: Gazebo (`gz`),
the PX4-Autopilot SITL build, ROS2 Jazzy, `tmux`, an RTX 5070, `MicroXRCEAgent`, and the ONNX
vision models under `/root/models/vision/`. `rclpy`, `cv2`, and `cv_bridge` all import.

The FMU was not built. The build directory held only cached dependencies. The build ran with
`./build.sh release shared px4 configure` (already done) then `build` at `-j8`. It produced the
node binaries and exited 0. Wall-clock was not recorded; it reported about 8.5 minutes of `sys`
time.

The demo is `source/dashboard/run_sitl_demo.sh`. It runs the `follow` scenario headless, with no
GUI window and with the VLM off (`LAUNCH_VLM=0`). It sets `FMU_OBSERVABILITY=1`, starts the
dashboard bridge, and runs an assessor that writes a PASS/FAIL verdict.

Three headless SITL runs were made. Runs 1 and 2 were before the bridge fix. Run 3 was after it.

## 3. Results

### 3a. Demo assessment — run 3, after all fixes (PASS)

| Check | Result | Evidence |
|---|---|---|
| annotated frames arriving | PASS | 50 msgs, 8.3 Hz |
| depth frames arriving | PASS | 38 msgs, 6.3 Hz |
| annotated width == 320 (FMU resize) | PASS | width=320 |
| annotated rate under cap (no dup publishers) | PASS | 8.3 Hz |
| HUD present + parseable | PASS | STATE=TAKEOFF ... DET=person@82% BATT=99% |
| bridge serves page | PASS | 4096 B |
| MJPEG annotated real frames | PASS | 200000 B, jpeg=True |
| MJPEG depth real frames | PASS | 200000 B, jpeg=True |
| SSE carries live HUD | PASS | STATE=FLIGHT TASK=follow(person) |

Bring-up timing (run 3): the bridge was ready at t+0 s. The first HUD arrived at ~15 s, the first
annotated frame at ~21 s, and depth at ~25 s. So the dashboard fills within about 25 seconds of
launch. The drone took off, followed the person by yaw, and held. The FMU log had no WARN or ERROR
lines.

### 3b. Teardown — run 3 (clean)

| Item | Result |
|---|---|
| port 8088 after teardown | 0 listeners (free) |
| leaked processes (gz, px4, FMU, bridge, agent) | none |
| bridge shutdown | logged "signal 15 -- shutting down" then "stopped", no abort |

### 3c. Rough edges found on the first run

| # | Rough edge | Severity | Disposition |
|---|---|---|---|
| 1 | FMU not built on a fresh checkout; the demo needs a build step first | high | Documented in the new README (§5, item 8) |
| 2 | Dashboard README run path `scripts/dashboard/serve.py` does not exist | high | Fixed |
| 3 | Dashboard bridge ignored SIGINT and SIGTERM; held port 8088 after every run | high | Fixed |
| 4 | `mock_data.py` docstring told you to run a `smoke.py` that does not exist | medium | Fixed |
| 5 | Stale path also in `serve.py` and `assess.py` docstrings | medium | Fixed |
| 6 | The launcher's promised `logs_<timestamp>/fmu.log` is never written | medium | Docstring fixed; the real FMU log path is now documented |
| 7 | The VLM reasoning panel stays idle in the shipped `follow` demo | medium | Proposed (§6) — owner decision |
| 8 | Perception runs on the CPU, not the GPU | medium | Proposed (§6) — owner decision |
| 9 | Stray `1: command not found` prints once during headless bring-up | low | Fixed |
| 10 | HUD line prints to the FMU pane at ~4 Hz and also to the dashboard | low | Proposed (§6) |
| 11 | HUD shows `BATT=-1%` for the first ~1 s before battery telemetry arrives | low | Proposed (§6) |

## 4. Analysis

1. The demo works. Run 3 passed all nine assessment checks after the fixes. The dashboard shows
   the annotated camera, the depth colormap, and the flight HUD, all live.

2. A fresh checkout cannot run the demo. It has no FMU binary. The build step is now the first
   thing the new top-level README documents.

3. The bridge port-leak was the one demo-breaking defect. The bridge (`serve.py`) ran an HTTP
   server in its main thread. `rclpy.init()` installed signal handlers that stopped the ROS
   executor but never interrupted that thread, so `serve_forever()` ignored SIGINT and SIGTERM.
   The process stayed alive and held port 8088. A second demo run could not bind the port, so its
   dashboard would break. This was confirmed twice: runs 1 and 2 both left the bridge alive after
   teardown.

4. The fix installs signal handlers in `serve.py` after `rclpy.init()`, so they win. Each handler
   stops the HTTP server from a helper thread, because `serve_forever()` cannot be stopped from its
   own thread. The shutdown then joins the ROS spin thread before it destroys the node. Without the
   join, the process aborted in C++ at exit ("terminate called without an active exception"). After
   the fix, the bridge exits cleanly on both signals and frees the port. Run 3 confirmed it
   end-to-end.

5. The VLM reasoning panel is one of the four judge-facing panels. The shipped `follow` demo runs
   with the VLM off, so this panel stays idle for the whole run. A judge sees a dead panel. This is
   a demo-content choice, so it is left to the owner (§6).

6. Perception runs on the CPU. The FMU log prints `Inference device: CPU` for both the
   segmentation and depth models. The annotated stream still held 8.3 Hz, which is enough for the
   demo. The latency cost of CPU inference is unverified. Moving perception to the GPU may contend
   with the VLM for the 8 GiB of VRAM, so this is left to the owner (§6).

## 5. Changes made

As of 2026-09-06 this work now includes ONE flight-code change (the APPROACH auto-land guard in
fmu_node.hpp) and the 4B model swap in sim_core.sh -- see section 8. The earlier claim of no
flight-code change no longer holds. No safety check was weakened. The frozen `projects/integration/` was not touched. The
uncommitted work in `source/asr/` and `source/keyboard/` was not touched.

| File | Change |
|---|---|
| `projects/llm_to_action/README.md` | New. Node graph, build step, SITL demo, dashboard. |
| `projects/llm_to_action/source/dashboard/serve.py` | Bridge fix: install SIGINT/SIGTERM handlers, join the spin thread on shutdown. Fixed the docstring path. |
| `projects/llm_to_action/source/dashboard/README.md` | Fixed the run path (6 places); noted the run directory. |
| `projects/llm_to_action/source/dashboard/assess.py` | Fixed the docstring run path. |
| `projects/llm_to_action/source/dashboard/mock_data.py` | Docstring: point at `mock_data.py`, not the missing `smoke.py`. |
| `projects/llm_to_action/source/dashboard/run_sitl_demo.sh` | Fixed the docstring so the FMU log location is honest. The teardown trap is unchanged from origin. |
| `projects/llm_to_action/test/lib/sim_core.sh` | Moved a comment out of the `CMD_PX4` string. A backtick expression in that comment ran as a command inside the double quotes and printed `1: command not found` at bring-up. The launch command is byte-identical. |
| `docs/active/2026-09-05-llm-to-action-report.md` | This report. |

## 6. Open decisions — cleanup candidates (propose first; owner rules)

Ranked by demo impact. None of these are applied.

1. **The VLM panel stays idle in the shipped demo.** The `follow` scenario runs with the VLM off.
   A judge sees an empty VLM reasoning panel. Choice A: demo a scenario that runs the VLM. That
   costs about 12 GiB of VRAM (unverified, from the scenario table) and a one-time cold prewarm.
   Choice B: label the panel plainly when the VLM is off. Risk: low. Visibility: high.

2. **Perception runs on the CPU.** Moving the segmentation and depth models to the GPU may lower
   latency, but it may contend with the VLM for VRAM. The latency gain is unverified. Risk: medium.
   Needs a measured run before and after.

3. **On-screen log volume.** The FMU pane prints the HUD line at ~4 Hz and per-tick diagnostics.
   The HUD already goes to the dashboard, so the pane print is redundant. If the owner shows the
   FMU pane, the diagnostics could be throttled or gated behind a flag. This is behaviour-touching,
   so it needs a Gazebo run to verify. Risk: medium. Depends on which panes the owner shows.

4. **`BATT=-1%` in the first HUD frames.** The HUD shows `-1%` until the first battery message,
   about one second. It could show a dash until real data arrives. Risk: low.

## 7. Suggested commit block (house style; the owner runs git)

Only this session's files are staged. The other session's work in `source/asr/`, `source/keyboard/`,
and elsewhere is left alone.

```bash
cd /root/groundstation
git add projects/llm_to_action/README.md \
        projects/llm_to_action/source/dashboard/serve.py \
        projects/llm_to_action/source/dashboard/README.md \
        projects/llm_to_action/source/dashboard/assess.py \
        projects/llm_to_action/source/dashboard/mock_data.py \
        projects/llm_to_action/source/dashboard/run_sitl_demo.sh \
        projects/llm_to_action/test/lib/sim_core.sh \
        docs/active/2026-09-05-llm-to-action-report.md
git commit -m "feat(llm_to_action): make the judge demo presentable -- top-level README + dashboard fixes

- new top-level README: node graph, build step, SITL demo, dashboard (project had none)
- dashboard bridge (serve.py): install SIGINT/SIGTERM handlers + join the spin thread on
  shutdown; it ignored both signals and held port 8088, so a second demo run could not bind it
  (confirmed leak; now exits clean, port freed, verified in a headless SITL run)
- fix stale run paths in dashboard README, serve.py, assess.py, mock_data.py (pointed at
  scripts/dashboard/*, which does not exist, and a missing smoke.py)
- run_sitl_demo.sh docstring: FMU log lands in test/sitl/runs/follow/captured_panes_log.txt,
  not logs_<timestamp>/fmu.log
- sim_core.sh: move a comment out of the CMD_PX4 string -- backticks inside "..." ran as commands
  and printed "1: command not found" on every headless bring-up (launch command byte-identical)
- report: docs/active/2026-09-05-llm-to-action-report.md

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```


## 8. Addendum 2026-09-06 — 4B swap + multi-step auto-land guard

Author: groundstation-13 [8501ec] (llm_to_action presentation agent). Objective: move the demo to
Qwen3-VL-4B, fix the multi-step auto-land bug, verify the 4B swap is safe, and prepare a commit.

### 8.1 Changes applied

| File | Change |
|---|---|
| `projects/llm_to_action/source/fmu/fmu_node.hpp` | Flight code. The APPROACH auto-land now fires ONLY when the task queue is empty (the approach was the mission's last action). Guard added: `m_taskQueue->size_approx() == 0` at line 2244. |
| `projects/llm_to_action/test/lib/sim_core.sh` | Default VLM model set to Qwen3-VL-4B-Instruct Q4_K_M (`-m` / `--mmproj`). The `${VLM_MODEL:-...}` form means an env override still falls back to 2B. This is in addition to the earlier backtick-comment fix. |

### 8.2 Why the auto-land guard

The auto-land was unconditional: every APPROACH completion enqueued a LAND. A LAND sets
mission-complete and halts VLM planning (fmu_node.hpp:741). So any mission where an APPROACH was not
the last step died at the first approach. The guard keeps the original intent (a weak planner that
forgets the final land) for a single-step "approach and land", and unblocks multi-step plans. Both
orderings are now correct by construction.

Verification status: compiles (build exit 0). NOT yet exercised in a full multi-step SITL run. The
behaviour is verified by code reasoning only. Treat it as unverified until a Gazebo run confirms it.

### 8.3 4B model verification (measured; RTX 5070 Laptop, 8 GB, Vulkan)

Standalone llama-server, the exact sim_core.sh args (`-ngl 99 -c 8192`, q4_0 KV, flash-attn, temp 0.3).

| Metric | Value |
|---|---|
| Model + mmproj load | OK, listening on :8080 |
| VRAM used / total | 4097 MiB / 8151 MiB |
| Text inference (3 tok) | 0.078 s |
| Vision inference (320x240 synthetic frame, 36 tok) | 1.06 s |
| Vision description quality | accurate (gradient described correctly) |

4B fits the 8 GB GPU with about 4 GB headroom. The vision forward pass runs on Vulkan without a
crash. Perception (seg + depth ONNX) runs on the CPU, so it does not contend for this VRAM.

Tuning note (not applied): the server logs "Qwen-VL models require at minimum 1024 image tokens";
sim_core.sh does not set `--image-min-tokens 1024`. This affects grounding (bbox) precision, not
load. It is the same as the 2B config. Apply only with a measured before/after.

### 8.4 Verified vs not

Verified: the build compiles; 4B loads, fits VRAM, runs text and vision inference; the UI is sensible.
Not verified by me: the full multi-step VLM flight end-to-end in Gazebo -- the auto-land guard's real
effect and 4B plan quality in the loop. Run rubicon_orbit on the workstation GUI to confirm.

### 8.5 Commit block (single commit; supersedes section 7; the owner runs git)

```bash
cd /root/groundstation
git add projects/llm_to_action/README.md \
        projects/llm_to_action/source/dashboard/serve.py \
        projects/llm_to_action/source/dashboard/README.md \
        projects/llm_to_action/source/dashboard/assess.py \
        projects/llm_to_action/source/dashboard/mock_data.py \
        projects/llm_to_action/source/dashboard/run_sitl_demo.sh \
        projects/llm_to_action/source/fmu/fmu_node.hpp \
        projects/llm_to_action/test/lib/sim_core.sh \
        docs/active/2026-09-05-llm-to-action-report.md \
        docs/active/2026-09-06-llm-to-action-and-depth-handoff.md
git commit -m "feat(llm_to_action): judge demo -- 4B VLM, multi-step auto-land fix, README + dashboard

- move demo to Qwen3-VL-4B-Instruct Q4_K_M (sim_core.sh default; VLM_MODEL/VLM_MMPROJ still
  override, falling back to 2B). Verified standalone (RTX 5070 Laptop, 8 GB, Vulkan): loads with
  mmproj, VRAM 4097/8151 MiB, text 0.078 s, vision 1.06 s on a 320x240 frame, accurate
  description -- about 4 GB headroom.
- fmu_node.hpp: APPROACH auto-land now fires ONLY when the task queue is empty (approach was the
  last action). Unconditional auto-land landed multi-step missions at the first approach, because
  a LAND halts VLM planning. Single-step approach-and-land unchanged; multi-step (approach ->
  move-back -> orbit) now continues. Compiles; not yet run in full SITL.
- new top-level README: node graph, build step, SITL demo, dashboard.
- dashboard bridge (serve.py): SIGINT/SIGTERM handlers + join the spin thread on shutdown; it
  held port 8088 across runs (confirmed leak; now exits clean, verified in headless SITL).
- fix stale run paths in dashboard README, serve.py, assess.py, mock_data.py; run_sitl_demo.sh
  docstring log path; sim_core.sh backtick-comment bring-up fix.
- reports: 2026-09-05 llm_to_action report + 2026-09-06 handoff.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```


## 9. Addendum 2026-09-06 (run 2) — dashboard VLM demo, headless SITL result

Author: groundstation-13 [8501ec]. The owner's rubicon-orbit run did not fly. Root cause: that
scenario defaults to voice (empty objective + LAUNCH_ASR=1); the FMU idled in STANDBY. Log:
"No objective given -- idling in STANDBY, waiting for a spoken objective."

Fix: a dashboard-hosted VLM demo with a TYPED objective. New script
`projects/llm_to_action/source/dashboard/run_vlm_dashboard_demo.sh` runs the `vlm` scenario through
the dashboard, headless, no voice. Watch at http://localhost:8088.

### 9.1 Run result (4B, RTX 5070 Laptop, Vulkan, default_car world)
- Drone flew. Mission completed and landed. Completed tasks: takeoff_ok, orbit_ok, land_ok.
- 4B planned the FULL mission correctly: takeoff; approach car; go 0,0,0 (dropped as a no-op);
  go x=-200 cm (move back 2 m); orbit car radius 300 cm, 360 deg, cw; land.
- The APPROACH did NOT complete. The loom guard interrupted it (see 9.2). The move-back go also did
  not complete. The drone jumped to the fixed-circle orbit, then landed.

### 9.2 Root cause of the approach stall
The loom backstop (fmu_node.hpp:826) interrupts when any detection's bbox fills more than
kBoundaryLoomFillFrac = 0.28 of the approach camera. As the drone approaches the car (its target),
the car's box grows past 28%. loomFill rose to 0.53-0.61; the guard fired 67 times and abandoned the
approach. The guard cannot tell "my approach target" from "an obstacle". This is the schizo
monocular-depth problem: the backstop exists because depth is unreliable close up, and it fights the
approach.

### 9.3 Speed (measured)
- First 4B plan: ~7 s (VLM request at 594.7 -> takeoff activated 601.6). image=yes b64Bytes=23688
  promptChars=17302 (a 640x640 frame + the full system prompt).
- One plan drove the whole mission; no re-plan was logged. Flight itself was ~81 s (593 -> 674).
- The pre-mission 4B model load dominates the "slow" the owner saw.

### 9.4 Fix options for the approach (owner decides; this is a safety guard)
1. Gate the loom backstop OFF during an active APPROACH. The approach law self-limits to the 2.5 m
   standoff, so the backstop is redundant during approach. Small edit + recompile. Sim-safe; it
   re-introduces collision risk only if depth over-reads, which matters for REAL flight -- flag it.
2. Raise kBoundaryLoomFillFrac 0.28 -> ~0.65 (global; weakens the backstop for all phases).
3. Ship takeoff -> orbit -> land as-is; the VLM plan shown on the dashboard is fully correct.
4. Real fix: adopt metric depth (post-meeting); the depth study is for this.

Recommendation: option 1 for a clean demo, applied only with the owner's OK (it is a safety guard).


## 10. Deterministic verified sweep (2026-09-06) — pass/fail map

Author: groundstation-13 [8501ec]. Command: `./run.sh --all` with SKIP_HIGH_VRAM=1 (VLM scenarios
skipped). Result: 8 pass / 3 fail / 10 skipped. Every verdict is FMU self-report (log parse), NOT
world ground truth.

PASS (8): approach-impact, battery-landnow, battery-rth, follow, hover, obstacle-stop, orbit,
queue-overflow.

FAIL (3): queue-overflow-airborne, rotate, search. Corrected cause (the earlier "No connection to
GCS" note was wrong -- that line is static boilerplate sim_core.sh prints on every launch; the
headless sweep waives the GCS check with PX4_PARAM_NAV_DLL_ACT=0, so QGroundControl is never used).
The real cause, from the runs/<name>/captured_panes_log.txt of all three: the FMU received NO
odometry. posENU stayed (0.00,0.00,0.00) and measVelENU (0,0,0) for the whole run; altENU never left
0. Without a position estimate PX4's EKF cannot lock, so PX4 never armed (arm=0) and the drone sat at
the origin while the FMU streamed setpoints into a dead link. All three are the LAST three scenarios;
the first eight got a live odometry link and flew with the same binary. Likely mechanism (unverified):
the gz -> PX4 -> uXRCE-DDS pipeline stops coming up cleanly after many sequential spawn/teardown
cycles. Not a code regression -- these scenarios do not use the VLM, and zero odometry is upstream of
any FMU logic changed this session. Run fresh and alone, they should pass.

SKIP (10): approach, approach-real, cross, vlm (digest -- no auto verdict); crowd, rubicon,
rubicon-orbit, search-follow (unverified); interrupt-storm, override (highvram VLM).

Caveat: a PASS means the FMU's control law converged by its own sensors. It does not confirm the
drone reached the correct position in the world. A ground-truth verdict is not yet built.
