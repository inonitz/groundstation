# Session handoff -- 2026-08-08

For the next agent session. Read this first. It captures what changed today, what did not, what is
mid-flight, and what is left. Dates are absolute. This is the overseer's log, not a spec.

## TL;DR -- current state

- **Spec 3 (failsafe/override/backpressure): DONE.** Committed, SITL-verified, archived to `docs/closed/`.
- **Spec 4 (ROTATE/LAND verification): DONE.** Committed, SITL-verified, archived to `docs/closed/`.
- **Spec 1 (interrupt/boundary/motion-gate): CODE-COMPLETE IN THE WORKING TREE, BUT UNCOMMITTED,
  UNBUILT, AND UNRUN.** This is the top priority. See "Uncommitted work" below. Do not stomp it.
- **Spec 2 (GO/ORBIT/SEARCH/safe-land): NOT STARTED.** Design frozen, ready to spawn. No source touched.
- **Runtime constants loader (ROADMAP 9.14): scheduled, not started.** Decision today: do NOT build it
  before spec-1/spec-2. Reasons in "Strategic decisions" below.
- **SITL suite: 15/15 green** for spec-3/spec-4 scope. Spec-1's 3 new scenarios are wired but UNRUN.
- **Real Tello: never flown.** Zero hardware validation. This is the dominant project risk, not the loader.

## What was committed today

Chain: `585652f -> c3639fd -> f72a9b9 -> e1efeea -> 2807534 -> 06dbd20 -> 7aa346e`.

- `c3639fd` -- landed the reviewed Spec 3 + Spec 4 work (fmu_node.{hpp,cpp,base}, px4_backend battery
  path, keyboard node, perception_runtime health check, the full `scripts/test/` SITL harness, sdf
  models). Deleted `scripts/simenv_llm.sh` and `scripts/setup-nvidia-useraccess.sh`.
- `f72a9b9` -- intent-only commit summarizing the shipped spec-3/spec-4 behavior; also moved both spec
  reports into `docs/closed/`.
- `e1efeea` -- archived the two finished specs, added the 15-row SITL test matrix + item 8.6 to ROADMAP,
  added the runtime-constants gap (9.14), NOTES top note, the two status HTMLs, the scheduled
  runtime-config spec. Deleted the dead `llamaconnect3.cpp` (user's call).
- `2807534` -- reconciled `docs/ARCHITECTURE.md` with what actually shipped; moved `LOCKS.md` ->
  `docs/LOCKS.md` to declutter the root; repointed spec-1/spec-2 at the new lock path.
- `06dbd20` -- codified the commit-message style in `docs/code-guidelines.md` (intent-first,
  `|`-separated, ASCII only).
- `7aa346e` -- added the dated "Overseer update (2026-08-08)" block to spec-1 and spec-2 (read the
  closed reports; new constants are 9.14 debt; new test dirs must become matrix rows; 9.12-9.14 taken;
  follow the commit rule).

## What did NOT change (guardrails held)

- **`GenericCommand` byte layout untouched.** Still 8-byte aligned. Nobody may touch it.
- **Spec 2 source untouched.** `llm_base.hpp` and the GO/ORBIT/SEARCH/safe-land laws do not exist yet.
- **Perception model unchanged** (YOLO26n). No vision code shipped today.
- **No real-drone integration.** Everything is PX4 Gazebo SITL. The Tello odometry frame is still
  unverified (flagged in spec-2's own follow-ups).
- **The 20 Hz control loop contract is intact.** FlightState machine, ENU convention, SPSC queue.

## Uncommitted work in the tree (CRITICAL -- handle first)

`git status` on `feature-llm-driver` shows work that is NOT from the overseer session. It is a spec-1
subagent's landed implementation, left uncommitted. All its locks in `docs/LOCKS.md` are released, and
the lock notes read "needs build+SITL" / "runnable after build; unrun".

Modified source (spec-1):
- `source/llm_to_action/fmu/fmu_node.hpp` -- `raiseInterrupt()`, `m_stashedTask`, interrupt-storm state
  (`m_interruptEscalated`), the emergency-boundary trip (`kBoundaryBaseM + kBoundaryVelScale*speed`),
  and the APPROACH `approach_impact` motion-gate. Canned test hooks for boundary/storm/approach-impact.
- `source/llm_to_action/fmu/fmu_node.cpp` -- 3 canned CLI flags (`--canned-boundary/-storm/-approach-impact`).
- `source/llm_to_action/fmu/fmu_node_base.hpp` -- 7 new constants (1.5/6.1/6.3/6.4).
- `source/llm_to_action/perception/detection_query.hpp` -- `nearestDepthM()` (pure, unit-testable).
- `source/llm_to_action/fmu/test/detection_query_test.cpp` -- a `nearestDepthM` case.

New untracked test dirs (spec-1 owned): `scripts/test/boundary/`, `scripts/test/interrupt-storm/`,
`scripts/test/approach-impact/`. Modified `scripts/test/approach-real/` too.

Modified docs (spec-1): `docs/LOCKS.md`, `docs/ROADMAP.md` (3 new test rows, unrun),
`docs/code-guidelines.md` (loop-local hoisting rule), `docs/scheduled/2026-08-08-runtime-drone-config-constants.md`,
`docs/active/2026-08-07-spec-1-...md` (its implementation report).

**What to do with it, in order:**
1. Do NOT discard or overwrite it. Do NOT re-run the spec-1 agent from scratch over it.
2. Read spec-1's implementation report (bottom of its spec file) to see what it claims and what it left.
3. **Resolve the still-open design decision** spec-1 flagged: `nearestDepthM` cannot tell an obstacle
   from the car being intentionally approached, and every SITL scenario flies with the car in frame.
   Confirm the boundary is suspended (or target-excluded) during APPROACH, or it will interrupt every
   legitimate approach/override run. Verify this is actually handled before trusting the tests.
4. Build the workspace and run the 3 new scenarios (`boundary`, `interrupt-storm`, `approach-impact`)
   plus a regression pass of the existing 15. Only then mark ROADMAP 1.5/6.1/6.3/6.4 done.
5. Commit under the codified message style, separating spec-1's code from any doc bookkeeping.

`.claude/settings.local.json` is also untracked -- local settings, leave it.

## Planned vs achieved today

Everything the overseer set out to do got done: review the shipped agent work and update all docs;
add the SITL test matrix (all pass); write the runtime-constants scheduled spec; move the finished
specs to `docs/closed/`; produce the two status HTMLs (`status-map`, `roadmap-progress`); reconcile
`ARCHITECTURE.md`; move `LOCKS.md` into `docs/`; codify the commit-message rule; brief the spec-1 and
spec-2 agents on the state that shifted under them.

Roadmap standing at last count: ~46/86 leaf items done (~53%), spec-3/spec-4 shipped, spec-1 landed
but unverified, spec-2 and the loader open.

## Strategic decisions made today (the 10-hour question)

Grounded, not aspirational. The overseer asked whether to build the constants loader now and how to
sequence the remaining work with ~10 hours to ship.

- **The loader is not the bottleneck; Tello bring-up is.** The loader's value is realized only when
  the real drone flies, and nothing about it gets you there. The Tello's odometry frame is unverified
  -- if position comes back in the wrong frame or is too drifty, no control law works, loader or not.
  That is an observability problem, not a tuning problem.
- **Do NOT build the loader before spec-1/spec-2.** You would build it twice, because both specs add
  more constants. Let them keep appending `constexpr`, then consolidate into a thin profile seam once
  the full set is frozen, right before the first real flight. Full `DroneConfig` apparatus waits.
- **You cannot finish spec-1 + spec-2 + loader + real-drone migration in 10 hours.** Pick the deliverable.
  - Real-Tello path (recommended if hardware is a MUST): freeze SITL scope now. Spend the hours on
    bring-up (measure the odometry frame FIRST), takeoff/hover/land on hardware, one movement law on
    hardware, then the MUST safety checks -- battery failsafe and manual override -- validated on a
    real battery and a real override, using the fault-injection hook at low altitude. Defer spec-2.
  - SITL-POC path: skip hardware, land spec-1, attempt spec-2 in SITL, no loader. Spec-2 is the risk
    (3 commands + a missing depth-map accessor).
- **Parallel specs is the wrong axis.** Spec-1/2/4 all edit the same `fmu_node.hpp` movement handler,
  so the practical ceiling is ~2-3 code specs before merge cost dominates. Hardware testing is serial
  -- one drone, one airspace, one operator -- and no spec count changes that.
- **Test migration.** Do not port the SITL harness to hardware; it is log-assert over a simulator with
  canned injection. Keep the SITL suite as the code-regression gate. Build a separate, small, manual
  hardware protocol ordered by blast radius: odometry-reads-sane hand-carried -> low hover -> bounded
  movement -> failsafes -> autonomy. Bench the failsafes on the ground before trusting them airborne.
- **Git strategy.** Minimize parallelism. The merge hotspot is one file -- the 20 Hz safety loop.
  Spec-1's interrupt core and spec-2's shared aim helper both refactor the same APPROACH branch, so
  landing them from two branches at once is a guaranteed conflict in safety code. Sequence them:
  spec-1 (safety spine) first, spec-2's laws on top. `fmu_node_base.hpp` conflicts are trivial
  (append-only). Run the full SITL suite after every merge as the gate.

## TODO (ordered)

1. **Build, verify, and commit the uncommitted spec-1 work** (see "Uncommitted work"). Resolve the
   boundary-vs-approach-target decision before trusting its tests.
2. **Choose the ship target** -- real Tello or SITL POC. Everything downstream forks on it.
3. If Tello: hardware bring-up, starting by measuring the reported odometry frame; then takeoff/land;
   then one movement law; then failsafe + override validated on hardware.
4. If SITL POC: spawn spec-2 (sequence it after spec-1's safety spine lands).
5. Runtime constants loader: thin profile seam, only near the first real flight, over a frozen set.

## Invariants the next agent must keep

- rtk wrappers only via Bash (`rtk read/grep/ls/find/git`); native Read/Grep/Glob are forbidden by
  `CLAUDE.md`. Edit via python heredoc with `assert s.count(old)==1`.
- Never touch the `GenericCommand` byte layout.
- Locks live at `docs/LOCKS.md`. Read it before editing any shared FMU file; hold short; release.
- Commit-message style: `docs/code-guidelines.md` "Review & commits". Intent-first, `|`-separated, ASCII.
- The Tello odometry frame is unverified. Treat any real-drone control as unproven until measured.
