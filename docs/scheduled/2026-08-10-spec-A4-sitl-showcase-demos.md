# A4 — SITL showcase demos (S1 / S2 / S3)

**Status:** scheduled / not started. **Created:** 2026-08-10. **Branch:** feature-llm-driver (SITL showcase).
**Depends:** A1 (runner), A3 (S3 voice). **ROADMAP:** 3, 5, 6. **Lock:** new demo dirs only; no `fmu_node.hpp`.

## Objective
Turn the proven-in-tests stack into three end-to-end, VLM-driven demos that run the *whole* system,
not a single feature rig. These are the SITL showcase and the fallback if the Tello or SLAM slips.

## Scope
- **In:** `scripts/demo/{s1,s2,s3}/run.sh` + `filter.sh`.
  - **S1 Find & inspect:** objective "find the car and circle it" → SEARCH → APPROACH → ORBIT → land.
  - **S2 Hazard reroute:** APPROACH with an obstacle in the path → `emergency_boundary` interrupt →
    the VLM reassesses and re-plans.
  - **S3 Voice stand-down:** patrol, then a spoken/canned "done, land" ends it.
- **Out:** new motion laws. Composition of existing verbs only.

## Tests to create
- **[AUTO]** S1: assert the ordered task-completions (`search_*` → `approach_ok` → `orbit_ok` → land).
- **[AUTO]** S2: assert an `emergency_boundary` interrupt followed by a fresh plan (not a crash/land).
- **[AUTO]** S3: assert `land` after the `[USER]` block (rides A3's canned-voice path).
- **[HUMAN]** watch each once for plan *quality* — the state-trace is asserted, the VLM's judgment is not.

## Acceptance
All three run green headless on their deterministic milestones, and look right in one live watch each.

## Agent notes
Pure composition — safe to parallelize with A2. S3 is blocked until A3 lands.
