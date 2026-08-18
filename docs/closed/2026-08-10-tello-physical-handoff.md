# Tello physical hardware handoff (dry, position-independent tests)

**Why this doc exists:** written at 02:xx on 2026-08-10, session ending without laptop/hardware
access. Everything below is prepared and buildable from this checkout; none of it has been run on
real hardware yet. This is the handoff for whoever is at the laptop next to the drone.

**Scope, deliberately narrow:** takeoff, rotate/scan, VLM describing what it sees, land. **Nothing
position-dependent** (GO/APPROACH/ORBIT/SEARCH) — the real Tello has no X/Y position source at all
right now (no SLAM wired into control, see `docs/ARCHITECTURE.md` §8), so those commands have
nothing valid to read and are out of scope until that lands. This matches B4's own original scope
(`docs/active/tello-B4-agent-prompt.md`).

## Before you fly: build state

The Tello binary was rebuilt at the end of tonight's session and includes every fix from today:
- The plan-parsing rewrite (`plan_parse.hpp`) — a VLM response with a stray bracket in its own
  prose no longer gets silently discarded.
- Schema-constrained VLM output (`llamaclient.hpp`) — the model is now forced by the inference
  server itself to emit only a JSON array, nothing else. Verified against a standalone request;
  **not yet flight-verified** (SITL run was in flight when this doc was written).
- SEARCH return-to-start (irrelevant to this dry scope, but shares code with the rest of the FMU).
- DECISION RULE 9 (system prompt): the model is now told explicitly that a non-`_ok` status in its
  own history means a command failed, and to adjust rather than continue blindly.
- Raw VLM response text is now logged (previously only a character count) — if anything looks
  wrong on hardware, the FMU pane's log now has the actual model text to read, not just a count.

None of the above changed anything in `tello_backend.cpp`/`tello_backend_base.hpp` themselves —
the Tello-specific control code is untouched tonight.

**Rebuild before flying** (safe even if already done — confirms the binary matches this checkout):
```bash
cd /root/groundstation
./build.sh release shared tello configure
./build.sh release shared tello build
```

## One real, open risk from tonight worth watching for

During SITL testing tonight, the drone once got stuck commanding a yaw rotation that never
actually happened (commanded yawrate 0.8 rad/s, measured yawrate 0.00, for 20+ minutes straight,
at low altitude) — see `docs/NOTES.md` 2026-08-09 "ROTATE hang". **Root cause is unknown; it has
only been seen once.** If a ROTATE command on real hardware seems to hang with no visible
rotation, that's this bug, not a new one — land manually via keyboard immediately (see
`scripts/tello/README.md` "Land and stop") rather than waiting for it to resolve itself.

## Test procedure

Bring-up mechanics (build, WiFi, `run.sh`, three-pane layout, troubleshooting) are already fully
documented in `scripts/tello/README.md` — follow that for getting RX/FMU/keyboard up. This section
is the actual test checklist on top of that bring-up.

**Charge multiple batteries first.** One battery is ~10-13 minutes; bring-up alone eats into that.

1. **[Manual] Bring-up sanity.** `cd scripts/tello && ./run.sh`. Confirm per `README.md`'s "What
   success looks like": RX pane goes quiet (frames flowing), FMU pane shows Tello connect +
   `streamon` ack + steady control/rc lines, telemetry parses without a flood of errors.
   **PASS = all three panes healthy for at least 30s with the drone still on the ground.**

2. **[Manual] Keyboard takeoff/land, no VLM.** With the drone on the ground and RX/FMU healthy,
   use the keyboard pane to take off, hold a few seconds, land. This exercises the real motor/ESC
   path and the 20Hz control loop against real telemetry, with zero VLM involvement — isolates
   "does the airframe/link work at all" from "does the VLM work."
   **PASS = clean takeoff, stable hover, clean land, no telemetry parse-error flood.**

3. **[Manual] VLM-driven takeoff + describe + land, no movement.** Start `llama-server` in a
   fourth pane exactly as `scripts/test/lib/sim_core.sh`'s `CMD_VLM` does (same model/flags as
   SITL: Qwen3-VL-2B-Instruct, Vulkan, `-ngl 99`). Give the FMU an objective like *"Take off,
   describe what you see, then land."* — deliberately no movement/search/approach in the
   objective, since those need position.
   **PASS = takeoff → VLM produces a plan (raw text now visible in the FMU log — check it
   actually describes the real camera view, not something generic/hallucinated) → land. Watch
   for any `plan JSON parse failed` warnings; there should be none now (schema-constrained
   output), but the raw-response logging means you can tell immediately if the model went off
   the rails rather than guessing.**

4. **[Manual] Rotate-and-scan.** Objective like *"Take off, rotate 90 degrees, describe what you
   now see, then land."* Exercises ROTATE specifically (watch for the hang risk above) and
   confirms the camera feed the VLM reasons over actually changes with real orientation, not a
   stale frame.
   **PASS = visible physical rotation matching the commanded angle (roughly — Tello's own yaw
   sensing is what it is), description changes to match the new view, clean land.**

5. **[Manual] Battery-swap continuity.** After any of the above, land, swap battery, rerun
   `./run.sh`. Confirms bring-up is repeatable within one session, not a one-shot fluke.

## Explicitly out of scope tonight

- GO / APPROACH / ORBIT / SEARCH — no position source on real hardware yet.
- Anything SLAM-dependent — stella_vslam is not wired into control at all (§8 ARCHITECTURE.md),
  and even once it is, `dependencies/stella_config_tello.yaml` is still a **community/provisional**
  camera calibration, not measured from this specific airframe (see the `feature-calibrate-slam`
  branch, not yet merged — real calibration tooling exists there but a physical checkerboard
  capture session against the actual drone still needs to be run).

## If something's wrong and you don't know why

The raw VLM response is now in the FMU log (`[FMU_NODE_DEBUG] VLM raw response: ...`) — read what
the model actually said before assuming the code is broken. Most of tonight's bugs were the model
being fed the wrong thing or being unable to be understood downstream, not the flight-control math
itself being wrong.
