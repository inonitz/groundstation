# Final objective — voice-commanded DJI drone (MOD Demo Day, 2026-08-28)

**Read this first.** This is the compass for any agent working toward Demo Day. It states what we are
building, what is proven, what is not, and where the detail lives. Keep it honest and current.

## The objective
A drone a human commands by **voice**, that **understands the scene** it sees, and acts — for the
Israeli MOD challenge. Demo Day is **2026-08-28**.

## The system — destination vs prototype
- **Destination: the C++ `source/llm_to_action/` system.** This is the real product. Voice → intent
  → deterministic verb → drone. The FMU runs a 20 Hz control loop over a `GenericBackend` (CRTP).
  `DjiBackend` is the backend for our aircraft.
- **Prototype: the Python `source/llm_cv_*` perception** (VLM scene understanding, open-vocab
  detection, ASR). It passed its gate. It is a **component to fold into the C++ system**, not the
  destination.

## The hardware bet — why DJI
We fly a **DJI drone** controlled from a **GrapheneOS phone** running the ExoSkeletons MSDK app. The
phone bridges to the drone over the RC-N3. The **Linux workstation is the brain** and reaches the
phone over WiFi: control + telemetry on **8080**, raw H.264/H.265 video on **5600**. The old
Tello/SITL era is retired (docs deleted; recoverable from git history).

## What is PROVEN (as of 2026-08-22)
- App builds from source and installs on the phone (`tools/adk.sh`).
- Workstation ↔ drone command channel works; discrete verbs (`/c/takeoff`, `/c/land`, `/c/stop`)
  round-trip on the real link.
- Transport latency at point-blank range: WS p95 **24 ms**, telemetry p95 **47 ms**, zero loss
  (`docs/active/latency-2026-08-22/`).
- `DjiBackend` yaw units/sign fixed (rad/s → deg/s, ENU CCW+ → DJI CW+).

## What is NOT proven — do not claim it
- **Continuous velocity control** via `/c/ws/sticks` at ~18 Hz, end-to-end through our software.
- **command→action latency** (the scored < 1 s) on the real link — needs an outdoor, secured-drone,
  human-run session (Task 4).
- **Video glass→Linux latency** (Task 5) — the decode path is testable now; the latency *number*
  needs a filmed millisecond clock.
- Real-drone velocity envelope, gimbal control, mid-flight re-tasking.

## Operational facts you need
- **Phone IP is fixed at `10.222.215.92:8080`** — it is the WiFi hotspot gateway. Derive, never scan:
  `ip route show dev wlp2s0 | awk '/^default/{print $3}'`.
- **Indoors the drone refuses horizontal/vertical sticks** — VPS cannot lock a uniform space. Yaw and
  slow vertical only. Outdoors with features: nominal. This is drone-side VPS, not a comms fault.
- **`/status/` exposes no altitude and position3D is null indoors** — no height feedback over HTTP;
  closed-loop altitude must use on-phone `ac.height` (`AircraftController.ascendTo`).
- **Safety is law.** The assistant NEVER sends arm/takeoff/land/stick/motor commands to a real drone.
  It prepares them; the human runs them. Full rules in `CLAUDE.md`; kill-switch proof in
  `docs/active/kill-switch-verification.md`.

## Canon docs for detail
- `mission-brief-2026-08-15.md` — the MOD challenge + platform context.
- `spec-dji-backend.md`, `spec-dji-endtoend-bringup.md`, `spec-dji-websocket-protocol.md` (FROZEN wire).
- `dji-bringup-runbook.md` — bring-up steps + latency table.
- `../ARCHITECTURE.md` — the FMU / GenericBackend / control-loop architecture.

## Implementation plan for Demo Day — TBD (NOTE1)
We have NOT yet drafted the implementation-specific plan for 2026-08-28: the exact
voice→intent→verb→`DjiBackend` "simple mode" build, the perception fold-in, and the demo script.
That is the next design task. **Placeholder — to be filled when we design it.**
