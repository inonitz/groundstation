# POC Task List — consolidated 2026-08-07

Single actionable list, sorted with the user this session. `docs/ROADMAP.md` stays the master
objective tree; this is the near-term work queue drawn from it. Visual companion:
`2026-08-08-status-map.html` (updated) / `2026-08-07-task-map.html` (this morning).

**SITL test matrix (15 tests, all green 2026-08-08):** see `docs/ROADMAP.md` → `## SITL test matrix`.

**Legend**
- `[AUTO]` — decided + bounded; Claude implements and build-checks solo (SITL/flight verify is human).
- `[REVIEW]` — needs human design/decision before any code (brainstorm → spec → plan → implement).
- `[HW]` — needs the real drone or a SITL run (human-in-the-loop); cannot be done off-desk.
- `[DONE]`.

---

## Done this session (2026-08-07)
- **Battery through GenericBackend** (6.2 dependency) — Tello returns real telemetry `bat`; PX4
  now subscribes `/fmu/out/battery_status_v1` (real, wired by Spec 3 — was a `-1` stub); FMU reads it per-loop instead of the stub. `[DONE]`
- **build.sh / build.ps1** reconciled to clean/configure/build only; `.ps1` rewritten to mirror
  `.sh`; run/sim actions dropped (belong in `scripts/`). (9.6) `[DONE]`
- **Dead CMake option** `GROUNDSTATION_BUILD_SYSTEM_BACKEND_TYPE` removed. (9.5) `[DONE]`
- **Branch push** — `feature-llm-driver` synced to origin, 0 ahead/behind. (9.1) `[DONE]`
- **LAND flare** (9.11) — descent tapers from `kLandDescendVelEnu` to `kFlareTouchdownVelEnu`
  below `kFlareStartAltEnu`. **SITL-verified 2026-08-08** (Spec 4): `vLand` tapers −0.500 → −0.139 to STANDBY; regression `scripts/test/land-flare/`. `[DONE]`
- **ROTATE end-to-end** (1.1.2) — was scaffolding-only + silently dropped. Added: rotate parse
  branch (`direction` + `angle_deg`), `CommandID::ROTATE` dispatch + accumulated-angle yaw law (swept-angle integration in the commanded direction),
  granular + correct for ≥180°/360° (not shortest-path), completing within `kRotateCompletionDeg`.
  **SITL-verified 2026-08-08** (Spec 4: 90° cw swept −86°, 200° ccw swept +195° the long way;
  `scripts/test/rotate-land/`). `[DONE]`


## Done this session (2026-08-08) — Spec 3 (failsafe supervisor + override + backpressure)
Implemented + **SITL-verified end-to-end** (6-test suite, all PASS); 8 defects found and fixed HITL.
Full report at the bottom of `docs/closed/2026-08-07-spec-3-failsafe-supervisor-backpressure.md`.
- **6.2 Battery / failsafe supervisor** — real PX4 battery bridge; `≤20% → RTH then land`,
  `≤10% → land-in-place`, both latched; `battery_pct == -1` = UNKNOWN (skipped). `[DONE]`
- **6.2 User override (ARCH 11)** — reversible manual takeover: Bool `/fmu/in/override` + keyboard
  `/keyboard/in/raw`; handback re-plans; failsafe outranks manual. `[DONE]`
- **1.4 SPSC backpressure** — bounded `try_enqueue` + reject-newest, every drop logged; proven under
  a startup storm and an in-air command storm (queue bounded, maneuver not hijacked). `[DONE]`
- **Test suite** `scripts/test/{battery,battery-rth,battery-landnow,flood,flood-airborne,override}/`
  + new flat world `dependencies/empty.sdf`. `[DONE]`
- **Deferred (documented):** smart energy/terrain RTH → `docs/scheduled/2026-08-07-battery-rth-energy-terrain-subsystem.md`. `[DEFER]`

## Done this session (2026-08-08) — Spec 4 (ROTATE granularity + LAND/ROTATE verification tests)
Implemented + **SITL-verified**. Report at the bottom of `docs/closed/2026-08-07-spec-4-verification-rotate-granularity.md`.
- **1.1.2 ROTATE** — accumulated-angle law confirmed granular + correct for ≥180°/360° (Part A by
  the overseer); 90° cw swept −86°, 200° ccw swept +195° the long way. `[DONE]`
- **9.11 LAND flare** — `vLand` taper confirmed from the log stream (not a constant −0.5). `[DONE]`
- **Log-based SITL harness** — canned `--canned-rotate` / `--canned-land-flare` plans +
  `scripts/test/{rotate-land,land-flare}/filter.sh` assert swept-angle direction/magnitude and the
  flare taper. `[DONE]`
- **Terrain-land AGL finding** — landing keys on `od.pos.z` (height above takeoff origin, not AGL);
  over uneven terrain the flare mis-triggers. `--canned-terrain-land` + the Rubicon world expose it
  (ROADMAP 9.12). Rangefinder / terrain-relative altitude is a follow-up. `[DONE test, fix open]`

## Done this session (2026-08-08) — APPROACH visual-servo hardening + perception fixes
Ad-hoc hardening pass (not a numbered spec); driven by live `vlm` / `approach-real` SITL runs.
Full technical detail at the bottom of `docs/NOTES.md`; ROADMAP status in 5.1.5 / 5.1.6 / 6.4.
- **Vision model paths fixed** (4.2) — `kVisionSegModelPath` / `kVisionDepthModelPath` pointed at a
  doubled `/vision/vision/` dir, so both engines silently failed to load and every real APPROACH
  FAILed ~50 ms in. Corrected; unblocked all real-perception runs. `[DONE]`
- **Fail-loud on model load** — `PerceptionRuntime::ready()` checked at FMU startup; a failed load
  now `RCLCPP_FATAL` + `std::abort()` (no exception, per the no-exceptions rule) instead of flying
  blind on zero detections. `[DONE]`
- **APPROACH servo: brake on odometry, not depth** (5.1.5) — depth range is too noisy near the
  target (same parked car read 1.6–6.5 m tick to tick), so the old `(range-standoff)` speed law
  crept forward on every noisy-high read until a fluke low read tripped `reached` — into the car.
  Servo now latches an early range as a fixed travel budget and dead-reckons the stop from
  odometry, so a noisy read can't re-accelerate into the target. Depth kept as a backstop;
  lost-target handling is travel-aware (complete / HOLD / coast). `kApproachStandoffM` 2.0 → 3.0 m
  for margin against protruding target parts. **SITL-verified** (`vlm` stopped clean, no collision). `[DONE]`
- **Acquisition grace** — APPROACH hovers and waits for the first lock instead of instant-FAIL when
  the target is not framed on the activation tick (intermittent detection). `[DONE]`
- **Per-feature SITL test harness** — `scripts/test/<feature>/` (forward, cross, speed, approach,
  approach-real, rotate-land, land-flare, terrain-land, vlm): each `run.sh` sources the shared
  `scripts/test/lib/sim_core.sh` launch engine; each `filter.sh` is self-contained (captures panes +
  asserts). Replaced the monolithic `simenv_llm.sh`. Battery pin (`SIM_BAT_MIN_PCT`) in the core lib
  stops PX4's ~16% SITL pack from tripping the 20% RTH on non-battery runs. `[DONE]`
- **House rules codified** — `docs/code-guidelines.md`: no exceptions (status/error codes only,
  unless wrapping a third-party throw) + no virtual calls (static dispatch). `docs/writing-style.md`
  added + imported into `CLAUDE.md`. `[DONE]`
- **Shipped clean** — temporary `[PERCEPTION_DEBUG]` logging removed from `perception_runtime.hpp`. `[DONE]`
- **New TODOs logged** — 5.1.6 (stop still trusts the noisy depth backstop; travel budget is only a
  failsafe), 9.12 (terrain-land AGL / origin-relative altitude), 9.13 (GO off-heading drift). `[open]`


## Resolved / parked
- **Legacy offboard node** (9.7-related) — **KEEP** (user decision 2026-08-07). Retain
  `source/llm_to_action/offboard_ctrl/` and `scripts/simenv.sh` for legacy reference / code
  recycling. Not removed. `[parked]`

## Specs for parallel sessions (2026-08-07)
The review items below are decomposed into 4 work-packages, each with its own spec file; a spawned
session owns one file and appends its report at the bottom. Merge/review of overlapping edits to
`fmu_node.hpp` is done by the overseeing session, not the workers.
- Spec 1 — `2026-08-07-spec-1-interrupt-reactive-safety.md` (1.5, 6.1, 6.4) — **NOT STARTED**: design
  approved (rev 2), shelved, no source edited; session handoff at the spec's bottom. Ready to spawn.
- Spec 2 — `2026-08-07-spec-2-movement-command-laws.md` (5.2, 1.1.6, 1.1.7, 5.3) — **NOT STARTED**: no
  source edited; spec ready to spawn.
- Spec 3 — `2026-08-07-spec-3-failsafe-supervisor-backpressure.md` (6.2, 1.4) — **[DONE 2026-08-08, SITL-verified]** → moved to `docs/closed/`
- Spec 4 — `2026-08-07-spec-4-verification-rotate-granularity.md` (ROTATE fix, LAND/ROTATE tests) — **[DONE 2026-08-08, SITL-verified]** → moved to `docs/closed/`

---

## Tier 2 — near-term, needs a design pass
- **APPROACH false-positive motion-gate** (6.4) — `approach_ok` is declared on perceived range
  alone; a real SITL collision (yawrate 6.9, vert vel −1.75, alt 0.99→0.02 m in ~1s) was read as
  success off an ill-timed depth frame. Fix: at the "reached" tick, also require odom/IMU nominal
  (|yawrate|≈commanded, small vert vel, stable alt); else raise INTERRUPT. `[REVIEW → AUTO → HW]`

## Tier 3 — safety subsystems
- **Interrupt / stop-and-reassess** (1.5) — on interrupt: STOP, stash the active task so it isn't
  lost, reassess. Hover if we stopped in time; else evade — move aside if the obstacle is moving,
  nudge opposite if static. `[REVIEW]`
- **Emergency boundary** (6.1) — velocity-scaled trigger distance vs nearest depth → hold; must
  tolerate a slow depth refresh. Survey faster monocular-depth backbones ~2026-08-08 (ROADMAP
  4.1.8d) as an input. `[REVIEW → HW]`
- ~~**SPSC backpressure** (1.4)~~ — **[DONE 2026-08-08]** bounded `try_enqueue` + reject-newest, every drop logged; SITL-verified under a startup storm and an in-air storm. `scripts/test/flood`, `flood-airborne`.
- ~~Interrupt hysteresis + retries (6.3)~~ — **dropped** as overcomplicated; stop-and-reassess covers it.

## Tier 4 — Tello / measurement
- **Velocity modes** (2.3.1 + 2.3.4) — environment-keyed tested constants (indoor slow / open
  fast); keyboard override reads the same table. `[AUTO scaffold → HW tune]`
- **Simpson odometry verify** (2.3.2) — SITL: integrate vs Gazebo ground truth (validates the
  method). Real Tello: tape a rectangle, fly a closed-loop preplanned path, record odometry, diff
  the trace against the known tape geometry (drift = start↔reported-end gap). `[AUTO SITL test → HW]`
- **Active stability correction** (2.3.5) — close the drift loop (monitor vs intended path,
  correct); real-hardware only, SITL won't surface it. `[HW]`
- **Latency + I/O tests** (2.3.6) — record a real flight's I/O + timestamps → deterministic replay
  fixture; measure keypress→response, odometry (wire→parsed), camera (frame→decoded). `[AUTO harness → HW record]`

## Tier 5 — navigation capabilities (each: design → human review → implement → test)
- **GO redesign** (5.2) — per-tick recompute against a live **target** (drift-free); self-contained,
  not hardcoded. Arbitrary points in space are Being-B/SLAM territory, out of scope here. `[REVIEW]`
- **Safe-landing servo** (5.3) — feedback law: center over the landmark, then descend. VLM picks
  the spot; the servo does the precise go-over-and-descend. `[REVIEW]`
- **ORBIT** (1.1.6) — target-anchored. `[REVIEW]`
- **SEARCH** (1.1.7) — 2D circle. `[REVIEW]`
- ~~**Failsafe supervisor** (6.2)~~ — **[DONE 2026-08-08]** real PX4 battery; 20%->RTH / 10%->land-in-place (latched) + reversible manual override; SITL-verified. `scripts/test/battery*`, `override/`. Smart RTH deferred to `docs/scheduled/`.
- **Being B** (SLAM / OctoMap / A*) — backburner. `[DEFER]`

---

## What needs YOU (human review / planning), at a glance
1. Legacy offboard node removal — coupled to simenv migration (9.7 / 8.3).
2. APPROACH motion-gate — approve concept + thresholds (6.4).
3. Interrupt / stop-and-reassess design — incl. moving-vs-static evade (1.5).
4. Emergency boundary — safety-critical spec (6.1).
5. ~~Backpressure (1.4)~~ — **DONE 2026-08-08** (SITL-verified, `scripts/test/flood*`).
6. GO redesign, Safe-landing, ORBIT, SEARCH — each design → review (5.2/5.3/1.1.6/1.1.7). (~~Failsafe supervisor 6.2~~ — **DONE 2026-08-08**.)
7. **Runtime constants** (9.14) — tuning values are compile-time `constexpr`; they must become
   runtime drone-dependent config before real-Tello flight (SITL ≠ Tello dynamics). Spec:
   `docs/scheduled/2026-08-08-runtime-drone-config-constants.md`. `[REVIEW]`

Autonomous items already picked up: LAND flare + ROTATE — **both SITL-verified (Spec 4, 2026-08-08).**
Still to spawn: Spec 1 (interrupt / boundary / APPROACH motion-gate) and Spec 2 (GO redesign /
safe-land / ORBIT / SEARCH) — both specced, not started.
