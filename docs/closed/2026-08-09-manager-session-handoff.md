# Manager session handoff — 2026-08-09

> **Superseded (2026-08-10):** read `2026-08-10-session-handoff.md` instead. Specs A1-A4/B1-B5 referenced below are stale or done; git state below predates the feature-calibrate-slam merge and tonight's fixes. Kept here for its still-true gotchas (§7) until the next docs/closed/ housekeeping pass.

Cold-start brief for the next overseer session. Read this first, then the docs it points to. It
replaces the stale `2026-08-08-manager-session-handoff.md` (delete that one).

## 0. The one rule that overrides everything

**The human owns the entire git workflow.** Agents run NO git writes — no `add`/staging, no
`commit`, no `push`, no `mv`/`rm`, no `merge`/`rebase`/`reset`/`tag`. Read-only inspection is fine.
When work is ready, SUGGEST the exact git commands in the house style; the human runs them. This is
in `CLAUDE.md` and `docs/code-guidelines.md` and it overrides any skill that says otherwise.

Other standing rules: use the `rtk` wrappers for read/grep/ls/find/git; edit files via Python
heredocs with `assert s.count(old)==1` (native Read/Edit are blocked); keep prose in short sentences
(`docs/writing-style.md`).

## 1. What this project is

Off-board VLM-driven autonomous drone. **The VLM plans; deterministic math executes.** Primary target
is the DJI Tello; PX4 Gazebo SITL is the simulation fallback. Canonical frame is ENU. The heart is a
20 Hz control loop in `source/llm_to_action/fmu/fmu_node.hpp`.

Source of truth for goals and status: **`docs/ROADMAP.md`** (re-read it fresh; do not trust a cached
summary). Architecture: `docs/ARCHITECTURE.md` (living spec, refreshed 2026-08-09). Decision log:
`docs/NOTES.md`. Visual status: `docs/active/2026-08-09-poc-status.html`.

## 2. Where we are right now

**Git: clean and synced.** Everything from this session is committed on `feature-llm-driver`. That
includes the full spec-1 (reactive safety) + spec-2 (ORBIT/SEARCH) feature work, the APPROACH
close-out (dead-reckon finish, quadratic flare, standoff 2.5 m, canned tests in the `empty` world),
the governance rule, the ARCHITECTURE refresh, and all of tomorrow's spec files.

**SITL: 20/20 scenarios green.** The showcase capability set is feature-complete. See the ROADMAP
test matrix.

**The blocker for real flight is position.** The Tello reports no X/Y (`docs/tello_backend_notes.md`
confirms — 16-field state, velocity only). Anything that flies *to a place* needs SLAM, which is
scaffold-only.

## 3. The plan — two branches

- **`feature-llm-driver` — the guaranteed SITL showcase.** Specs **A1–A4**. Lock this down first.
- **`feature-slam-tello` — new branch, cut from the showcase after its state is confirmed.** The
  risky hardware + SLAM path. Specs **B1–B5**.

Full manifest, dependency table, and parallelization notes:
**`docs/scheduled/2026-08-10-tomorrow-plan-index.md`**. Narrative plan:
`docs/active/2026-08-09-slam-tello-bringup.md`.

### Spec files (each = one feature-commit for one agent), in `docs/scheduled/`
- **A1** live sandbox + headless runner + capture-to-file — *do first; unblocks headless CI.*
- **A2** observability (VLM view, depth colormap, prompt/response log).
- **A3** voice interrupt + mission termination — *touches `fmu_node.hpp`.*
- **A4** showcase demos S1/S2/S3.
- **B1** stella_vslam SITL bring-up — *the risk spike.*
- **B2** Tello camera calibration (operator, ground).
- **B3** slam pose → FMU — *gated on B1; touches `fmu_node.hpp`.*
- **B4** Tello bring-up + position-free demos T1/T2 — *guaranteed hardware deliverable.*
- **B5** stick→m/s calibration + wind correction.

**Contention:** only A3 and B3 touch `fmu_node.hpp`, and they are on different branches, so agents
never collide. Everything else is new files or a separate node. Follow `docs/LOCKS.md` for any FMU
edit: take the lock right before, release right after.

## 4. Is it realistic in ~14 hours? No — and that is the plan.

- **Commit-worthy tomorrow:** the SITL showcase (A1–A4) and a first **position-free** Tello flight
  (B4). Plumbing on a proven base; agents parallelize; your SITL/hardware testing is the serial cost.
- **A spike, not a commitment:** B1 (does stella track?) is unbounded. Timebox it.
- **Will not land reliably:** B3 + B5 — SLAM-wired Tello autonomy. Hardware iteration does not
  compress with more agents.

Sequence the day so the showcase is safe by ~hour 8, then spend the rest on the SLAM spike with B4 as
the clean fallback. **Do not gate the showcase on SLAM.**

## 5. Status vs the stated goals and roadmap

ROOT goal: off-board VLM drone, Tello primary / SITL fallback, "VLM plans, deterministic math
executes." Block by block (see ROADMAP for detail):

- **1 Flight core** — done. GO, ROTATE, TAKEOFF, LAND, STOP, ORBIT, SEARCH; interrupt reflex; SPSC
  queue + backpressure. All SITL-verified.
- **2 Backends** — GenericBackend + PX4 done; **Tello partial** — telemetry/camera/odometry live on
  hardware (2026-08-06), but no X/Y and no stick calibration.
- **3 VLM planner** — done. Event-driven, async, tolerant extraction, dynamic prompt.
- **4 Perception** — integrated and running, but **both seg and depth miss the perf target** on this
  CPU. Works; slow.
- **5 Visual servoing** — APPROACH done and SITL-verified (dead-reckon + motion-gate). Live-YOLO GO
  and safe-land deferred.
- **6 Safety / failsafe** — done. Boundary, storm escalation, battery RTH/land, reversible override,
  motion-gate. All SITL-verified.
- **7 SLAM / "Being B"** — **scaffold only.** This is the dominant gap and the whole Tello-autonomy
  risk. stella_vslam compiles and links but has never been brought up (B1).
- **8 Sim / tooling** — done; the live-system sandbox is the one missing piece (A1).
- **9 Debt** — tracked. Runtime config (9.14), AGL landing (9.12), GO drift (9.13), perception perf
  (4.1.8), fmu_node.hpp refactor. None block the showcase.

Headline: **SITL is demonstrable end-to-end; Tello autonomy is blocked on position (SLAM). The
position-free Tello demo is reachable now.**

## 6. Which tests get the human out of the loop

- **Fully automatable, headless SITL** (once A1's capture-to-file lands): every canned scenario — the
  20 existing, plus A3 (`--canned-voice` / `--canned-complete`), A4 (S1/S2 state-traces), B1
  (tracking-health vs EKF2 ground truth), B3 (return-to-start vs ground truth), A2 (topic-rate + log
  checks). Sim ground truth is what makes even SLAM assertable.
- **Desk-automatable without flying:** B4/B5 parser, odometry, latency, stick→m/s curve — via a
  recorded-flight replay fixture (ROADMAP 2.3.6).
- **Human stays in the loop:** real Tello flights, and VLM *plan quality* on free-flight runs. The
  state-trace is asserted; the model's judgment is not.

Every spec file carries a `## Tests to create` section tagging `[AUTO]` vs `[HUMAN]`.

## 7. Gotchas the next manager should know

- **tmux capture fragility:** tests scrape scrollback and drop events under load — the cause of "false
  FAIL on rerun." A1 fixes it by teeing FMU stdout to a file. Prioritize A1.
- **Tello bring-up gremlins** (`docs/tello_backend_notes.md`): UDP bind collision (needs
  `SO_REUSEADDR`), the `ReceiveResponse` timeout, and the 15 s auto-land unless `rc` streams at
  ~30 Hz. Batteries last ~10–13 min — charge several.
- **Old visual docs are superseded:** `2026-08-07-task-map.html`, `2026-08-08-roadmap-progress.html`,
  `2026-08-08-status-map.html`, and the stale `2026-08-08-manager-session-handoff.md`. The current
  status doc is `2026-08-09-poc-status.html`. Recommend deleting the superseded ones.
- **Re-verify before branching:** build the current `feature-llm-driver` and re-run the 20 SITL tests
  as a sanity gate before cutting `feature-slam-tello`, so the new branch starts from known-green.

## 8. First actions for the new manager

1. Read `docs/ROADMAP.md` and `docs/scheduled/2026-08-10-tomorrow-plan-index.md`.
2. Sanity gate: confirm the branch builds and the 20 SITL tests are green (suggest the human runs it,
   or use the sandbox once A1 exists).
3. Dispatch the parallel front: **A1** (unblocks CI), **B1** (the SLAM spike — timebox it), **B2**
   (operator calibration, no flight). These have no FMU contention and no cross-dependency.
4. Queue A2/A4 behind A1, and A3 as the single serialized FMU edit on the showcase branch.
5. When the human is ready to fly: `docs/active/2026-08-09-poc-status.html` §01 has the Tello runbook.
