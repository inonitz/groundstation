# Spec 1 — Interrupt & reactive safety

**Status:** unassigned (for a spawned session). **ROADMAP:** 1.5, 6.1, 6.4.
**Owns (edits):** `source/llm_to_action/fmu/fmu_node.hpp`, `.../fmu/fmu_node_base.hpp`.
Overlaps the movement handler with Spec 2 & 4 — the overseeing session merges; keep edits localized
and clearly commented.

> **Repo conventions (read first, you start cold):** this project's `CLAUDE.md` forbids the native
> Read/Grep/Glob tools — use `rtk read <file>` / `rtk grep <pat> <path>` / `rtk ls` via Bash. Edit
> with python heredocs (`open().read()/.replace()/.write()` with `assert s.count(old)==1`) since
> native Edit needs a blocked Read. **Do NOT touch the `GenericCommand` byte layout** (`m_id` +
> `m_padToMultipleForCmd` + `union m_rawBytes`) — it is intentionally 8-byte aligned. Match existing
> style/indentation. Do not run a full build (heavy); leave build + SITL verify to the human.

## Overseer update (2026-08-08) -- read before the SESSION HANDOFF below
Specs 3 and 4 shipped and moved to `docs/closed/` (spec-3 failsafe + backpressure, spec-4 rotate +
land). Read their reports before you build on them -- the code under you changed. APPROACH now brakes
on a dead-reckoned travel budget with a 3.0 m standoff, not a live-depth servo at 2.0 m; your motion-
gate (6.4) sits on top of that shipped behavior, so re-read the branch before wiring the gate. ROTATE
is accumulated-angle and LAND has a flare taper. Spec 4 is no longer an active co-editor; the shared
canned-plan rig it built is in the tree -- reuse it, do not coordinate live.

Your seven new constants are runtime-config debt. They are already pre-listed in
`docs/scheduled/2026-08-08-runtime-drone-config-constants.md` (ROADMAP 9.14). Whether they land as
`constexpr` fallbacks or in the loader is the re-sync step-2 decision; either way keep that scheduled
doc in sync. One binary must load per-drone profiles -- SITL numbers are only the fallback.

Any new SITL test dir must also land as a row in the ROADMAP "SITL test matrix" (now 15/15 green)
once it passes. Creating the dir is not enough -- the matrix is what the overseer checks. ROADMAP
9.12-9.14 are taken (AGL, off-heading, runtime-constants); pick fresh numbers for new debt.

Commit messages: `docs/code-guidelines.md` "Review & commits" now carries the hard rule --
intent-first, `|`-separated, ASCII only. Follow it.

## Goal
One reflex shared by three triggers: **detect a problem → STOP → stash the active task → wake the
VLM to reassess → hold until cleared.** This is the safety spine the other specs lean on.

## Current state
The 20 Hz tick is `fmu_node.hpp` ~line 376+ (`od = m_backend->odometry(); n/e/d = od.pos.*; st =
m_flightState.load(...)`). Movement commands run in `if (m_hasActive)` (~line 427) dispatching by
`m_currTask.m_cmd.id()`. There is **no** interrupt/hold path today: a task runs to completion or
FAIL; nothing can pre-empt it and resume later.

## Design
### A. Interrupt core (1.5)
Add one helper and one saved slot:
- Members: `ActiveTask m_stashedTask{}; bool m_hasStashed{false};` (near `m_currTask`).
- `void raiseInterrupt(const char* reason)`:
  1. `m_backend->set_velocity(Vec3{0,0,0}, 0.0f);` — immediate hover/STOP.
  2. If `m_hasActive`: copy `m_currTask` → `m_stashedTask`, `m_hasStashed=true`, `m_hasActive=false`.
  3. Log `[FMU_NODE_DEBUG] INTERRUPT (reason=%s): stashed=%s hover+reassess`.
  4. Trigger the existing event-driven VLM wake with `reason` folded into the prompt (see the
     dynamic-prompt builder ~line 716) so the model reassesses with context.
- **Hold-clearance:** while interrupted and no active task, keep streaming hover each tick. Resume is
  implicit: the VLM's next plan enqueues normally. The stashed task is **not** auto-resumed (the
  reassess decides); expose it in the prompt as "interrupted: <thought>" so the model can re-issue if
  still valid. (Auto-resume is out of scope — reassess owns the decision.)

### B. Emergency boundary (6.1) — a trigger for A
Each tick, after odometry: `speed = norm(od.vel)`, `trigger = kBoundaryBaseM + kBoundaryVelScale *
speed`. Read the nearest obstacle distance from the atomic `PerceptionSnapshot` the FMU already holds
for the prompt (min `median_depth_cm/100` over detections; if you must, add a small
`nearestDepthM()` helper next to the existing snapshot accessor). If `nearest > 0 && nearest <
trigger` → `raiseInterrupt("emergency_boundary")`. Depth is slow: gate on snapshot age — if the
snapshot is older than `kBoundaryMaxSnapshotAgeMs`, treat nearest as unknown (do **not** trip on
stale data; optionally slow down instead). Constants → `fmu_node_base.hpp`.

### C. APPROACH motion-gate (6.4) — a trigger for A
In the APPROACH movement branch (`else if (id == CommandID::APPROACH)`, ~line 476+), at the tick
where "reached/approach_ok" would be declared, **also** require nominal motion:
`fabs(od.yawrate) < kApproachNominalYawrate && fabs(od.vel.z) < kApproachNominalVertVel` (altitude
not collapsing). If motion is out of nominal → `raiseInterrupt("approach_impact")` instead of
`approach_ok`. (Root cause: a real collision produced yawrate 6.9, vert vel −1.75, alt 0.99→0.02 m in
~1 s but range read 1.83 m off an impact frame and declared success.)

## New constants (fmu_node_base.hpp)
`kBoundaryBaseM` (~0.6), `kBoundaryVelScale` (~0.5 s), `kBoundaryMaxSnapshotAgeMs` (~500),
`kApproachNominalYawrate` (~1.0 rad/s), `kApproachNominalVertVel` (~0.6 m/s). Tune in SITL.

## Testing (log-based, SITL)
Reuse the canned-plan rig (`injectCannedPlan`/`--canned*`). (1) Force a boundary trip with a canned
obstacle → assert `INTERRUPT (reason=emergency_boundary)` + hover. (2) Reuse the canned-approach
collision path → assert `INTERRUPT (reason=approach_impact)` NOT `approach_ok`. Coordinate the test
harness with Spec 4 (shared canned infra).

## Out of scope
Interrupt hysteresis / max-retries (6.3, dropped). Auto-resume of the stashed task. Evasion motion
(move-aside / nudge-opposite) — design it here only if trivial; otherwise leave a stub + note for a
follow-up, hover-and-reassess is the MVP.

## Implementation report (session: append below, do not edit above)
<!-- files changed, key decisions, deviations from this spec, what was/wasn't SITL-tested -->


---

## SESSION HANDOFF — shelved, resume in the morning (2026-08-08)

**Status:** NOT STARTED (no source edited). Plan designed, reviewed by the overseer, and
**approved (rev 2)**, then deferred because two other agents (spec-2, spec-4) are still
working and a **runtime-file-loaded constants restructuring** is landing that my constants
must fit into. Nothing in `fmu_node.hpp` / `fmu_node_base.hpp` / `detection_query.hpp` has
been touched. docs/LOCKS.md was all-`FREE` at last check but do NOT trust that — re-read it.

### 0. FIRST, re-sync with the codebase (things likely changed overnight)
Before writing any code, verify these — several are expected to have moved:
1. **`rtk read docs/LOCKS.md`** — confirm `fmu_node.hpp` + `fmu_node_base.hpp` are `FREE` (or held
   by you). If held by another agent: **wait or do free work**, never override. Any file you
   edit beyond those two (`detection_query.hpp`, `docs/code-guidelines.md`, `docs/ROADMAP.md`)
   **must be added as a row in docs/LOCKS.md and held** — overseer was emphatic about this.
2. **Constants restructuring (BLOCKER):** check whether physical/tunable constants are still
   `constexpr` in `fmu_node_base.hpp` or have moved to a **runtime drone-dependent config file**
   (SITL vs reality values differ and can't be one hardcoded number). `rtk grep` for a new
   config loader / a runtime constants struct. **If it landed, my 7 new constants go into that
   path, NOT hardcoded into `fmu_node_base.hpp`.** This decides where §1 of the plan writes.
3. **Re-read the current `fmu_node.hpp`** — spec-2/spec-4 edit the same movement handler /
   dispatch switch / prompt builder. My line anchors (below) may have shifted; re-locate by
   symbol, not line number. Watch for merge overlap on the APPROACH branch and `buildDynamicPrompt`.
4. **`rtk read` this whole spec top section** in case the overseer amended requirements.

### 1. The approved plan (full copy — the scratch plan file may not be reachable in a new session)
Scratch copy also at `/root/.claude/plans/snazzy-snacking-cosmos.md` (rev 2) if present.

**Owns/edits:** `fmu_node.hpp`, `fmu_node_base.hpp` (locked). Plus `detection_query.hpp`,
`docs/code-guidelines.md`, `docs/ROADMAP.md` (add LOCKS rows + hold).

**Guardrails:** rtk-only reads; edit fmu files via python heredoc with `assert s.count(old)==1`
(native Edit needs a blocked Read); never touch the `GenericCommand` byte layout; match style
(tabs, `m_`/`k`/`b` naming, `u8/f32`, guard clauses, explicit `return;`, `[FMU_NODE_DEBUG]` logs);
no full build / no SITL — human verifies.

**Data facts (verified this session):** `PerceptionSnapshot{ TargetDetection dets[16]; u32 count;
u64 host_stamp_us; bool valid; }`; `TargetDetection{ ... f32 median_depth_cm; }`
(`build/.../vision-src/vision/include/vision/perception_types.hpp`). `nowUs()` (steady_clock us)
shares the epoch with `host_stamp_us`, so snapshot age = `nowUs() - snap->host_stamp_us`.
`m_perception->snapshot()` returns `std::shared_ptr<PerceptionSnapshot>`. `od.vel` is ENU (z=Up),
`od.yawrate` available. controlLoop declares ALL locals at the top (file idiom + new guideline).

**Guideline to add** (`docs/code-guidelines.md`, "Structure & idioms"): hoist loop-body locals to
the top of the function; the only exception is a `const&`/`auto&` binding aliasing an existing
object (can't hoist without pointer indirection / dynamic alloc). Plain scalars must be hoisted.

**§A Interrupt core (1.5):** new members near `m_currTask`:
`ActiveTask m_stashedTask{}; bool m_hasStashed{false}; bool m_interruptPending{false};
const char* m_lastInterruptReason{nullptr};` plus storm state (below).
New method `raiseInterrupt(const char* reason)`: set_velocity(0,0,0,0) hover; if `m_hasActive`
copy `m_currTask`->`m_stashedTask`, set `m_hasStashed`, clear `m_hasActive`; set reason +
`m_interruptPending`; run storm detector; log
`[FMU_NODE_DEBUG] INTERRUPT (reason=%s): stashed=%s escalated=%d hover+reassess`.
Hover-hold: in the idle path (after the `if (m_hasActive){...} return;` block, before the
settle-ticks check) `if (m_hasStashed) m_backend->set_velocity(Vec3{0,0,0}, 0.0f);`.
Clear `m_hasStashed`+`m_interruptPending` in `activateTask` (after `m_hasActive=true`) — the
stash is NEVER auto-resumed by the FMU; the reassess re-issues it.

**§D Interrupt storm / max-retries (6.3 — RE-ADDED by overseer; was wrongly dropped):**
members `u64 m_interruptTimes[kInterruptMaxRetries]{}; u32 m_interruptRingIdx{0};
bool m_interruptEscalated{false};`. O(1) detector in `raiseInterrupt`: compare `now` to the
timestamp N interrupts ago (the ring slot about to be overwritten); if
`oldest!=0 && (now-oldest) <= kInterruptStormWindowMs*1000` -> `m_interruptEscalated=true`.
Reset escalation + zero the ring in `completeCurrent` (a clean completion == the drone escaped).
Escalation surfaces in the prompt (below) telling the model it's in a storm — reason about root
cause, produce a creative escape, don't re-issue the tripping action. **Evasion + task
continuation are model-driven via that enriched prompt, NOT a hardcoded FMU nudge** (the model
owns spatial planning; a blind reflex could worsen an impact). Overseer's intent: the interrupt
must lead to genuine recovery, not just a stop.

**§B Emergency boundary (6.1):** in `controlLoop`, between the LANDING block and the
`if (m_hasActive)` section, **gated to `st == FlightState::FLIGHT`**. `speedNow = norm(od.vel)`,
`boundTrig = kBoundaryBaseM + kBoundaryVelScale*speedNow`; read `snap = m_perception->snapshot()`;
only if `snap && snap->valid && (nowUs()-snap->host_stamp_us) <= kBoundaryMaxSnapshotAgeMs*1000`
(stale depth = unknown, never trip); `nearestM = nearestDepthM(*snap)`; if
`nearestM>0 && nearestM<boundTrig` -> log + `raiseInterrupt("emergency_boundary"); return;`.
Hoist temporaries `f32 speedNow, boundTrig, nearestM;` and reuse `snap`.

**`nearestDepthM()`** (new `static inline` in `detection_query.hpp`, after `detectionByLabel`):
min `median_depth_cm/100` over valid dets; returns `0.0f` when nothing measurable (callers treat
`<=0` as unknown). Loop local `d` hoisted.

**§C APPROACH motion-gate (6.4):** in the APPROACH branch, replace the
`if (tr.range < kApproachStandoffM)` "reached" block: before declaring `approach_ok`, require
nominal motion — if `fabs(od.yawrate) >= kApproachNominalYawrate || fabs(od.vel.z) >=
kApproachNominalVertVel` -> log + `raiseInterrupt("approach_impact"); return;`. Else the existing
hover + `completeCurrent("approach_ok")`. (Root cause: SITL impact read range 1.83 m off the
impact frame while yawrate 6.9 / vertVel -1.75 / alt 0.99->0.02 m in ~1 s -> false success.)

**§ Prompt (fold context in)** — `buildDynamicPrompt`, after the `[PERCEPTION]` block, before
`[EXECUTED COMMAND HISTORY]`: if `m_interruptPending`, append
`[INTERRUPT]\nreason=%s\ninterrupted: %s\n\n` (reason + stashed thought). If
`m_interruptEscalated`, append an `[ESCALATION]` block instructing deeper root-cause reasoning +
a creative escape. Both persist across re-plans (cleared on activate/complete). Interrupt state
is written only on the control thread; `buildDynamicPrompt` runs on the async plan thread — no
cross-thread write race on these fields.

**New constants (destination depends on re-sync step 2):** `kBoundaryBaseM=0.6f`,
`kBoundaryVelScale=0.5f`, `kBoundaryMaxSnapshotAgeMs=500`, `kApproachNominalYawrate=1.0f`,
`kApproachNominalVertVel=0.6f`, `kInterruptMaxRetries=3`, `kInterruptStormWindowMs=5000`.
All first-guess — SITL sweep left to human.

**ROADMAP:** mark 1.5 / 6.1 / 6.3 / 6.4 implemented-pending-SITL (under its lock; re-read first).

### 2. OPEN DESIGN DECISION — resolve BEFORE coding the boundary
`nearestDepthM` over ALL detections cannot tell an *obstacle to avoid* from the *target being
intentionally approached*. **Every SITL scenario runs `WORLD_NAME=default_car` with live YOLO**,
so the car is always in frame and the boundary is armed in every flying test — including runs
where closing on the car IS the goal (`approach`, `override` "find the car, approach it"). Left
as-is, boundary will interrupt legitimate approaches / GO-toward-object missions.
Options to pick from: (a) suspend boundary while APPROACH is the active task, or exclude its
target label; (b) arm boundary only above a closing-speed floor; (c) keep `boundTrig` well below
`kApproachStandoffM` (2.0 m). The spec inherited this blind spot. **Recommend (a)+(c).** Ask the
overseer, then add a target-exclusion guard to the §B block accordingly.

### 3. Test blast radius (assessed read-only this session)
Unit tests (`source/llm_to_action/**/test/*.cpp`): only `detection_query_test.cpp` is in scope
(I add `nearestDepthM` to its header) — additive, self-contained, effectively zero risk; **add a
`nearestDepthM` case to it** (my-owned file, no lock). No unit test compiles `fmu_node.hpp` /
`fmu_node_base.hpp`, so the core logic is covered only by the SITL scenarios below.

SITL scenarios (`scripts/test/<feature>/`; most `filter.sh` are grep-milestone + human-confirm,
only `flood`/`battery` auto PASS/FAIL). All fly in `default_car` with live perception:
- `flood` — SAFE (queue-only, no flight; backpressure untouched).
- `approach`, `approach-real` — HIGH: motion-gate flips `APPROACH reached` -> `INTERRUPT
  (approach_impact)` on exactly the frames these target; update their README + milestone grep.
- `override` — MED-HIGH: flying toward the car trips boundary at ~1 m before APPROACH finishes;
  handback re-plan now interacts with my stash/interrupt state.
- `forward`, `cross`, `speed`, `rotate-land`, `land-flare`, `terrain-land`, `battery` — CONDITIONAL
  MED: if the canned path enters the car's boundary radius, the movement/RTH milestone won't
  appear. `battery` RTH-at-20% assertion could be perturbed by an interrupt delaying the drain path.
- `vlm` — LOW: prompt only gains `[INTERRUPT]`/`[ESCALATION]` when an interrupt actually fires.
Resolving the §2 decision (suspend boundary during APPROACH) removes most of the approach/override
breakage. Coordinate the canned-approach assertions with spec-4 (shared harness).

### 4. Not yet done / next-session checklist
- [ ] Re-sync (§0), especially the constants-restructuring destination.
- [ ] Resolve the §2 boundary-vs-target decision with the overseer.
- [ ] Acquire locks (fmu_node.hpp, fmu_node_base.hpp; add rows for the other 3 files); short holds.
- [ ] Implement §0 guideline, §1/§D/§B/§C/§prompt, constants, `nearestDepthM` + its unit-test case.
- [ ] Update ROADMAP (under lock). Release all locks. Append final results to this report.
- [ ] Leave build + SITL constant sweep to the human (no full build here).
