# docs/ Reorganization — Task-Lifecycle Buckets

**Date:** 2026-08-06
**Status:** WIP — awaiting user double-check of this ticket.
**Scope:** Pure documentation move/reorganization. **No code, spec content, or handoff content was edited** — only files relocated and two index/reference files updated. Everything is a git-tracked rename, fully reversible.

## Why
`docs/` mixed finished, in-progress, and not-started session artifacts across `handoffs/` and `plans/` with no lifecycle signal. This reorg files every task artifact by its state so the master session (and future agents) can see at a glance what is done vs. live vs. queued.

## New layout
```
docs/
  tasks_closed/   finished work (archive)
  tasks_wip/      in-progress, has pending items
  tasks_todo/     not started (plans + queued handoffs)
  specs/          durable design specs (NOT task state — unchanged)
  tello_backend_notes.md   (moved up from reference/)
  README.md       (index updated to match new layout)
  ARCHITECTURE.md / NOTES.md / ROADMAP.md / project_overview.md  (unchanged)
```
`handoffs/`, `plans/`, and `reference/` directories were removed after their files moved out. `closed/` was renamed to `tasks_closed/`.

## Every move (git renames)
| From | To | Bucket rationale |
|---|---|---|
| `closed/2026-08-06-tello-real-world-bringup-telemetry-hardening.md` | `tasks_closed/` (same name) | already closed |
| `handoffs/2026-08-05-git-ledger.md` | `tasks_closed/` | Tasks 1-3 commits landed; ledger is a record of done work |
| `handoffs/2026-08-05-perception-agent-prompt.md` | `tasks_closed/` | perception library was built (now lives in `/root/build_yolo/vision/`) |
| `handoffs/2026-08-05-px4-backend-extraction.md` | `tasks_wip/` | Tasks 1-3 fly; **Task 4 (ENU seam) + GO-spiral fix still open** |
| `handoffs/2026-08-05-go-controller-visual-servo.md` | `tasks_wip/` | GO-spiral fixed; **visual-servoing redesign not started** (paused) |
| `handoffs/2026-08-06-fmu-perception-integration.md` | `tasks_todo/` | ROADMAP block 4.2, the next session's start — not begun |
| `handoffs/2026-08-06-build-yolo-vision-generic-backend-refactor.md` | `tasks_todo/` | explicitly a **Draft**, unstarted future refactor |
| `plans/2026-08-04-px4-backend-extraction.md` | `tasks_todo/` | per directive "plans/* → tasks_todo" (see caveat below) |
| `plans/2026-08-05-perception-library.md` | `tasks_todo/` | per directive (see caveat below) |
| `reference/tello_backend_notes.md` | `docs/tello_backend_notes.md` | the "Tello SDK reference" moved up one level |

## Caveats on the placement — please confirm
1. **`plans/*` → `tasks_todo/` is a blunt move per instruction.** Two nuances the master agent should reconcile:
   - `plans/2026-08-05-perception-library.md` is **effectively done** (the library exists and was benchmarked). It is arguably `tasks_closed`, not `tasks_todo`. Left in `tasks_todo` only because "plans/* → tasks_todo" was the instruction.
   - `plans/2026-08-04-px4-backend-extraction.md` is **partially executed** (Tasks 1-3 done, Task 4 open) — it is really a WIP plan, not a clean todo.
   - If you prefer strict-by-state over strict-by-directive, move perception-library → `tasks_closed` and the px4 extraction plan → `tasks_wip`.
2. **`tasks_wip` vs `tasks_todo` boundary for the px4 chain.** The px4-backend-extraction *handoff* (wip) and its *plan* (todo) now sit in different buckets. Intentional (handoff = live state, plan = the how), but flagging in case you want them together.

## Step 4 — honest read on `docs/specs/*` (LOW CONFIDENCE — header skim only)
**I did not review these in depth. I read only the status blocks / first ~20 lines of each. Everything below needs reverification before being trusted.**

- **`2026-08-04-drone-backend-abstraction-design.md`** — still the source-of-truth for the PX4Backend seam; Tasks 1-3 match it and fly. But its scope block says "no TelloBackend ships here," and a real `source/llm_to_action/tello_backend/` now exists — so **reality has moved past the spec's stated scope**. Task 4 (ENU) still unshipped. *Verdict: core still relevant; scope/status lines are stale.*
- **`2026-08-05-perception-library-design.md`** — the library it specifies was **built**, but the `build-yolo` refactor handoff reports the models **miss their real-time CPU targets** (seg 2.1x, depth 4.6x over). So the spec's **performance assumptions are partly invalidated** and a backend-swap refactor is now planned on top. *Verdict: API/type sections likely still good; performance + model-choice sections need reverification.*
- **`2026-08-05-visual-servoing-approach-design.md`** — forward-looking `APPROACH <label>` design, **gated on Task 4 landing first** (hasn't). Overlaps the `go-controller-visual-servo` WIP handoff. Not implemented. *Verdict: still relevant as a target, but blocked and unverified against the current GO code.*

## Separate inconsistency worth a look (not fixed here)
`tello_backend_notes.md` is titled **"SDK 2.0 verified notes"** and references SDK-2.0-only features (`sn?`, mission pad). The telemetry-hardening session proved the actual drone is a **standard Tello on SDK 1.3** (replies `unknown command` to `sn?`/`sdk?`). The note's *port/parser/frame* content is still correct and 1.3-compatible, but the "SDK 2.0" framing is misleading. Left untouched — flag for the master agent to reconcile alongside NOTES.md/ARCHITECTURE.md.

## Also changed
- **`docs/README.md`** — "Folders" section rewritten to describe `tasks_todo/`/`tasks_wip/`/`tasks_closed/`/`specs/` and the relocated `tello_backend_notes.md`. This was necessary hygiene — the old index listed the now-deleted `plans/`, `handoffs/`, `reference/` folders.

## Deferred / to-verify at handoff (NOT done — added 2026-08-06)
These came up during the reorg discussion. None is a dealbreaker; record and carry forward.

### 1. Latency benchmarks + self-contained I/O tests (important, not blocking)
No measurement exists for how responsively the drone reacts to teleop input. We need:
- **Keypress → drone-response latency** benchmark. Idea: **record a real flight session (the input/command sequence + timestamps) to disk, then replay that sequence in a test** as a deterministic fixture — so the benchmark is repeatable without re-flying.
- **Self-contained "is it working" tests with end-to-end latency** for the two data paths independently:
  - **Odometry**: state packet on the wire → parsed `Odometry` published (measure the lag).
  - **Camera stream**: frame emitted by drone → decoded frame available to the consumer (measure the lag).
- Status: important for trusting the control loop, but **not a dealbreaker** — continue forward and keep this in mind.

### 2. Tello is severely wind-sensitive → add a runtime speed control + stability handling
Physical reality observed: the DJI Tello is **strongly disturbed by wind** — a home fan alone pushes it around, and its **own prop-wash** gives it momentum in weird, non-linear directions. Consequences:
- **`tello_teleop` should expose a runtime-adjustable command velocity.** Bind two keys — **"more speed" / "less speed"** — that step the velocity sent to the drone within a clamped range `min <= v <= max`. Lower speeds are the practical mitigation for the twitchy, non-linear response in confined/indoor air.
- **Drift + real-time stabilization matters more than on SITL.** The control path has to fly the drone **more carefully**: actively **monitor stability** and **send corrective commands to counter erroneous (wind/prop-wash-induced) motion**, not just open-loop-issue the intended move. This ties into the visual-servoing / GO-controller work (`tasks_wip/`) and the odometry that the telemetry fix just unblocked.

## Not done / open
- Nothing committed yet — all changes sit in the working tree for the user's own commit message.
- **Link audit done** — repo-wide scan found only two stale references caused by the move, both fixed: `docs/NOTES.md` (pointed at `handoffs/…build-yolo…` → now `tasks_todo/…`) and the telemetry-hardening doc (pointed at `reference/tello_backend_notes.md` → now `docs/tello_backend_notes.md`). No markdown links referenced the old `plans/`/`handoffs/`/`reference/` folder paths otherwise.
- Confirm the two placement caveats above.

**Hand this ticket + `tasks_closed/2026-08-06-tello-real-world-bringup-telemetry-hardening.md` to the master session.**
