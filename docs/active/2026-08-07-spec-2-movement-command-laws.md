# Spec 2 — Movement command laws

**Status:** unassigned (for a spawned session). **ROADMAP:** 5.2 (GO redesign), 1.1.6 (ORBIT),
1.1.7 (SEARCH), 5.3 (safe-landing servo).
**Owns (edits):** `source/llm_to_action/fmu/fmu_node.hpp` (parser, dispatch switch, movement handler),
`.../fmu/fmu_node_base.hpp` (constants), `.../fmu/llm_base.hpp` (VLM action schemas).
Heavy overlap of the movement handler / dispatch switch / parser with Spec 1 & 4 — overseeing session
merges. Keep each command's code in its own clearly-labelled block.

> **Repo conventions (start-cold):** use `rtk read/grep/ls` (native Read/Grep/Glob are forbidden by
> `CLAUDE.md`); edit via python heredocs with `assert s.count(old)==1`. **Never touch the
> `GenericCommand` byte layout.** Follow the existing APPROACH servo (5.1) and GO cross-track patterns
> exactly. No full builds; human does build + SITL.

## Reference patterns (already in the tree — copy these, don't invent)
- **Parser** `translateToBaseCommands` (~line 819): `else if (action == "...")` branches build a
  `Cmd*` and enqueue. Add local `Cmd*` decls near the top with the others.
- **Dispatch** `switch (id)` (~line 632): `case CommandID::GO/APPROACH:` freeze per-command state at
  activation (target, speed) from `od = m_backend->odometry()`.
- **Movement** `if (m_hasActive)` chain (~line 427): `if (id==GO){...} else if (id==APPROACH){...}` —
  per-tick control law + `completeCurrent("..._ok")` / FAIL.
- **Live-detection aim:** `detectionByLabel` (5.1.1) + the APPROACH yaw-center/range-decel servo
  (5.1.2) already do "aim from the current frame." This is the substrate to reuse.

## Design
### 5.2 GO redesign (drift-free, self-contained)
Today GO freezes a world-ENU target **once** from drifting odometry (dispatch ~line 653). Redesign:
- If the `go` command names a target object (`"target_object"`), recompute the aim **per tick** from
  live perception (reuse the APPROACH aim substrate) → drift-free, re-grounds each tick.
- If it's a bare relative offset (no target), keep today's frozen start→target cross-track line
  (correct for dead-reckoned nudges).
- **Refactor requirement (user, explicit):** factor the per-tick "aim from live detection → world
  velocity" into ONE small reusable unit shared by APPROACH + GO (+ ORBIT + safe-landing). The code
  must read as self-contained, not hardcoded/inlined per command. Arbitrary world points (no target,
  no offset) are **out of scope** — that is Being-B/SLAM.

### 1.1.6 ORBIT (target-anchored)
Schema already advertised (`llm_base.hpp` ~line 56): `{"action":"orbit","target_object","radius_cm",
"angle_deg","direction":"cw|ccw","speed"}`. Add `CmdOrbit` (struct exists, line ~91) parse + dispatch
+ movement. Movement: hold `radius` from the tracked target (perception aim) while progressing around
the circle at `speed`; sweep `angle_deg` then `completeCurrent("orbit_ok")`. Target lost → FAIL
(mirror APPROACH lost-target). Perception-gated.

### 1.1.7 SEARCH (2D circle, no target)
**Check `llm_base.hpp` — SEARCH may not be advertised yet; if missing, add the schema + a line in the
system prompt.** `CmdSearch` struct exists (line ~99). Movement: fly a 2D circle / sweep pattern to
bring an object into view; `completeCurrent("search_ok")` when the named object appears in the
snapshot, or after a full sweep → FAIL/`search_exhausted`.

### 5.3 Safe-landing servo
Likely needs a new schema (`{"action":"safe_land","target_object"}` or landmark) — add to
`llm_base.hpp` + system prompt. Feedback law: keep the landmark centered under the drone (perception
aim → lateral correction) while descending; when centered within tolerance AND low → transition to
the normal LAND state machine (reuse the flare, Spec 4). VLM picks the spot; this executes the precise
go-over-and-descend. Do **not** duplicate the LAND descent — hand off to `FlightState::LANDING`.

## New constants (fmu_node_base.hpp)
Orbit: `kOrbitRadiusToleranceM`, `kOrbitTangentialGainHz`. Search: `kSearchSweepSpeed`,
`kSearchCircleRadiusM`. Safe-land: `kSafeLandCenterTolM`, `kSafeLandDescendStartAltEnu`. Tune in SITL.

## Testing (log-based, SITL)
Reuse the canned-approach rig with a detected object (vendored hatchback gz model). Canned plans:
takeoff → orbit/search/safe_land → assert `orbit_ok`/`search_ok`/safe-land handoff logs. Lost-target
paths assert FAIL. Coordinate canned infra with Spec 4.

## Out of scope
Collision avoidance during these maneuvers (Spec 1 owns the boundary/interrupt). Arbitrary-point GO
(Being B). Multi-orbit > 360°.

## Implementation report (session: append below, do not edit above)
<!-- files changed, the shared aim-unit's interface, schema additions, what was/wasn't SITL-tested -->
