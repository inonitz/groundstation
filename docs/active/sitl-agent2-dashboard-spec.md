# Agent 2 — Live dashboard (lean) + 320×240 downscale

**Date: 2026-08-11** · Deadline: Wed evening 2026-08-12.

**Mission**: a lean browser dashboard — camera + depth + detection boxes + HUD tiles + VLM reasoning —
that does NOT hurt system performance mid-test/flight/demo. Communication MUST stay lean.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + LOCKS + commit rules),
then `CLAUDE.md`, `docs/code-guidelines.md`, `docs/writing-style.md`. Study:
`docs/active/2026-08-10-a2-dashboard-mockup.html` (the visual target); `fmu_node.hpp`
`publishAnnotatedFrame` (`1260-1266`) + `publishDepthColormap` (`1270-1281`) + HUD assembly
(`1329-1345`) + `callLlamaServer` (`~1871`); `perception_runtime.hpp` seg/depth loops; the
`mb_observability` gate wiring (`fmu_node.hpp:280-316`).

**Your place in the plan**: presentation wow + a live debug tool. Independent — start now. Boxes are
already baked into the annotated image, so v1 just shows that image (no vector-box plumbing).

## Build

- **FMU downscale (lean transport, C++)**: in `publishAnnotatedFrame` and `publishDepthColormap`, add
  `cv::resize(..., cv::Size{320,240}, cv::INTER_AREA)` before `toImageMsg()`. Throttle to ~10 fps with
  `m_lastAnnUs`/`m_lastDepthUs` guards mirroring `kHudThrottleUs` (`fmu_node_base.hpp:100`). Keep it
  ALL under the existing `mb_observability` gate — OFF must stay zero-cost (this is what protects
  takeoff). Add `m_lastVlmText` cache + an obs-gated `/fmu/vlm_text` `std_msgs/String` set in
  `callLlamaServer` (the HUD only carries `busy/idle` today).
- **Bridge** `scripts/dashboard/serve.py` (new, no lock): an `rclpy` node + stdlib
  `ThreadingHTTPServer`. Subscribe `/fmu/perception/annotated`, `/fmu/perception/depth` (JPEG-encode
  via `cv_bridge`+`cv2`), `/fmu/hud`, `/fmu/vlm_text`. Serve `dashboard.html`, one MJPEG
  `multipart/x-mixed-replace` endpoint per image, and `/events` SSE for HUD + VLM log. **Zero pip deps**
  — websockets/rosbridge/foxglove are NOT installed; do not add them. Single process, cheap.
- **Browser** `scripts/dashboard/dashboard.html` (new): adapt the mockup — replace its `setInterval`
  self-sim with `new EventSource('/events')` + two `<img>` MJPEG panels.

## Constraint (hard)

Measure that dashboard ON does NOT break takeoff and keeps total app RSS < 8 GiB (we hit this
regression before — full 1280×720 publishing starved the VLM). Prefer FMU-side resize over shipping
full frames. If you must choose, leanness wins over prettiness.

## Tests (with the human)

`FMU_OBSERVABILITY=1` SITL run + `python3 scripts/dashboard/serve.py`; open `http://localhost:<port>`;
confirm camera + depth + boxes + HUD + VLM update live with FMU CPU low; re-run a takeoff to confirm no
regression and RSS < 8 GiB.

## Locks (docs/LOCKS.md)

`fmu_node.hpp`, `fmu_node_base.hpp` — short holds; Agents 0 and 1 also edit `fmu_node.hpp`. New
`scripts/dashboard/*` files are yours alone.

## Constraints

Concise intentful code. No git writes — suggest `agent2: dashboard bridge + downscale`. Prose per
`docs/writing-style.md`.

## Report
_(append findings / blockers / decisions below)_

### 2026-08-11 — agent2 build complete (compile verify pending)

**Done.**
- `scripts/dashboard/serve.py` (new, mine): one `rclpy` node + `ThreadingHTTPServer`, zero pip deps.
  Subscribes `/fmu/perception/annotated`, `/fmu/perception/depth` (JPEG q70 via `cv_bridge`+`cv2`),
  `/fmu/hud`, `/fmu/vlm_text`. Serves `dashboard.html`, one MJPEG `multipart/x-mixed-replace` endpoint
  per image (`/stream/annotated`, `/stream/depth`), and `/events` SSE for HUD + VLM text. Image queue
  depth 1 so a slow encoder drops stale frames instead of backing up. MJPEG loop sleeps 0.1s (~10 fps
  ceiling). SSE blocks on a condition var and only wakes on a real HUD/VLM change (15s keep-alive tick).
- `scripts/dashboard/dashboard.html` (new, mine): the mockup restyled with the sim removed. Two `<img>`
  MJPEG panels + one `EventSource`. Parses the fixed HUD line into tiles + a detection list. VLM text
  goes into the reasoning log via `textContent` (no HTML injection from model output).
- `fmu_node_base.hpp`: added `kVlmTextTopic` (`/fmu/vlm_text`), `kA2ImgW`/`kA2ImgH` (320/240),
  `kImgThrottleMs`/`kImgThrottleUs` (~10 Hz).
- `fmu_node.hpp` (all under the existing `mb_observability` gate — OFF stays zero-cost):
  - `publishAnnotatedFrame`: ~10 Hz throttle (`m_lastAnnUs`) + `cv::resize` to 320x240 `INTER_AREA`
    before `toImageMsg()`.
  - `publishDepthColormap`: throttle (`m_lastDepthUs`) placed BEFORE the normalize/colormap work so the
    CPU cost is skipped, not just the publish; then resize to 320x240.
  - `m_pubVlmText` publisher created in the obs gate; `callLlamaServer` caches `m_lastVlmText` and
    publishes the reasoning text after a successful parse.

**Decisions.**
- Throttle counters (`m_lastAnnUs`/`m_lastDepthUs`) are plain `u64`, not atomic: each is touched by a
  single perception thread (seg for annotated, depth for depth). No cross-thread race.
- Depth throttle sits before the colormap, not after — the point is to spend no CPU on dropped frames.
- Leanness over prettiness: FMU ships 320x240 already, so the bridge only re-encodes what arrives and
  never requests full frames. This is the fix for the earlier 1280x720 RSS regression.

**Locks.** `fmu_node.hpp` + `fmu_node_base.hpp` acquired 11:39Z, released after the edits. Both FREE now.

**Compile.** Incremental `release shared px4` build PASSED (exit 0, 0 errors): `fmu_node.cpp.o` rebuilt
and `bin/llm_to_action_fmu_px4` linked. `serve.py` passes `py_compile`.

**Tests (with human).** `FMU_OBSERVABILITY=1` SITL run + `python3 scripts/dashboard/serve.py`; open
`http://localhost:8088`; confirm camera + depth + boxes + HUD + VLM update live with FMU CPU low; re-run
a takeoff to confirm no regression and total app RSS < 8 GiB.

**Suggested commit** (human runs it): `agent2: dashboard bridge + downscale`


### 2026-08-11 — live verification against the real FMU (headless, no drone)

Ran the real `llm_to_action_fmu_px4` binary with `FMU_OBSERVABILITY=1`, fed synthetic camera frames
on `camera/stream`, and let its real ONNX perception drive the topics. No PX4/Gazebo/VLM needed for the
image path. Verified end-to-end:

- `observability=ON`, both ONNX models load, topics appear only under the gate.
- Annotated frame width = **320** (real `cv::resize` on the live perception output).
- Publish rate in a clean `ROS_DOMAIN_ID`, single publisher: **~7.5 Hz annotated / ~6.5 Hz depth** --
  under the 10 Hz cap. Throttle confirmed working on the real perception loop.
- Real HUD line, with the DET field carrying live YOLO detections (e.g. `sports ball@62%`, `frisbee@28%`
  frame-to-frame). VLM=idle (no VLM server up); the 66 `VLM HTTP error` lines are expected.
- Website: page + both MJPEG streams (real JPEG frames) + SSE HUD, all live through `serve.py`.
- Independently re-verified by a second agent reviewing the FMU log + curling the site: all PASS.

False alarm worth recording: an early measurement read ~28 Hz and looked like a broken throttle. Root
cause was the test harness, not the code -- FMU processes killed abruptly left phantom DDS publishers on
the default domain that inflated the topic-level rate. In a clean domain with one publisher it is the
correct ~7.5 Hz. Temporary debug instrumentation was added and removed; no code change resulted.

Enabling fix landed: `scripts/test/lib/sim_core.sh` `CMD_FMU` now exports
`FMU_OBSERVABILITY=${FMU_OBSERVABILITY:-}` so the var reaches the FMU's tmux pane; default stays OFF.

Still pending (need the full stack / hardware): Layer 4 takeoff regression + RSS < 8 GiB under real VLM
load, and all of HITL.

### 2026-08-11 — packaged self-assessing test (headless Gazebo)

New `scripts/test/SITL/dashboard/` (run.sh + README): brings up the moving_person FOLLOW demo with
Gazebo HEADLESS (no GUI), FMU_OBSERVABILITY on, GCS arm-check waived; starts the dashboard bridge; runs
`scripts/dashboard/assess.py`, which checks the whole pipeline and writes a PASS/FAIL verdict. Logs land
in `logs_<stamp>/` (fmu, dashboard, assessor, verdict). The stack is a child process (its own sim_core
cleanup trap); the wrapper owns only the bridge. `sim_core.sh` CMD_PX4 now passes `HEADLESS` through.

Verified on a full headless SITL run: **DASHBOARD ASSESSMENT: PASS (9/9)** -- real camera 1280x720 from
Gazebo -> perception -> 320x240 annotated/depth at ~7.6 Hz (under cap), HUD with live `DET=person@83%`,
MJPEG + SSE serving real frames. `serve.py` now has file logging (`--log`, `--verbose`); the assessor's
SSE check was fixed (it demanded a fixed byte count under a short timeout; now reads until one event).

Caveat surfaced, not a dashboard issue: takeoff is VLM-latency-bound. On the 4 GB GTX 1050 Ti, Qwen3-VL-2B
contended with Gazebo + ONNX can take longer than the run window to return the first plan, so the drone
may stay STANDBY. A less contended probe did complete a plan and reach FLIGHT. Stack/VLM tuning, Agent 1.

### 2026-08-12 — CPU benchmark, executor decision, debug-image knobs

Live headless-SITL flight (moving_person FOLLOW, Gazebo headless): the drone armed, took off, and
followed the person (`STATE=FLIGHT`, `TASK=follow(person)`, real YOLO `DET=person@90%`), with the VLM
producing 6 plans over 10 min and the dashboard live throughout. Total stack RSS 2.29 -> 2.44 GiB
(well under the 8 GiB budget), stable, no leak; publish rate 3.3-7.9 Hz (under the 10 Hz cap the whole
time). Takeoff is VLM-latency-bound on the 4 GB GPU -- sometimes the first plan lands after the window,
leaving the drone in STANDBY; that is stack/VLM behavior, not the dashboard.

Bridge CPU A/B on the saturated box (baseline = committed pre-optimization bridge; per-process CPU via
/proc, two readings each; the single-threaded row is an isolation test that changed only the executor):

| bridge config | idle CPU | watched CPU | threads |
|---|---|---|---|
| baseline (always-on subs, ThreadingHTTPServer) | 4.7% | ~5% | 16->19, unbounded |
| 2-thread MultiThreadedExecutor | 2-3% | ~9% | 23->24 |
| single-threaded (shipped) | 0.5% | 3.9% | 22, bounded |

Decision: ship single-threaded. rclpy's `MultiThreadedExecutor` roughly doubled watched CPU for this
light workload (two 10 Hz encodes fit one thread); single-threaded is leanest on both idle and watched.
Kept the dynamic image subscriptions (subscribe only while a browser streams), encode-gating, and the
bounded HTTP worker pool -- together they drop idle CPU ~90% vs baseline (4.7% -> 0.5%).

Debug image quality (for closer inspection without a freeze): `FMU_A2_IMG_W`/`FMU_A2_IMG_H` (FMU env)
override the 320x240 publish size, clamped to source; bridge `--quality` sets JPEG quality. The FMU
image sinks now skip when `get_subscription_count()==0`, so with the bridge's on-demand subs the FMU
does image work ONLY while a browser is watching -- a high debug resolution costs nothing when
unwatched, and stays 10 Hz capped when watched. Verified: `FMU_A2_IMG_W=960 FMU_A2_IMG_H=540` published
960-wide annotated + depth.
