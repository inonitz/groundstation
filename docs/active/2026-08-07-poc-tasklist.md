# POC Task List — consolidated 2026-08-07

Single actionable list, sorted with the user this session. `docs/ROADMAP.md` stays the master
objective tree; this is the near-term work queue drawn from it. Visual companion:
`2026-08-07-task-map.html`.

**Legend**
- `[AUTO]` — decided + bounded; Claude implements and build-checks solo (SITL/flight verify is human).
- `[REVIEW]` — needs human design/decision before any code (brainstorm → spec → plan → implement).
- `[HW]` — needs the real drone or a SITL run (human-in-the-loop); cannot be done off-desk.
- `[DONE]`.

---

## Done this session (2026-08-07)
- **Battery through GenericBackend** (6.2 dependency) — Tello returns real telemetry `bat`; PX4
  returns sentinel `-1` (no battery topic subscribed); FMU reads it per-loop instead of the stub. `[DONE]`
- **build.sh / build.ps1** reconciled to clean/configure/build only; `.ps1` rewritten to mirror
  `.sh`; run/sim actions dropped (belong in `scripts/`). (9.6) `[DONE]`
- **Dead CMake option** `GROUNDSTATION_BUILD_SYSTEM_BACKEND_TYPE` removed. (9.5) `[DONE]`
- **Branch push** — `feature-llm-driver` synced to origin, 0 ahead/behind. (9.1) `[DONE]`
- **LAND flare** (9.11) — descent tapers from `kLandDescendVelEnu` to `kFlareTouchdownVelEnu`
  below `kFlareStartAltEnu`. Code landed; **SITL-verify pending.** `[AUTO → HW verify]`
- **ROTATE end-to-end** (1.1.2) — was scaffolding-only + silently dropped. Added: rotate parse
  branch (`direction` + `angle_deg`), `CommandID::ROTATE` dispatch that freezes target heading,
  clamped-P-yawrate movement branch completing within `kRotateCompletionDeg`. Code landed;
  **SITL-verify pending.** `[AUTO → HW verify]`

## Resolved / parked
- **Legacy offboard node** (9.7-related) — **KEEP** (user decision 2026-08-07). Retain
  `source/llm_to_action/offboard_ctrl/` and `scripts/simenv.sh` for legacy reference / code
  recycling. Not removed. `[parked]`

## Specs for parallel sessions (2026-08-07)
The review items below are decomposed into 4 work-packages, each with its own spec file; a spawned
session owns one file and appends its report at the bottom. Merge/review of overlapping edits to
`fmu_node.hpp` is done by the overseeing session, not the workers.
- Spec 1 — `2026-08-07-spec-1-interrupt-reactive-safety.md` (1.5, 6.1, 6.4)
- Spec 2 — `2026-08-07-spec-2-movement-command-laws.md` (5.2, 1.1.6, 1.1.7, 5.3)
- Spec 3 — `2026-08-07-spec-3-failsafe-supervisor-backpressure.md` (6.2, 1.4)
- Spec 4 — `2026-08-07-spec-4-verification-rotate-granularity.md` (ROTATE fix, LAND/ROTATE tests)

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
- **SPSC backpressure** (1.4) — empirical: drive the FMU task queue with real VLM plan output,
  observe growth/behaviour, mitigate directly in the queue (bounded `try_enqueue` + drop/reject
  policy). Not a paper exercise. `[REVIEW → HW]`
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
- **Failsafe supervisor** (6.2) — now unblocked by the battery field. `[REVIEW]`
- **Being B** (SLAM / OctoMap / A*) — backburner. `[DEFER]`

---

## What needs YOU (human review / planning), at a glance
1. Legacy offboard node removal — coupled to simenv migration (9.7 / 8.3).
2. APPROACH motion-gate — approve concept + thresholds (6.4).
3. Interrupt / stop-and-reassess design — incl. moving-vs-static evade (1.5).
4. Emergency boundary — safety-critical spec (6.1).
5. Backpressure — needs a real VLM run to observe (1.4).
6. GO redesign, Safe-landing, ORBIT, SEARCH, Failsafe supervisor — each design → review (5.2/5.3/1.1.6/1.1.7/6.2).

Autonomous items already picked up: LAND flare + ROTATE (both code-landed, awaiting your build + SITL).
