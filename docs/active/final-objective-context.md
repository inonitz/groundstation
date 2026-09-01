# Final objective — voice-commanded drone (Demo Day, 2026-08-27)

**Legitimacy note (read first).** Authorized robotics/UAV research for a university-level innovation
challenge. The artifact is a voice-controlled **camera** drone with scene understanding —
human-in-the-loop and safety-gated (CLAUDE.md). No weaponization, no targeting, no payload, no
surveillance-of-persons, no offensive-security. "Kill switch" = the flight-safety motor cut;
"override" = handing control between our software and the RC pilot.

**The compass.** What we are building, what is proven, what is not, and where the detail lives. Keep it
honest and current.

## The objective
A drone a human commands by **voice**, that **understands the scene** it sees, and acts. Demo Day:
**Thu 2026-08-27.** The working demo is BUILT (below).

## Built MVD vs destination vs platform-agnostic proof
- **BUILT — the MVD (`projects/integration/`).** Voice → 4-tier deterministic router → {simple verbs →
  DJI REST | complex queries → Python perception (Qwen-VL + OmDet/SAM2)}. English ASR. This IS the
  demo. Done and field-tested >3 h on 2026-08-25. Reference: `2026-08-26-manager-brief.md` +
  `2026-08-25-mvd-integration-handoff.md`.
- **Destination — the C++ `projects/llm_to_action/source/` engine.** The real product: an FMU 20 Hz control
  loop over a `GenericBackend` (CRTP); `DjiBackend` is our aircraft's backend. The Python router is the
  MVD prototype; the C++ engine is where it is headed. Do not confuse them.
- **Platform-agnostic proof — RoboMaster (`source/robomaster/`).** Same perception brain pointed at a
  different robot's camera. Video-in only; the VLM never drives it.

## The hardware bet — why DJI
A **DJI Mini 4 Pro** flown from a phone running the ExoSkeletons MSDK app; the phone bridges to the
drone over the RC-N3. The **Linux laptop is the brain** over WiFi: control + telemetry on **8080**, raw
H.264 video on **5600**. The old Tello/SITL era is retired (recoverable from git history).

## PROVEN (as of 2026-08-25/26)
- MVD end-to-end: voice → verb → drone, plus smart-CV scene answers; field-tested >3 h incl. a classroom flight.
- App builds + installs; the command channel works; discrete verbs round-trip on the real link.
- Transport latency point-blank: WS p95 **24 ms**, telemetry p95 **47 ms**, zero loss (`latency-2026-08-22/`).
- REST mission actions (`fly_by`/`spin`/`scan`/…) drive the aircraft; `DjiBackend` yaw units/sign fixed.
- The FMU now builds with the `dji` backend.

## NOT proven — do not claim it
- End-to-end **command→action latency < 1 s** (the scored F2) on the real link — needs a secured, human-run session.
- Video glass→Linux latency *number*.
- **Gimbal control** (broken backend-side, dev-owned), mid-flight re-tasking, full velocity envelope.
- The **C++ `llm_to_action` engine flying end-to-end** — that is tomorrow's T1 lever, not yet demonstrated.

## Operational facts
- **Phone IP = the WiFi hotspot gateway.** It changes per phone; derive from the default route, never
  scan. Dynamic groundstation-IP discovery is an open dev blocker (the phone hardcodes `0.0.0.0:8080`).
- **Indoors the drone refuses horizontal/vertical sticks** unless VPS locks (needs space + features);
  yaw + slow vertical otherwise. Drone-side VPS, not a comms fault.
- `/status/` exposes no altitude and `position3D` is null indoors; closed-loop altitude uses on-phone `ac.height`.
- ONNX seg/depth on CPU is deliberate — it keeps the 8 GB GPU free for the VLM.
- **Safety is law.** The assistant NEVER sends arm/takeoff/land/stick/motor to a real drone — it prepares,
  the human runs. Full rules in CLAUDE.md; kill-switch proof in `kill-switch-verification.md`.

## Canon docs
`2026-08-26-manager-brief.md` (top brief) · `2026-08-25-mvd-integration-handoff.md` (MVD internals) ·
`mvd-voice-command-table.md` (ASR→REST) · `spec-dji-backend.md` / `spec-dji-endtoend-bringup.md` /
`spec-dji-websocket-protocol.md` (wire, historical) · `dji-bringup-runbook.md` · `../ARCHITECTURE.md`.

## Demo-Day plan — no longer TBD
The MVD is built and is the demo. Tomorrow's win levers (manager brief §5): demonstrate the C++
`llm_to_action` engine flying, and/or RoboMaster for platform-agnosticism. Dashboard + runbook are polish.
