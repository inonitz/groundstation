# PROJECT CONTEXT RECOVERY — read this first (2026-08-20)
Written to get a cold agent up to speed on the GLOBAL objective after a long, locally-scoped session
drifted from it. Authoritative sources: docs/active/mission-brief-2026-08-15.md, docs/project_overview.md,
docs/ARCHITECTURE.md, docs/ROADMAP.md (CURRENT PHASE banner), the DJI specs below. This file summarizes;
those are canon.

## 1. THE GLOBAL OBJECTIVE (never lose this)
A **voice-commanded autonomous drone** for an **Israeli MOD contest** (Demo Day ~2026-08-28). One line:
**operate a drone by natural-language voice against a LIVE visual scene — parse intent, understand the
scene with CV, execute a physical action.** Flagship success = a **complex command in an UNPLANNED
environment** ("exit through the door").

Scoring that actually matters (from the mission brief):
- FIXED thresholds: **local hardware, no cloud**; **<1 s** end-of-command -> start-of-action;
  **platform-agnostic**; robust to **noise / low light / dynamic scene**; Hebrew (DEPRIORITIZED — demo in
  English on Parakeet).
- SCORED HIGH: noise robustness, **intent-parse accuracy**, **visual-parse accuracy**, **minimal extra
  hardware**, action-vs-intent accuracy.
- SCORED MEDIUM: **sequence of commands** (build context), low latency. LOW: speaker ID.

Control philosophy: **"the VLM plans, deterministic math executes."** A local VLM (Qwen3-VL via
llama-server) is an EVENT-DRIVEN planner OUT of the per-frame hot loop; a deterministic **20 Hz C++
control loop** executes discrete verbs (takeoff/go/rotate/land/stop/approach; orbit/search specced).

Endorsed architecture (mission brief): **voice -> intent parse -> open-vocab perception -> deterministic
control.** Perception must be (a) **open-vocab grounding** (embed the command text + each detection into a
shared space, match by similarity — any description, no fixed taxonomy) and (b) **Re-ID fingerprinting**
(each detection -> a Re-ID vector in an ANN index -> identities that SURVIVE occlusion + re-entry).
Control rides the resolved track_id by bearing (errX/errY) + apparent size from a hover — no absolute
position (survives a position-limited indoor drone).

## 2. PLATFORM (why DJI, not Tello)
- **Tello DROPPED**: no X/Y position source, VPS false-zeros over bare floor. (Earlier "primary"; now dead.)
- Parrot dropped (cost). **Platform = DJI Mini 4/5 Pro**, controlled via **MSDK v5 (Android-only — there
  is NO Linux DJI SDK)**, bridged by an Android device running a teammate's app (below).

## 3. THE C++ SYSTEM = source/llm_to_action/  (the REAL product)
C++17, ROS2, CMake+Ninja+CPM. **No virtual dispatch, no exceptions** (CRTP + tagged dispatch; see
code-guidelines.md). FMU = FlightManagementUnitNode (VLM planner + 20 Hz loop + in-process offboard
translator). Backends hidden behind a **compile-time CRTP `GenericBackend<Derived>`** (start/takeoff/land/
set_velocity/odometry/state); world frame = **ENU** (PX4 speaks NED, Tello/DJI FLU/body — each converts).
Two navigation "beings": **A** (home-relative dead-reckon + in-frame YOLO visual servo — flies today in
SITL, brittle over distance) / **B** (SLAM + OctoMap + A* — specced, scaffolding in source/slam/, not built).

## 4. THE DJI / EXOSKELETONS TRACK (the human's CURRENT hardware task)
- **Exoskeletons app** = `ExoSkeletons/DJI-android-sdk-v5-recon-swarm`, a teammate's Kotlin/Ktor Android
  app (DJI MSDK v5) that runs an **API server on the phone/controller over LAN**. Our Linux stack talks to
  it like any backend. Exposes: `GET /status[/battery|/gps|/signal]` (isFlying, battery, **velocity3D**,
  position3D=GPS/invalid-indoors, attitude, gimbalAttitude); `WS /c/ws/sticks` streaming
  **FlightParam={vx,vy,vz,yaw}** body-frame m/s @ ~18 Hz (also keepalive); `POST /c/takeoff|land`.
  Demo-safety: **Tunneling.kt must NOT start the Cloudflare/Pinggy relay** (local/no-cloud, <1 s budget).
- **Video is the #1 gap.** The app currently streams **RTMP** (~1-5 s latency — breaks the closed see->act
  loop). We asked the author for **raw H.264 NAL over a plain TCP socket** (decode on Linux ~150-300 ms).
  Until then the perception demo uses the RTMP feed via MediaMTX (the Python prototype path).
- **`DjiBackend` (C++)** = sibling of PX4/Tello backends: streams sticks, polls /status -> Odometry
  (dead-reckon position from velocity3D), takeoff/land. Built + tested against
  `scripts/test/dji_mock/mock_apiserver.py` (no drone needed). Specs: spec-dji-backend.md,
  spec-dji-websocket-protocol.md (FROZEN wire), dji-apiserver-review.md, spec-dji-endtoend-bringup.md.
- **The human's task NOW (2026-08-20):** integrate the **RC-N3** (a controller that accepts a phone +
  the SDK app, unlike the locked RC 2 appliance) + the Exoskeletons app + the **new laptop** (the
  field/portable Linux unit) -> real drone control + video into the stack. = Task A/B of the bringup spec.

## 5. THE PERCEPTION PROTOTYPE = source/llm_cv_scene + source/llm_cv_track  (PYTHON, this session)
Rapid Python prototypes built to pass the **2026-08-20 tech-credibility GATE** (prove the system is SMART:
live scene understanding via ASR + strong CV; FLIGHT WAS CUT for the gate). GATE PASSED. These are the
proving ground for the perception layer — NOT the final system.
- **llm_cv_scene (backup):** voice -> Qwen3-VL describes + localizes -> SAM2 mask. 100% local.
- **llm_cv_track (star):** voice -> **OmDet-Turbo** open-vocab detect (box follows) -> SAM2 mask; VLM for
  Q&A only. OmDet loads local/offline in ~1 s (see llm_cv_track/README.md). Detail: that README +
  docs/active/2026-08-20-{demo-runsheet,gate-readiness-assessment,phase2-detector-feeltest}.md.
- **These prototypes prove open-vocab grounding + segmentation. They do NOT yet have the mission brief's
  Re-ID fingerprinting, and they are NOT wired into the C++ FMU or drone control.** That is the gap below.

## 6. WHERE WE ARE (post-gate) — done / WIP / stopped
- DONE: gate passed; Python perception prototypes work (webcam + drone RTMP); DjiBackend built + mock-tested;
  flight-core verbs (GO/ROTATE/APPROACH/ORBIT/SEARCH) SITL-verified; ASR (Parakeet) + noise-robustness bench.
- WIP / OPEN: real drone bring-up (RC-N3 + Exoskeletons + laptop — human, NOW); raw-H.264 video off the drone
  (blocked on the app author); **persistent Re-ID tracking (NOT solved — see 8)**; the C++ integration (below).
- STOPPED / DEFERRED: Tello (dead); Being-B SLAM/OctoMap/A* (specced, deferred); flight-core hardening
  (deferred behind the gate); AGPL escape (Ultralytics YOLO/SAM2/BoT-SORT still AGPL).

## 7. THE CONVERGENCE = feature-total-integration  (what the whole project points at)
Move the proven Python perception into the C++ **source/llm_to_action/** on a branch **feature-total-
integration**, migrating only what fits without breaking the working system (Python models can run as
HTTP model-servers, llama-server style, if a full C++ port is too much for the deadline). Two modes the
human specified, which map onto the architecture:
- **"simple" mode** = BYPASS the VLM planner: voice -> intent parse -> perception -> deterministic verb ->
  execute. For simple tests + Being-A-style direct control. Fast, predictable, demoable.
- **"plan" mode** = give the VLM an initial objective and let it PLAN the flight path (the flagship
  unplanned-environment "exit through the door"). VLM event-driven, out of the hot loop, as specced.
This is the endorsed shape from the mission brief (perception under source/llm_to_action/perception/, VLM
planner + deterministic control). It is the actual Demo-Day-and-beyond target, of which the Python
prototype is a proof of one layer.

## 8. THE HARD OPEN PROBLEM — persistent tracking (SCORED, not optional)
FOLLOW-through-occlusion is a scored MOD capability and the mission brief mandates **Re-ID fingerprinting**
(detection -> Re-ID vector -> ANN index -> survives occlusion + re-entry), shared with the selection
embedding space. Current state: only a WEAK prototype (follow.py, colour histogram) that confuses
look-alikes and churns IDs. **This must be solved with real appearance embeddings (e.g. OSNet) + a vector
index, not colour.** It is arguably the biggest technical gap between the prototype and the graded system.

## 9. HOW THIS SESSION DRIFTED (so it does not recur)
The gate demanded a fast Python CV prototype. The session then spent many turns on LOCAL prototype fixes
(OmDet offline load, ASR mic device, core-dump/exit teardown, UI, VLM-garbage) — all correct locally, but
the GLOBAL objective (the C++ integrated voice->perception->plan->drone system with Re-ID) fell out of
view, and docs got appended-to rather than reconciled. Recovery = this file + the ROADMAP CURRENT PHASE
banner. A new agent should hold section 1 and 7 as the compass and treat the Python prototype as a proven
component to fold in, not the destination.
