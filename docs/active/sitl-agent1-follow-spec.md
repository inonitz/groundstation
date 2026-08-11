# Agent 1 — FOLLOW verb (Demo A)
**Date: 2026-08-11**


**Mission**: implement a `follow` verb — a position-free visual servo that holds a fixed standoff on a
VLM-chosen target and keeps it centered — and prove it in SITL with a moving target. It is a near-copy
of APPROACH; keep it simple.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + coordination + LOCKS +
commit rules), then `CLAUDE.md`, `docs/code-guidelines.md`, `docs/writing-style.md`. Study the code:
`fmu_node.hpp` APPROACH branch (`792-955`) + `activateTask` (`~1648`) + parser loop (`~1943-1990`);
`source/llm_to_action/perception/detection_query.hpp` (`detectionByLabel:49-81`, `TargetRelative`);
`llm_base.hpp` verb specs + `buildDynamicPrompt` `[PERCEPTION]` block (`~1777-1793`);
`llamaclient.hpp buildPlanGrammar` (`111-132`). Grep `docs/NOTES.md` for approach/orbit/follow.

**Your place in the plan**: demo-critical. Independent — start now. Manual-fly tests need Agent 0's
keyboard fix; until it lands use `ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data:true}"`.

## Design (instance selection = VLM returns an index)

Detections carry no stable id, so resolve the VLM's `target_index` ONCE at activation to a label + bbox
center, then track by nearest-centroid each tick. APPROACH closes to standoff and completes; FOLLOW
holds standoff and never completes. The servo is vision-based (bbox/depth), so it works on the Tello
even though `od.pos` is zero there.

## Build

1. `CmdFollow{ i32 target_index; i32 standoff_cm; i32 speed; }` near `CmdApproach` (`fmu_node.hpp:126`);
   add `CommandID::FOLLOW` to enum (`105-118`), union (`136-158`), id-ctor (`160-181`).
2. Grammar: add `"\"follow\""` to the verb enum in `buildPlanGrammar` (`llamaclient.hpp:111-132`).
3. Prompt: `follow` spec after `approach` in `kSystemPrompt` (`llm_base.hpp:~63`):
   `{"action":"follow","target_index":<int>,"standoff_cm":<int>,"speed":<int>}`. In the `[PERCEPTION]`
   block of `buildDynamicPrompt` (`fmu_node.hpp:~1777`), **add an `index` field to each printed
   detection** so the VLM can reference one.
4. Parser branch `else if (action=="follow")` (`fmu_node.hpp:~1963`).
5. `activateTask` case (`~1648`): resolve `target_index` on `snapshot()` → store `m_followLabel` +
   `m_followLastCenter`; reset lost timers.
6. New matcher in `detection_query.hpp`: `detectionNearestCenter(snap,label,lastCenterPx,cam,now)` —
   among label matches pick the bbox nearest `lastCenterPx`; back-project to `TargetRelative`.
7. Control branch after APPROACH (`~955`): snapshot → `detectionNearestCenter` → update
   `m_followLastCenter`; `yawRate=-kApproachYawGain*errX`, `vUp=-kApproachVertGain*errY`,
   `spF=kFollowFwdGain*(range-standoff)` (ALLOW negative — back off when too close);
   `flu_to_enu({spF,0,vUp}, od.yaw)` → `set_velocity`. On target-lost: coast-then-hover (reuse
   APPROACH's lost logic) and **never `completeCurrent`** — FOLLOW runs until re-assess/stop.
8. Constants `kFollowStandoffM / kFollowFwdGain / kFollowLostTimeoutMs` (`fmu_node_base.hpp`), reuse
   `kApproachYawGain`/`kApproachVertGain`; add `followStandoffM` to `drone_config.hpp` + `config/*.yaml`.
9. **Moving-target world**: add a simple Gazebo mover (a person/box translating left-right or randomly
   within a cone) to a SITL world for testing.

## Tests (manual-verify OK; automated nice-to-have)

- Target moves → drone follows, holds standoff, keeps it centered (errX/errY → 0), backs off when close.
- You fly the drone manually → it re-centers on a static target.
- Debug FOLLOW ENTIRELY here (not in the dashboard agent's scope).
Run via `scripts/test/SITL/<your-scenario>/run.sh` (paths fixed by manager). Grammar already enforces
`follow` as a valid verb once you add it to the enum.

## Locks (docs/LOCKS.md — acquire before editing, release right after)

`fmu_node.hpp`, `fmu_node_base.hpp`, `llm_base.hpp`, `llamaclient.hpp`, `detection_query.hpp`. New world
files and any new test script are yours alone (no lock).

## Constraints

Concise intentful code, comment only the non-obvious. No git writes — suggest an agent-labeled commit
(`agent1: follow verb + control`) when a unit is done. Prose per `docs/writing-style.md`.

## Report
_(append findings / blockers / decisions below)_
