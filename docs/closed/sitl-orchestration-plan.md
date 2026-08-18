# Orchestration Plan — hat-follow / Tello demo push (REQUIRED reading for all agents)
**Date: 2026-08-11**


**Deadline: Wednesday evening (2026-08-12). Critical work built AND tested today.**

Every agent (0–5) MUST read this whole file before starting — it is the shared context. Your own
detailed spec is `docs/active/sitl-agentN-*-spec.md`. The human is overseer + Agent 0; one Claude
session (manager) coordinates. Agents run as separate Claude tabs on this same checkout.

## What this push is

The VLM takeoff-grammar fix landed (done, uncommitted). Everything else derailed; this splits the
remaining work into general, end-to-end-owned tasks. Demo A = "identify the person wearing the hat and
follow them in place." The **SITL** hat-follow demo needs no SLAM (PX4 EKF gives position). The
**Tello** demo needs SLAM localization + minimum recovery.

## Agent roster & ownership

| Agent | Owner | Task (build + test end-to-end) | Primary files |
|---|---|---|---|
| **0** | human | Physical Tello bring-up; keyboard override fix; whole-airframe drift characterization | `fmu_node.hpp` (`keyCallback`), `scripts/tello/README.md` |
| **1** | agent | FOLLOW verb + a moving-target SITL world; debug FOLLOW here | `fmu_node.hpp`, `detection_query.hpp`, `llm_base.hpp`, `llamaclient.hpp`, `fmu_node_base.hpp`, `drone_config.hpp`, `config/*.yaml`, new world |
| **2** | agent+human | Lean dashboard (SSE/MJPEG) + 320×240 downscale | new `scripts/dashboard/*`, `fmu_node.hpp` (resize + `/fmu/vlm_text`), `fmu_node_base.hpp` |
| **3** | agent | QA/cleanups: YOLO image-quality test, P1 disarm verify, prompt-trim→ROADMAP, rotate→ROADMAP; later PX4-SLAM safety | test scripts, `docs/ROADMAP.md`, `docs/NOTES.md` |
| **4** | agent+human | SLAM camera calibration (manual) | `dependencies/stella_config_tello.yaml`, `scripts/tello/` calib |
| **5** | agent+human | SLAM impl: stella+Tello bring-up, measure, stabilization test, DR+fusion+recovery | `source/slam/slam2.hpp`, `tello_backend.*`, new stabilization test |

## Dependency & sequencing

- Agent 0's keyboard fix unblocks manual flying → Agents 1 & 5 need it (workaround until then:
  `ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data:true}"`).
- Agent 4 calibration → Agent 5 C1 → C1 go/no-go gates Agent 5 C2/C3.
- Agent 5 SLAM landing → Agent 3's PX4-path safety check.
- `fmu_node.hpp` is edited by Agents 0, 1, 2 — serialize via `docs/LOCKS.md`.
- Start now in parallel: Agent 1 (FOLLOW), Agent 2 (dashboard), Agent 4 (calibration).

## Coordination — MANDATORY

- **Locks**: follow `docs/LOCKS.md` exactly. Before editing any file listed there, read LOCKS, set
  `holder`=your session id + `since`=UTC, **save LOCKS first**, edit, then release (`holder=FREE`,
  one-line `notes`). Keep holds short; prefer many short holds on `fmu_node.hpp`. New files you alone
  create need no lock. Only the overseer clears someone else's stale lock.
- **No git writes** (CLAUDE.md). When a unit is done, SUGGEST a commit in house style; the human runs
  it. Commits stay **small, atomic, agent-labeled** (e.g. `agent1: follow control branch`) so any unit
  can be reverted without disturbing parallel work.
- **Read first**: `CLAUDE.md` (auto-loaded — RTK wrappers, economy, no git writes),
  `docs/code-guidelines.md`, `docs/writing-style.md`, `docs/project_overview.md`, `docs/ARCHITECTURE.md`
  (your area), `docs/NOTES.md` (grep your topic), `docs/LOCKS.md`, and THIS file.
- **Docs may be stale — trust code over docs** and flag discrepancies (e.g. ARCHITECTURE claims a
  "Simpson's-rule dead-reckoning" Tello driver that does NOT exist in code).
- **Report**: append findings / blockers / decisions to the `## Report` section at the bottom of your
  own spec file. If blocked on a lock: write `blocked on <file> held by <holder>` and pick other work.

## Prerequisite (manager fixes before SITL runs)

`scripts/test/SITL/` move broke paths: `run_all.sh` iterates `scripts/test/<name>` (now
`scripts/test/SITL/<name>`) and scenario `run.sh` files `source ../lib/sim_core.sh` (now `../../lib/`;
`lib/` + `slam/` stayed at `scripts/test/`). Fixed as a setup step.

## Wednesday scope

SITL hat-follow (no SLAM) is the reliable headline; Tello+SLAM (Agents 4/5) is the stretch. Agent 5's
recovery (C3) is the minimum needed for a real Tello "search & fly to the hatted man" run.
