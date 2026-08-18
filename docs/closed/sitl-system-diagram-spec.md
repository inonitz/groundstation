# System diagram — one unified SITL + Tello technical diagram (owner: agent + human)

**Date: 2026-08-12** · Deadline: Wed evening 2026-08-12.

**Mission**: produce one technical diagram of the whole system, drawn "as if all features land". One
diagram set covers both deployment targets — SITL (PX4 + Gazebo) and the physical Tello — with
shared, SITL-only, Tello-only, and new-this-push components visually distinguished. It is a
presentation asset and an onboarding map.

**State of the art (read this first, it is easy to misremember)**: the diagram does NOT exist yet.
What exists is a plan for it (this spec) and two text/visual sources to draw from:
`docs/ARCHITECTURE.md` (the authoritative text description) and
`docs/active/2026-08-10-a2-dashboard-mockup.html` (a UI mockup, not a system map). There is no mermaid
or UML artifact in the repo. Build it.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md`, `CLAUDE.md`, `docs/writing-style.md`,
`docs/ARCHITECTURE.md`. Cross-check every component and topic name against the landed code, not the
docs — the docs are known to drift (ARCHITECTURE still claims a "Simpson's-rule dead-reckoning" Tello
driver that does not exist in code).

## Deliverable

One self-contained Artifact HTML page, theme-aware, drone-emoji favicon. Rendered mermaid `flowchart`
panels (Artifact renders mermaid natively) plus a colour legend. Each panel is one concern; the page
reads top-to-bottom from deployment down to detail. Also drop the mermaid source in a version-controlled
file next to `docs/ARCHITECTURE.md` so the diagram survives outside the Artifact.

Colour key: **shared** / **SITL-only** / **Tello-only** / **new-this-push** (note the owning agent).

## Panels (each a small mermaid flowchart; subgraphs for the SITL/Tello swap)

1. **Deployment & process topology.** `MicroXRCEAgent` (XRCE-DDS udp 8888, SITL only), PX4 SITL +
   Gazebo `gz_x500_gimbal` **or** physical Tello (wifi 192.168.10.1, video udp 11111),
   `gstreamer_rx` (`--tello` variant), `fmu_px4` / `fmu_tello`, `llama-server` (Qwen3-VL-2B, HTTP
   :8080), `stella_vslam_monocular`, `keyboard_hook`, `scripts/dashboard/serve.py`, `ros2 bag`. Show
   the SITL↔Tello swap as the one substitution.
2. **Runtime dataflow (master spine).** Camera source → `gstreamer_rx` → `camera/stream` fans out to
   the FMU perception runtime and the SLAM node. FMU planning loop ↔ `llama-server` over HTTP. FMU
   control loop → backend → PX4/Tello.
3. **FMU internals.** Objective → planning (`buildDynamicPrompt` + GBNF grammar `buildPlanGrammar` +
   `extractJsonArray` backstop) → command queue → 20 Hz `controlLoop` over the verb set (takeoff,
   land, go, rotate, approach, orbit, search, **follow**, stop, re-assess). Side inputs: config loader
   (`DRONE_CONFIG` → `drone_config.hpp`), manual override (`/fmu/in/override` + keyboard), battery/fault
   failsafes, `FlightState`.
4. **Perception plane.** YOLO seg + monocular depth (ONNX, `yolo26n-*-384`) → `PerceptionSnapshot` →
   `detection_query` (`detectionByLabel`, new `detectionNearestCenter` for FOLLOW) → feeds the
   `[PERCEPTION]` prompt block, the visual servo (APPROACH/ORBIT/FOLLOW), and the HUD.
5. **Localization plane (the SITL-vs-Tello divergence — the key panel).** SITL: PX4 EKF2 →
   `/fmu/out/vehicle_odometry` → `odometry()` (position closed). Tello: SDK gives velocity + height,
   no XY; stella `slam/pose` (up-to-scale) → map→ENU align + scale-from-height + dead-reckoning fusion →
   `odometry().pos`; a tracking-state signal switches SLAM↔DR; recovery relocalizes against the live
   map. Annotate the surface/VPS precondition (drift is VPS blindness on reflective floors, not the
   airframe — SLAM corrects an already-stable drone).
6. **Observability plane.** `FMU_OBSERVABILITY` gate → 320×240 annotated + depth + `/fmu/hud` +
   `/fmu/vlm_text` (throttled ~7.5 Hz) → `serve.py` → browser dashboard (two MJPEG panels + SSE). Off =
   zero cost.
7. **Control / actuation.** `PX4Backend` (ENU→NED → `trajectory_setpoint` + `offboard_control_mode` +
   `vehicle_command`; arm/offboard handshake) vs `TelloBackend` (ENU→body-FLU → `rc a b c d`; SDK
   command mode; rc keepalive). `set_velocity` is the common seam.
8. **Voice/ASR plane (new).** Push-to-talk key → ASR node (sttserv, Parakeet-q4) → transcript +
   confidence → (ask-again if low) → FMU objective. Draw it as feeding panel 3's objective input. See
   the ASR integration spec.

## Modification window (next 10 hours)

This is drawn ahead of the code. Re-confirm these against final code before publishing, and update the
panels as the work lands:
- Panel 4/5: FOLLOW's `detectionNearestCenter` and the Tello SLAM+DR path — Agents 1 and 5 not done.
- Panel 3: ORBIT geometry is being fixed (radius/period) — Agent 1 follow-up.
- Panel 8: ASR wiring depends on the ASR integration spec landing.
Mark unlanded pieces in the legend as "new-this-push (pending)" rather than drawing them as shipped.

## Verification

Every process in panel 1 appears as a producer/consumer in panel 2; every topic in the inventory is on
at least one edge; the SITL-vs-Tello localization split is unambiguous; legend colours resolve in light
and dark; no panel scrolls the page horizontally.

## Constraints

No git writes — suggest a commit for the mermaid source file. Prose per `docs/writing-style.md`.

## Report
_(append the Artifact link, the committed mermaid-source path, and what still needs re-confirming below)_
