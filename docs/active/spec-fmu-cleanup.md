# Spec — FMU node cleanup & correctness (fmu_node.hpp)

**Owner:** UNASSIGNED (this or a parallel agent). **Status:** ready. **Runs parallel to** the DJI
backend spec (`spec-dji-backend.md`) — different files, no collision except one shared line noted below.

---

## Context — read these first (a cold agent MUST load these)
- **`docs/active/mission-brief-2026-08-15.md`** — the project: a voice-commanded drone demo for an
  Israeli MOD contest (~2026-08-27). Linux stack (perception + planning) drives a drone backend.
  Platform is moving off the DJI Tello (no indoor position) to a DJI Mini via an Android bridge.
- **`docs/code-guidelines.md`** — house rules. Non-negotiable: **no virtual dispatch, no exceptions**
  (CRTP + tagged dispatch), guard clauses, WHY-comments, ~150-400 LOC file target, don't strip
  commented-out code you didn't write.
- **`docs/NOTES.md`** — design-decision log. The two most recent entries (2026-08-16) describe the
  canned-plan removal + the `TestPlan`/`command_id.hpp` rewrite already landed; read them.
- **`CLAUDE.md`** (repo root) — tooling rules. **All file reads/greps go through `rtk`**
  (`rtk read`, `rtk grep`, `rtk ls`). **The human owns the ENTIRE git workflow — run NO git writes**
  (no add/commit/push/stage). When done, SUGGEST the exact commit in house style (` | ` separators,
  ASCII only, ending `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`).
- **The `Edit` tool is blocked** by a repo Read-deny rule. Edit via `python3` string-replace (assert
  exactly one match before writing) or a full-file `Write`. This is the established pattern.

## Build / verify command (this environment can build)
```
cmake --build build/release/shared/px4 -- -j4        # ~3 min warm; MUST compile + link, exit 0
```
`fmu_node.hpp` is header-only into `fmu_node.cpp`; a change recompiles that one TU + relinks
`bin/llm_to_action_fmu_px4`. The ROS-free unit test (add cases as you extract pure logic):
```
cmake --build build/release/shared/px4 --target fmu_translate_test   # needs GROUNDSTATION_BUILD_TESTS=ON
# or compile standalone: g++ -std=c++17 -I<util2/include> test/fmu_translate_test.cpp
```

## State of the file
`source/llm_to_action/fmu/fmu_node.hpp` is ~2700 LOC, one class `FlightManagementUnitNode`, methods
inline. The canned-plan test scaffolding was already removed and replaced by `TestPlan` +
`runTestPlan()` + `command_id.hpp` + `test/fmu_test_plans.hpp`. This spec is the REMAINING cleanup.

## LOCKS (coordinate before touching)
`controlLoop` (~lines 720-1560) contains the **SEARCH and APPROACH servo branches the Manager
rewrote — LOCKED.** Do not restructure those two without coordinating. Everything else in the loop
(GO/LAND/HOVER/FOLLOW/ORBIT, the test-injection hooks) is fair game.

---

## Tasks (independent; do the safe ones first, verify after each)

### A. Remove `VehicleTelemetry` (dead + wrong units) — SAFE, do first
`struct VehicleTelemetry { altitude_cm; vx_cm_s; vy_cm_s; vz_cm_s; battery_pct; }` at ~line 216.
Only `m_telemetry.battery_pct` is ever read (3 sites: ~677, ~1694, ~1739). The cm velocity/altitude
fields are DEAD, and the backend already exposes `Odometry` (meters, ENU) + `battery_pct()`.
**Do:** delete the struct + `m_telemetry`; replace the 3 `battery_pct` reads with a plain
`i32 m_batteryPct` cache (or read `m_backend->battery_pct()` directly). Verify build.

### B. Extract the observability block into a method — SAFE
The env-gated dashboard block at ~lines 298-335 (reads `FMU_OBSERVABILITY`, creates the A2 image/HUD
publishers, reads `FMU_A2_IMG_W/H`, sets up the VLM log dir) is a big inline chunk in the ctor.
**Do:** move it verbatim into a private `void initDashboardDiagnostics()` called from the ctor at the
same point. Behavior-identical. Verify build.

### C. `max_tokens` — stop truncating the VLM's thoughts
`llamaclient.hpp:51` hardcodes `max_tokens = 256`, set once at construction (`m_jsonRequest["max_tokens"]`).
Thoughts get cut off. **Do:** add a per-call token budget to `LlamaClient` (overload/param on the
send path). FMU passes **~1024 for the first plan of a mission, ~128 for reassess cycles** (branch on
mission state). Minimum acceptable if per-call is awkward: bump the default to 512. Verify build; watch
a live run for un-truncated thoughts.

### D. Units -> meters everywhere — COORDINATE (touches LOCKED servos)
The VLM emits cm / cm-per-s (`x:100`=1 m, `radius_cm`, `standoff_cm`, `speed:30`=0.3 m/s) and the code
sprays `/100.0f` at every use site in `controlLoop` and elsewhere. **Do:** convert **once** at the parse
boundary in `translateToBaseCommands` — store **meters** in the `Cmd` structs (`CmdGo x/y/z`,
`CmdApproach.speed`, `CmdOrbit.radius/speed`, `CmdFollow.standoff`), rename `*_cm`/`*_cm_s` fields to
plain meters, and delete every scattered `/100.0f`. Update the VLM prompt if it documents cm. This
edits the LOCKED SEARCH/APPROACH branches — coordinate with the Manager for those two; do GO/LAND/
HOVER/FOLLOW/ORBIT + the struct/parse changes first.

### E. Decompose `controlLoop` — per-command servo functions — COORDINATE
`controlLoop` is ~850 LOC because every verb's servo is inlined in one switch. **Do:** extract each into
its own private method — `servoGo`, `servoFollow`, `servoOrbit`, `servoLand`, `servoHover` (and, with
the Manager, `servoSearch`, `servoApproach`) — leaving `controlLoop` as dispatch + the shared pre/post
(odometry read, safety, telemetry). Behavior-identical; verify the existing SITL scenarios still fly
(the ones under `scripts/test/SITL/` that use kept `--canned-*` flags). Start with the unlocked verbs.

> FUTURE (an anecdote, NOT this pass): the end-state of pulling each command out is each becoming a
> stateful class (e.g. `ApproachCommand` owning + managing its own state and helpers) -- that is where
> moving command state OUT of the node leads. This pass stops at plain functions for readability;
> do NOT introduce the command classes yet.

### F. (Deferred, when the scenarios are retired) test-injection hooks + demo hacks
- The `controlLoop` fault-injection hooks (`m_floodArmed`, `m_obstacleArmed` inside the emergency-
  boundary SAFETY block, `m_batForce*`) are production-dead but still present. Remove with the Manager
  once the fault scenarios are no longer needed.
- The hardcoded ORBIT geometry (~L1334) + auto-land-the-instant-APPROACH-finishes (~L2273) + the
  no-YOLO approach rig get **replaced** by the modular vision-servo, not blind-deleted. Gated on the
  perception work.

### G. Audit the many small helpers — do they belong in the node?
`fmu_node.hpp` carries a lot of small functions (bbox/anchor/range geometry, format/HUD helpers,
range medians, etc.). Many are **pure and node-independent** and belong in scoped headers, not welded
into the class. **Do:** inventory them; move the pure, reusable ones out (e.g. a `fmu_geometry.hpp` for
the bbox->anchor / range-projection math), following the `command_id.hpp` / `plan_parse.hpp` pattern.
Leave in the class only genuine node methods (those that touch ROS pubs/subs, `m_backend`, the task
queue, or member state). Every pure helper moved out becomes unit-testable — add cases to the ROS-free
test. Verify build after each move. This is the single biggest lever for getting the node under the
LOC ceiling.

## Done means
Every task above build-verified (compile + link, exit 0), the ROS-free unit test still passes, and the
kept SITL scenarios still fly. Suggest commits in house style per change group; do not stage/commit.
