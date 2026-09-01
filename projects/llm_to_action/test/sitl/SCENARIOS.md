# SITL scenario notes -- concatenated from the per-scenario READMEs at consolidation (2026-09-01).

## approach-impact

# approach-impact test

Verifies the APPROACH motion-gate (spec 2026-08-07-spec-1 §C, ROADMAP 6.4). A real collision reads
a plausible range off the impact frame and, before this spec, declared `approach_ok` while yaw-rate
spiked to ~6.9 and vertical velocity to ~-1.75 with altitude collapsing 0.99->0.02 m in ~1 s. The
gate now requires nominal motion before trusting "reached"; a collision instead raises
`INTERRUPT (reason=approach_impact)`.

- **Scenario:** `--scenario-approach-impact`
- **World:** `empty`   **Spawn:** `0,7,3`
- **Filter:** Auto PASS/FAIL.

## How it's triggered
`--scenario-approach-impact` runs the canned synthetic APPROACH rig (deterministic, no real
perception) and forces the motion-gate off-nominal. The rig drives to the standoff, "reached" is
treated as an impact, and the FMU raises `approach_impact` instead of `approach_ok`. The queued
land then runs, so the flight ends with `LANDING->STANDBY`. Empty world so only the rig detection
is present.

## PASS condition
`APPROACH activated` appears, at least one `INTERRUPT (reason=approach_impact)` (or
`emergency_boundary`), and **no** `task complete status=approach_ok`.

## Run
```
cd scripts/test/approach-impact
./run.sh
./filter.sh         # -> PASS/FAIL
```

## Observed (fill in per run)
- **date:**
- **what I saw:**
- **filter digest:**


## What this actually tests (no real car -- by design)
This uses the SYNTHETIC approach rig (a scripted fake detection), NOT a real car. It forces
the approach to reach the standoff with OFF-NOMINAL motion (as if it clipped something), and
verifies the system raises an **impact interrupt** instead of falsely reporting `approach_ok`.
PASS = `impact interrupt` + no `approach_ok`. There is intentionally nothing in the world to
see -- the detection is injected.

## approach-real

# approach-real test

Same APPROACH servo, but REAL perception (ONNX seg+depth) vs the car in the world.

- **Scenario flag:** `--scenario-approach-real`
- **World:** `default_car`   **Spawn:** `0,7,3`
- **Filter:** milestone digest (APPROACH sees label=car ...) — no PASS/FAIL.

## Run
```
cd scripts/test/approach-real
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- Real ONNX models detect the 'car' (COCO label) — `APPROACH sees ... first label=car`.
- Servo closes to the standoff distance (now 4.0 m, raised from 3.0): `APPROACH reached target=car range=..`.
- Skips only the VLM planner, not vision. Ends with `LANDING->STANDBY`.
- Motion-gate (spec 2026-08-07-spec-1 6.4): if the servo collides on a spiky frame, "reached" is
  rejected -- instead of `approach_ok` you see `APPROACH reached ... motion off-nominal ... impact
  interrupt` and `INTERRUPT (reason=approach_impact)`.
- Looming backstop (2026-08-08): SITL depth over-reads range ~2 m close up, so a smooth over-close
  can drive the drone into the car with no motion spike. The boundary now also trips on how much of
  the frame the car fills: `BOUNDARY looming fill=.. > 0.40 ... -> interrupt` +
  `INTERRUPT (reason=emergency_boundary)`. Seeing this instead of a crash is the CORRECT outcome --
  it stops the drone ~1 m short and re-plans.
- Verbose diagnostics: the log now streams `APPROACH ... rawRange=.. medRange=.. budget=.. trav=..
  rem=.. fill=..` and `BOUNDARY nearest=.. trig=.. loomFill=..` each tick. Use these to see the
  depth over-read directly -- rawRange/medRange stay high while the drone is physically at the car.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**

## approach

# approach test

Closed-loop APPROACH toward a canned (synthetic, no-YOLO) detection, then land.

- **Scenario flag:** `--scenario-approach`
- **World:** `default_car`   **Spawn:** `0,7,3`
- **Filter:** milestone digest (APPROACH activated/sees/reached/lost) — no PASS/FAIL.

## Run
```
cd scripts/test/approach
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- Servo drives toward a synthetic detection 3m north / 1m up of spawn.
- `APPROACH reached target ... range~standoff` — reaches the standoff distance.
- If the rig kills the detection mid-approach, expect a CLEAN `APPROACH lost ... FAIL`, not a crash.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**

## battery-landnow

# battery-landnow test

Battery **land-in-place** behaviour (spec-3, ROADMAP 6.2) — the "all of a sudden extremely low,
land NOW" fault. Distinct from RTH: the drone lands where it is, it does NOT fly home.

- **Scenario:** `--scenario-battery-landnow` — fly ~8m straight out, then force a sudden **8%**
  ~15s after reaching FLIGHT (test-only battery override; PX4 drain pinned high).
- Why forced, not drained: with gradual drain the 20% law latches RTH first, so 10% can never
  fire. Land-in-place is by nature a *discrete* crash to critical — so we inject it directly.
- **World:** `empty`
- Why not depict a collision either: run in the **empty** world (no car). land-in-place has **no obstacle awareness** (smart flat-site selection is the deferred subsystem), so in `default_car` it would drop onto the car at world 6,7 -- right on the outbound path.   **Spawn:** `0,7,3`

## Run
```
cd scripts/test/battery-landnow
./run.sh            # takes off, flies out ~8m; ~15s into FLIGHT the battery craters to 8%
./filter.sh         # after it lands: -> captured_battery_landnow_log.txt + digest + PASS/FAIL
```

## Expected (watch the drone)
- Climbs, flies straight out to several metres.
- `TEST battery fault injected -> forcing 8%`, then `FAILSAFE battery 8% -> LAND in place`.
- **Drone descends straight down where it is** (does NOT fly back), then `LANDING->STANDBY
  (force_disarm)` far from spawn.

## PASS requires (all)
- reached FLIGHT; `maxDist > 3m` (flew out); `<=10% LAND-in-place` fired (NOT RTH);
  `landDist > 2m` (landed far from home, i.e. in place); `LANDING->STANDBY` (landed AND disarmed).

## Observed (fill in per run, then hand this whole file back)
- **date:**   **what I saw:**   **filter digest:**   **my comment:**

## battery-rth

# battery-rth test

Battery **return-to-origin** behaviour (spec-3, ROADMAP 6.2) — the REAL RTH the plain `battery/`
test couldn't show (there the drone sat at origin, so "fly home" was a no-op).

- **Scenario:** `--scenario-battery-rth` — fly ~8m straight out, then force **18%** ~15s after
  reaching FLIGHT (test-only battery override; PX4 drain pinned high so only the forced value fires).
- **World:** `empty`   **Spawn:** `0,7,3`

## Run
```
cd scripts/test/battery-rth
./run.sh            # takes off, flies out ~8m; ~15s into FLIGHT the battery is forced to 18%
./filter.sh         # after it lands: -> captured_battery_rth_log.txt + digest + PASS/FAIL
```

## Expected (watch the drone)
- Climbs, flies straight out to several metres.
- `TEST battery fault injected -> forcing 18%`, then `FAILSAFE battery 18% -> RETURN to origin`.
- **Drone flies all the way back toward spawn**, then `LANDING->STANDBY (force_disarm)` at origin.

## PASS requires (all)
- reached FLIGHT; `maxDist > 3m` (genuinely flew out); `<=20% RETURN` fired (not land-in-place);
  `landDist < 1.5m` (RTH actually brought it home); `LANDING->STANDBY` (landed AND disarmed).

## Observed (fill in per run, then hand this whole file back)
- **date:**   **what I saw:**   **filter digest:**   **my comment:**

## cross

# cross test

Cross pattern: fwd/left/back/right 1m, returning to start after each leg (FLU sanity).

- **Scenario flag:** `--scenario-cross`
- **World:** `default_car`   **Spawn:** `0,7,3`
- **Filter:** milestone digest (per-leg GO activated/complete) — no PASS/FAIL.

## Run
```
cd scripts/test/cross
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- Four legs: forward, left, back, right — each re-anchored to actual position and returned to start.
- Two `GO` events per leg (out + back); path is a plus/cross, not drifting.
- Ends with `LANDING->STANDBY`.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**

## dashboard

# dashboard — headless SITL + live dashboard (self-assessing)

Brings up the `moving_person` FOLLOW demo with **Gazebo headless** (no GUI window)
and `FMU_OBSERVABILITY=1`, starts the dashboard bridge, and runs an assessor that
writes a PASS/FAIL verdict for the whole pipeline. Watch the demo in a browser
instead of a Gazebo window.

```bash
cd projects/llm_to_action/test/sitl-legacy/dashboard
./run.sh                                # demo: holds ~30 min, assesses once
HEADLESS_TIMEOUT_SECONDS=150 ./run.sh   # short self-test
DASH_PORT=9000 ./run.sh                 # pick the dashboard port
```

Open **http://localhost:8088** while it runs.

Outputs land in `./logs_<timestamp>/`:
- `verdict.txt` — PASS/FAIL with evidence (rates, width, HUD, website checks)
- `fmu.log` — FMU stdout: `[FMU_HUD]`, camera rx, perception, VLM, errors
- `dashboard.log` — bridge: subscription rates, requests, stream open/close
- `assess.log`, `sim.log` — assessor + stack bring-up output

The stack (PX4, gz, FMU, VLM) is a child process with its own cleanup trap; the
wrapper only owns the dashboard bridge. Needs PX4 built, gz, the ONNX vision +
Qwen VLM models, and MicroXRCEAgent.

## follow

# FOLLOW (scripted)

Gates the FOLLOW control law (soon `stepFollow`). Scripted (`--scenario-follow`, VLM off) so it is
deterministic: `[takeoff, follow target_index=0 standoff_cm=200]` in the `moving_person` world.

FOLLOW is a **yaw-only visual servo** -- it centres the person and holds standoff (backs off if too
close), never chases forward, and never self-completes.

## Expected / verdict (`./filter.sh`, auto)
- **PASS** = a sustained stream of `FOLLOW(yaw-only)` ticks (>=20), one stable track id, no
  `follow_no_target` release. Prints mean pixel-centering error + min(range-standoff) for insight.
- **FAIL** = never locked (no ticks), lost the target (`follow_no_target`), or the id churned.

## hover

# HOVER persistence

Verifies the extracted `stepHover` control law: a HOVER command is a **persistent** hold that
**never completes**, so anything queued after it never runs.

## Scenario (`--scenario-hover`)
`[takeoff, go +1.5m forward, hover, go -1.5m backward, land]`. Because HOVER never completes, the
backward GO and the land can never dequeue.

## Expected
- Drone takes off, flies ~1.5m forward, then holds station there.
- It does **not** reverse. The backward motion never happens; the drone parks at +1.5m.
- Log shows `HOVER activated` then repeated `HOVER holding station`, and **no** further `GO` lines.

## Verdict (`./filter.sh`, auto)
- **PASS** = forward GO ran, HOVER activated + held, and no GO activity after hover.
- **FAIL** = a GO line appears after `HOVER activated` (the back-go ran -> hover leaked), or HOVER
  never activated / never held.

## Your observations
_(fill in)_

## interrupt-storm

# interrupt-storm test

Verifies interrupt-storm escalation AND recovery (spec 2026-08-07-spec-1 §D, ROADMAP 6.3). When
`kInterruptMaxRetries` interrupts fire within `kInterruptStormWindowMs`, the FMU sets `escalated=1`
and the next VLM prompt carries an `[ESCALATION]` block telling the model to reason about the root
cause and find a creative escape. A later clean task completion resets the detector.

- **Scenario:** `--scenario-storm`
- **VLM:** on (`LAUNCH_VLM=1`) — needed for the escalated prompt AND the recovery re-plan.
- **World:** `rubicon_targets`   **Spawn:** `0,7,3`
- **Filter:** Auto PASS/FAIL on escalation; RECOVERY is a soft, operator-confirmed signal.

## How it's triggered
`--scenario-storm` takes off, then injects a synthetic close-obstacle burst for ~1.5 s. That trips
the boundary many times inside the window (deterministic `escalated=1`), then clears. The prompt
text is not logged, so the FMU logs `ESCALATION block added to reassess prompt` when it adds the
block — that is what the filter greps.

## Why rubicon_targets (not empty)
The point of escalation is that the model actually RECOVERS. In an empty world the VLM has nothing
to see or escape, so it never completes a task and escalation never clears — escalation fires but is
never shown to work. `rubicon_targets` is the Rubicon terrain plus two people and two cars in the
drone's forward view (`dependencies/rubicon_targets.sdf`). After the burst clears, real perception
shows the VLM an actual scene, so the escalated reassess can plan a real escape and complete it.

Models used as targets live in `assets/gz_models/`: `person_standing`, `person_walking`
(downloaded from Gazebo Fuel), `hatchback`, `hatchback_blue`. YOLO reads the people as "person" and
the cars as "car". If any model floats or buries on the sloped terrain, nudge its `z` in
`dependencies/rubicon_targets.sdf`.

## PASS condition
Hard: `>= 3` `INTERRUPT (reason=...)`, at least one `escalated=1`, and at least one
`ESCALATION block added to reassess prompt`. Soft (RECOVERY): a non-`takeoff_ok` `task complete`
AFTER the storm — the VLM escaped the loop. Recovery is operator-confirmed (a 2B VLM may not always
escape); watch whether the drone actually leaves the spot.

## Run
```
cd scripts/test/interrupt-storm
./run.sh            # needs the Qwen3-VL llama-server (LAUNCH_VLM=1 handles it)
./filter.sh         # -> PASS/FAIL + RECOVERY line
```

## Observed (fill in per run)
- **date:**
- **what I saw:** (did the drone leave the spot after the storm?)
- **filter digest:**

## obstacle-stop

# boundary test

Verifies the velocity-scaled emergency boundary (spec 2026-08-07-spec-1 §B, ROADMAP 6.1). Each
FLIGHT tick the FMU computes `trig = kBoundaryBaseM + kBoundaryVelScale * speed` and reads the
nearest detection depth via `nearestDepthM`. If a detection is inside `trig` it stops and raises
`INTERRUPT (reason=emergency_boundary)`. A snapshot older than `kBoundaryMaxSnapshotAgeMs` is
treated as unknown and must NOT trip it.

- **Scenario:** `--scenario-obstacle-stop`
- **World:** `empty`   **Spawn:** `0,7,3`
- **Filter:** Auto PASS/FAIL.

## How it's triggered
`--scenario-obstacle-stop` takes off, then injects a synthetic close obstacle (~0.4 m, below the 0.6 m
base trip distance) for a ~1.5 s burst once airborne, through the same atomic snapshot path real
perception uses. No real object in the world is needed; `empty` world keeps real detections from
competing. After the burst the drone hovers (no VLM) -- watch the trip, then Ctrl-C and filter.

## PASS condition
At least one `INTERRUPT (reason=emergency_boundary)`, preceded by a `BOUNDARY nearest=...` line.

## Run
```
cd scripts/test/boundary
./run.sh
./filter.sh         # -> PASS/FAIL
```

## Observed (fill in per run)
- **date:**
- **what I saw:**
- **filter digest:**

## orbit

# orbit test

ORBIT the car with REAL perception (ONNX seg+depth). Flies a full circle around the car, keeping it in
the camera the whole way (that framing is the survey), then lands. ROADMAP 1.1.6.

How it avoids the wobble the earlier version had: at the start it medians a few depth reads into ONE
fixed car position (the circle center). After that the circle is flown from odometry around that fixed
point, so the flight path never reacts to the jittery depth and cannot oscillate. The camera turns
separately (a gentle image-centering) to keep the real car in view, and if the center estimate was a
bit off, that camera tracking still keeps the car framed.

- **Scenario flag:** `--scenario-orbit` (takeoff -> orbit car, 360 deg, ccw, 30 cm/s -> land)
- **World:** `default_car`   **Spawn:** `0,6,3`
- **Filter:** milestone digest — PASS = `ORBIT center locked ...` then `ORBIT complete ... orbit_ok`.

## Run
```
cd scripts/test/orbit
./run.sh            # brings up the sim; WATCH the drone
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- `ORBIT activated ...`, then it hovers a moment while it fixes the center: `ORBIT center locked
  target=car R=.. centerENU=(..)`.
- Then it flies one smooth circle of radius R around that point, camera staying on the car. Diagnostics
  show `swept` climbing to ~6.28 and `dist` holding near `R`.
- Ends with `ORBIT complete ... orbit_ok`, then `LANDING->STANDBY`.

## Known tuning to check in SITL
- **Direction sign** (`m_orbitDir`): if cw/ccw circles the wrong way, flip the sign in the ORBIT dispatch.
- **Center accuracy**: the center is the medianed startup depth and then stays FIXED. The path is flown
  from odometry only; vision never touches the geometry (a slow "drift correction" was tried and reverted
  -- it fed vision back into the path and dragged the center away). Odometry drift over one short orbit is
  the accepted trade for a circle that cannot wobble.
- **Camera aim** is driven from odometry now (point at the locked center), not from the bbox — that is
  what killed the earlier hard-yaw jitter. `kOrbitAimTrimGain` is a small vision nudge onto the real car
  on top of it; raise it if the car sits off-centre, lower it if the camera twitches.
- `kOrbitRadialGainHz` (how hard it holds the radius) and `kOrbitYawGain` (how fast it settles onto the
  center look-angle) — sweep if the radius drifts or the aim lags.

## Edge cases (SITL-verify manually)
- Target never seen at all -> after the acquire window: `ORBIT never locked ... orbit_lost_failed`.

## Hardware note (DJI Tello)
Uses odometry for the ~20-30 s circle. That is short enough that odometry drift stays small (the concern
with odometry is long flights, not a bounded maneuver). Expect a slightly looser circle than SITL.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**

## override

# override test

Manual operator override (spec-3, ROADMAP 6.2 / ARCH 11) — reversible takeover, NOT a kill.

- **Override toggle:** the `Enter` key (or `/fmu/in/override`, `std_msgs/Bool`, as a fallback)
- **Movement input:** `/keyboard/in/raw` (the keyboard node pane, launched by sim_core.sh)
- **VLM:** on (`LAUNCH_VLM=1`) so a handback re-plans from the current pose
- **World:** `default_car`   **Spawn:** `0,7,3`

## Run
```
cd scripts/test/override
./run.sh            # sim + VLM + keyboard node come up; let it take off & start flying
```

## Manual steps (this test is interactive)
1. Once airborne under VLM control, **engage override**: press `Enter`.
   → FMU logs `MANUAL OVERRIDE engaged`; autonomy pauses (drone hovers).
   No pane needs focus -- the hook reads /dev/input globally, so it needs read access there.
   If the keyboard pane did not log `AsyncKeyHook successfully attached`, fall back to:
   ```
   ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data: true}"
   ```
2. **Fly it manually** — press: `W/S`=fwd/back, `A/D`=left/right, `↑/↓`=up/down,
   `←/→`=yaw, `Space`=hover. The drone should move under your keys, not the VLM.
3. **Hand control back**: press `Enter` again (or publish `{data: false}`).
   → FMU logs `MANUAL OVERRIDE released ... VLM will re-plan`; autonomy resumes and the
   VLM plans fresh from the current pose.
4. (optional) Confirm the **battery failsafe still outranks manual** — see the `battery`
   test; a low-battery RTH/land fires even while overridden.

## Then
```
./filter.sh         # -> captured_override_log.txt (this folder) + digest + PASS/FAIL
```

## Expected
- `MANUAL OVERRIDE engaged` on true, `MANUAL OVERRIDE released` + a re-plan on false.
- Keys visibly move the drone while engaged; the VLM does not command it until handback.
- `Enter` alone engages and disengages; no topic publish should be needed.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**

## queue-overflow-airborne

# flood-airborne test

In-flight command-storm / backpressure (spec-3, ROADMAP 1.4). Unlike `../flood` (which floods
at startup and never flies), this one flies first and gets flooded **in the air**.

- **Scenario:** `--scenario-queue-overflow-airborne` — injects the canned cross plan at startup, then arms
  a one-shot flood.
- **Trigger:** ~5s after the drone first reaches `FLIGHT`, the FMU injects a 100-action flood
  from a **producer-role `std::async`** (the same path the VLM plans on), so the SPSC queue
  contract holds — the control thread only *launches* it, it never enqueues.
- **World:** `default_car`   **Spawn:** `0,7,3`   (no VLM, no battery drain)

## Run
```
cd scripts/test/flood-airborne
./run.sh            # takes off, flies the cross; ~5s into FLIGHT the flood hits mid-air
./filter.sh         # -> captured_flood_airborne_log.txt (this folder) + digest + PASS/FAIL
```

## Expected behaviour (watch the drone)
- Takes off, starts the cross legs.
- `AIRBORNE FLOOD armed` at startup; `FLOOD test: injecting 100 ...` **after** `TAKEOFF->FLIGHT`.
- A burst of `BACKPRESSURE queue full -> dropped` (queue is already partly full with the cross
  legs, so more than the startup flood is dropped).
- **The drone keeps flying its current leg unbothered** — the storm queues *behind* the live
  plan (FIFO), so it cannot hijack the maneuver. The cross finishes and the drone lands
  (`LANDING->STANDBY`); the leftover `stop`s then drain as no-ops.

## What the filter asserts
- drone reached **FLIGHT** and the flood fired **while airborne** (`flood line after FLIGHT line`);
- **drops > 0** (backpressure engaged) and **maxQsize ≤ usable cap (63)** (bounded);
- (soft) `LANDING->STANDBY` — the flight completed safely; re-run after touchdown if not yet seen.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**

## queue-overflow

# flood test

Task-queue backpressure (spec-3, ROADMAP 1.4) — the SPSC queue must stay **bounded** under a
command storm and never grow without limit.

- **Scenario flag:** `--scenario-queue-overflow` (injects ONE plan of 100 `stop` actions at FMU start)
- **Queue:** `moodycamel::ReaderWriterQueue`, cap `kMaxPlanActions = 3*20 = 60`
- **The drone does NOT fly.** By design: the flood is 100 `stop`s injected before takeoff, purely
  to hammer the queue. "Never lifts off" is the expected, correct behaviour — this test is about
  queue mechanics, not flight.

## Run
```
cd scripts/test/flood
./run.sh            # sim comes up; the flood fires at FMU start (no need to wait for flight)
./filter.sh         # -> captured_flood_log.txt (this folder) + digest + PASS/FAIL
```

## Expected
- `FLOOD test: injecting 100 actions vs queue cap 60`.
- A burst of `BACKPRESSURE queue full (cap=60) -> dropped task` warnings (~37 of them).
- `qsize` peaks at **63, not 60** — and that is correct. moodycamel rounds the capacity up to
  `(next power of two of cap+1) - 1 = 63` usable slots, so ~63 enqueue and the remaining ~37 are
  rejected. The exact split (63/37 vs 60/40) is a lock-free-queue implementation detail; the test
  asserts the real invariant instead:
  - **drops > 0** — backpressure actually engaged (a regression to unbounded `enqueue` gives 0).
  - **enqueued ≤ usable cap** and **maxQsize ≤ usable cap** — the queue stayed bounded, never grew
    to hold all 100.
  - **enqueued + drops == injected** — nothing was silently lost.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**

## rotate

# rotate-land test

ROTATE granularity regression (spec-4 Part B).

- **Scenario flag:** `--scenario-rotate`
- **World:** `default_car`   **Spawn:** `0,7,3`

## Run
```
cd scripts/test/rotate-land
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest + PASS/FAIL
```

## Expected behavior (watch for this)
- First turn ~90 deg CLOCKWISE.
- Second turn ~200 deg COUNTER-clockwise the LONG way (not 160 deg shortest-path).
- Each turn logs `ROTATE complete`; net swept angle matches magnitude + direction.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**

## search

# SEARCH (scripted)

Gates the SEARCH control law (soon `stepSearch`), replacing the dead `search_follow/` + the contrived three-people world. Scripted (`--scenario-search`, VLM off): `[takeoff, search car]` in the
`rubicon_targets` world (the real rubicon map, with 2 people + 2 cars), spawned **facing away** so the drone must scan to find someone.

SEARCH advance-and-scans; on a confident detection the node logs `SEARCH DETECTED` and hands the
track straight to APPROACH.

## Verdict (`./filter.sh`, auto)
- **PASS** = `SEARCH activated` then `SEARCH DETECTED target=car`.
- **FAIL** = activated but never detected (scanned / timed out without a find).

## vlm

# vlm test

Full VLM-driven run (Qwen3-VL): the planner issues the verbs, no scenario.

- **Scenario flag:** `(none — VLM-driven)`
- **World:** `default_car`   **Spawn:** `0,7,3`
- **Filter:** milestone digest (VLM wake/plan, GO, APPROACH) — no PASS/FAIL.

## Run
```
cd scripts/test/vlm
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- Needs the model at /root/models/vlm and a Vulkan device (extra llama-server pane).
- `VLM wake` -> `VLM plan received` -> the FMU executes the planned GO/APPROACH verbs.
- Behavior is prompt-dependent; watch whether the plan is sane and it lands.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**

