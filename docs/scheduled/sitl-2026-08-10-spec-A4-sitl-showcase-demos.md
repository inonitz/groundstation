# A4 — SITL showcase demos (S1 / S2 / S3)

**Status:** scheduled / not started. **Created:** 2026-08-10. **Revised:** 2026-08-09 (session review —
see Revision log). **Branch:** feature-llm-driver (SITL showcase).
**Depends:** A1 (runner), A3 (S3 voice — specifically the `--canned-voice`/`--canned-complete` flags,
confirmed absent from `fmu_node.cpp` today). **ROADMAP:** 3, 5, 6. **Lock:** new demo dirs only; no
`fmu_node.hpp`.

## Objective
Turn the proven-in-tests stack into three end-to-end, VLM-driven demos that run the *whole* system,
not a single feature rig. These are the SITL showcase and the fallback if the Tello or SLAM slips.

## Grounding (verified against this checkout, 2026-08-09 — S1 cheaper than specced, S2 harder)
- `scripts/demo/` does not exist yet (confirmed).
- **S1 is cheaper than the original spec implied — near-zero new code.** `kSystemPrompt`
  (`llm_base.hpp:52-77`) already documents `orbit`, `approach`, and `search` as VLM-callable actions;
  `translateToBaseCommands()` already parses all three from any VLM-produced plan
  (`fmu_node.hpp:1645/1651/1660`) — no canned flag, no new parsing. `scripts/test/vlm/run.sh` is already
  a near-identical rig (`FMU_OBJECTIVE="Take off, find the car, approach it, then land."`,
  `FMU_CANNED_FLAG=""`, `WORLD_NAME="default_car"`, `LAUNCH_VLM="1"`) — S1 can be built by copying it and
  extending the objective to include "circle it" (ORBIT) plus writing a real PASS/FAIL `filter.sh` (the
  `vlm/` one is milestone-only today, no verdict).
  **Correction to the exact status strings** (verbatim from `fmu_node.hpp:517-1043`): `takeoff_ok`,
  `land_ok`, `go_ok`, `rotate_ok`, `approach_ok`, `approach_lost_failed`, `orbit_lost_failed`, `orbit_ok`,
  **`search_ok`** (not `search_*` as the original spec wrote), `search_exhausted`, `noop_ok`. The ordered
  assertion is `search_ok -> approach_ok -> orbit_ok -> land`, explicitly excluding `search_exhausted`
  and the two `*_lost_failed` variants as failure cases.
- **S2 is harder than the original spec implied — no existing rig proves real obstacle -> interrupt ->
  re-plan with live perception.** Both close analogs bypass real perception synthetically:
  - `scripts/test/boundary/`: `WORLD_NAME="empty"`, a synthetic burst, and the run script's own comment
    says the drone "hovers after the burst (no VLM)" — no re-plan at all, wrong shape for S2.
  - `scripts/test/interrupt-storm/`: VLM-driven post-storm (closer), but the trigger is still synthetic —
    `injectCannedBoundaryPlan`/`injectCannedStormPlan` (`fmu_node.hpp:1806-1826`) set `m_obstacleArmed=true`,
    and while armed, `nearestM` is **hardcoded to `0.4f`, bypassing perception entirely**
    (`fmu_node.hpp:560-583`, comment: "bypass the perception snapshot so the trip is deterministic").
    Real depth (`nearestDepthM`/`nearestFreeDepthM`) only runs in the un-armed branch.
  - `scripts/test/approach-impact/` similarly forces the motion-gate off-nominal in an `empty` world
    rather than using any real obstacle.
  - **No existing world has a verified obstacle sitting in an approach flight path.**
    `dependencies/default_car.sdf` has one object (car, pose `6 7 0.3`); `rubicon_targets.sdf` has four
    scattered objects (`11.5,1,5 / 6,2,1.5 / 3,8,2.5 / 12,-4.5,4.1`) — none confirmed to sit between a
    spawn point and an approach target. **S2 needs a new world or new object placement** to genuinely
    exercise the real (non-bypassed) boundary branch with a live VLM re-planning around it — this is a
    real content-creation task, not pure composition of existing verbs as the original spec framed it.
- S3: confirmed `--canned-voice`/`--canned-complete` are absent from `fmu_node.cpp`'s current canned-flag
  list (18 flags, none named voice/complete) — correctly blocked on A3, as the original spec said.
- Available worlds (`dependencies/*.sdf`): `default_car`, `empty`, `harmonic`, `rubicon`,
  `rubicon_targets`, plus individual `gz_models/` (hatchback, hatchback_blue, person_standing,
  person_walking). `default_car` suffices for S1. S2's new placement (see above) should reuse an
  existing model (e.g. drop a second `hatchback` or a person model directly in the flight path of
  `default_car`'s approach vector) rather than author new geometry — still new SDF work, just not
  starting from nothing.

## Scope
- **In:** `scripts/demo/{s1,s2,s3}/run.sh` + `filter.sh`.
  - **S1 Find & inspect:** objective "find the car and circle it" -> SEARCH -> APPROACH -> ORBIT -> land.
    Build from `scripts/test/vlm/run.sh` as a template; write a real PASS/FAIL `filter.sh` (the source
    template's is milestone-only).
  - **S2 Hazard reroute:** APPROACH with an obstacle in the path -> `emergency_boundary` interrupt ->
    the VLM reassesses and re-plans. **Requires a new/modified world** placing a second object in the
    flight path (see Grounding) — budget real time for this, it is not a `run.sh`/`filter.sh`-only task.
  - **S3 Voice stand-down:** patrol, then a spoken/canned "done, land" ends it. Blocked on A3.
- **Out:** new motion laws. Composition of existing verbs only (S1, S3) — S2 is the one exception, which
  needs new SITL content, not new code.

## Files
- Create: `scripts/demo/s1/run.sh`, `scripts/demo/s1/filter.sh` (copy-and-extend `scripts/test/vlm/`).
- Create: `scripts/demo/s2/run.sh`, `scripts/demo/s2/filter.sh`, and either a new `dependencies/*.sdf`
  world or a modified copy of `default_car.sdf`/`rubicon_targets.sdf` with a verified obstacle placement.
- Create: `scripts/demo/s3/run.sh`, `scripts/demo/s3/filter.sh` (rides A3's `--canned-voice` path).

## Tests to create
- **[AUTO]** S1: assert the ordered task-completions `search_ok -> approach_ok -> orbit_ok -> land_ok`
  (corrected status-string names per Grounding).
- **[AUTO]** S2: assert an `emergency_boundary` interrupt (real, not `--canned-boundary`-forced) followed
  by a fresh plan (not a crash/land) — this assertion is only meaningful once the new world/placement
  above actually triggers the un-armed, real-perception boundary branch.
- **[AUTO]** S3: assert `land` after the `[USER]` block (rides A3's `--canned-voice`/`--canned-complete`
  path once it lands).
- **[HUMAN]** watch each once for plan *quality* — the state-trace is asserted, the VLM's judgment is not.

## Acceptance
All three run green headless on their deterministic milestones, and look right in one live watch each.

## Change-impact (per `docs/code-guidelines.md`)
- **What this changes:** purely additive — new demo directories, at most one new/modified world file for
  S2. No existing scenario's world or run script changes (S2 should add a NEW sdf or a copy, not edit
  `default_car.sdf`/`rubicon_targets.sdf` in place, so the 20 existing scenarios that reference those
  worlds are unaffected).
- **Breaks existing behavior:** no, provided S2 doesn't edit shared world files in place.
- **Tests that re-run as-is:** all 20 SITL scenarios (A1).
- **Tests that are new:** the three listed above.

## Agent notes
S1 is genuinely pure composition — safe to parallelize with A2, start immediately using `vlm/` as a
template. S2 needs real SITL-content work (new/modified world) before its assertion is meaningful — budget
it separately, don't estimate it at S1's speed. S3 is blocked until A3 lands (confirmed: the two canned
flags it needs don't exist yet).

## Revision log
- 2026-08-09: corrected `search_*` to the verbatim status string `search_ok` (with `search_exhausted` as
  the explicit failure case); found `scripts/test/vlm/` is a ready-made template for S1, making it
  cheaper than implied; found the two closest existing "obstacle" rigs (`boundary/`, `interrupt-storm/`)
  both bypass real perception with a hardcoded `nearestM=0.4f` and/or an `empty` world, so S2 cannot
  reuse them as evidence the real path works — S2 needs new SITL world content, which is materially more
  work than "compose existing verbs"; listed available worlds/models for S2's placement; added
  change-impact section noting S2 must not edit shared world files in place.
