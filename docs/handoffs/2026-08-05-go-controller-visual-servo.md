# Session Handoff — GO controller iteration + pivot to visual servoing

**Date:** 2026-08-05, continuation of the session logged in `HANDOFF-2026-08-05.md`
(that file covers Tasks 1-3 / PX4Backend extraction; this one picks up exactly
where it left off: the GO-spiral bug). **Branch:** `feature-llm-driver`. Caveman
mode active for chat prose; code/commits normal.

**Read `HANDOFF-2026-08-05.md` first if you haven't** — PX4Backend extraction
context (Tasks 1-3 done + flies, Task 4 ENU seam not started) is not repeated
here.

---

## Where we are (one paragraph)

The GO-spiral bug from the prior handoff is functionally fixed: GO now reliably
converges and stops (no runaway, no infinite spiral) on every axis and speed
tested. It went through 5 iterations to get there (see NOTES.md's "GO controller
iteration (2026-08-05, continued)" section for the full blow-by-blow — worth
reading before touching this code again, several plausible-looking fixes made
things WORSE and are documented so they aren't retried). Mid-session the user
reframed the actual goal: **stop tuning point-to-point GO entirely** and instead
redesign GO for visual servoing — when a YOLO-tracked target drives the
movement, recompute the direction to it every iteration from the live
detection, don't convert one detection into a fixed NED waypoint and fly to it
open-loop. That redesign has NOT been started. Session paused here, at the
user's request, to re-read `docs/superpowers/specs/` and `docs/superpowers/plans/`
before writing any more code, so the visual-servoing design lands in the right
place architecturally instead of bolted on.

## What's done this session (landed, working)

- GO controller is now **line-of-sight guidance with cross-track PID**:
  direction frozen at task activation (start->target line), forward speed
  P-decays with remaining along-line distance, a separate term corrects
  perpendicular drift without rotating the forward command. Lives in
  `fmu_node.hpp::controlLoop()`'s `CommandID::GO` branch + `activateTask()`'s
  `CommandID::GO` case. Tunables in `fmu_node_base.hpp`:
  `kGoApproachGainHz` (0.5), `kGoCrossTrackGainHz` (1.0).
- **Momentum-settle dwell** between tasks: `kGoSettleMs` (500ms) in
  `fmu_node_base.hpp`; `completeCurrent()` arms `m_settleTicksRemaining`,
  `controlLoop()` holds zero-velocity and refuses to dequeue the next task
  until it elapses. Fixes residual velocity (esp. TAKEOFF's climb) bleeding
  into the next leg's frozen-direction math.
- **Two new canned test rigs** (no VLM needed), both routed through the real
  `translateToBaseCommands()` path like the original canned plan:
  - `injectCannedCrossPlan()` / `--canned-cross` / `./scripts/simenv_llm.sh cross`
    — forward/left/back/right 1m, each immediately undone (return to start)
    before the next axis. Used to rule out a `flu_to_ned` frame/sign bug.
  - `injectCannedSpeedPlan()` / `--canned-speed` / `./scripts/simenv_llm.sh speed`
    — forward+return at 15cm/s then 80cm/s. Used to check whether wobble scales
    with commanded speed (it doesn't — see NOTES.md, the test itself was also
    flawed: the P-law caps commanded speed around 0.5 m/s for a 1m hop
    regardless of the requested ceiling, so "80cm/s" never really ran there).
  - `scripts/simenv_llm.sh` now takes an optional first arg (`forward` default,
    `cross`, `speed`) selecting which canned plan the FMU binary runs.
- `NOTES.md` has the full iteration history (what was tried, what broke, why)
  under "GO controller iteration (2026-08-05, continued)", plus the visual-
  servoing decision under "Decision: stop tuning point-to-point GO...".

## What's explicitly NOT done / deprioritized (for time, not forgotten)

- `kGoCrossTrackGainHz` (1.0) was never retuned/swept — chosen as a first
  reasonable guess and never revisited once it worked well enough to stop
  runaway/spiral behavior.
- The forward leg (immediately after TAKEOFF) still has the largest path
  wobble of any leg in the cross test, even with the settle dwell. The 500ms
  dwell measurably helped (didn't eliminate) the climb-velocity residual.
  Left as-is because the visual-servoing redesign may obsolete this whole
  code path anyway.
- The speed test's own design flaw (P-law never lets a 1m hop reach a
  requested high cruise speed) was diagnosed but not fixed — not clear it's
  worth fixing given the pivot away from point-to-point GO.
- Task 4 (ENU seam, from the ORIGINAL handoff) — still not started, still the
  last gate per the original plan, still blocked behind whatever the GO
  redesign turns into.
- YOLO/VLM integration — not started. This was the actual ask for "today";
  paused per explicit user instruction to re-read docs first.

## THE PIVOT — visual-servoing GO (not yet designed, this is the next task)

User's direction, verbatim intent: when GO is driven by a YOLO-tracked target,
recompute the direction vector to that target every iteration and keep nudging
toward it, rather than converting one detection into a fixed world-NED point
and flying to it open-loop (which is what current GO does — it takes one FLU
delta at activation and freezes everything from there). Two concrete
requirements from the user:

1. Don't require the drone's own absolute local/global position to stay
   accurate over time to do this — track the **last position at which the
   target was seen** and take small relative nudges toward the current
   detection, instead of depending on a long-lived absolute NED estimate.
2. This sidesteps the local-frame-drift problem raised earlier in the session
   (NED position estimates drift over a long flight with nothing to re-anchor
   them — no GPS, no persistent vision lock yet). A continuously-refreshed
   visual error signal doesn't accumulate that drift the way a one-shot NED
   conversion does, because it's re-anchored to ground truth (the object
   actually in frame) every cycle instead of dead-reckoning from a stale
   estimate.

Why this isn't a rebuild: the reason GO ended up as a **velocity-command**
architecture rather than switching to PX4 native position-setpoint mode
earlier in the session was exactly this — a tick-owned error computation is
the right substrate for later swapping in a live vision error signal, versus
handing the whole trajectory to PX4's internal position controller (which
would need to be re-invoked per detection, fighting its own internal
smoothing). The cross-track guidance law built this session already computes
a fresh command every tick from *some* error signal (currently: distance from
a frozen NED line). The redesign is about swapping what that error is computed
against (live YOLO detection / last-known-detection-relative nudge), not
rebuilding the control loop or the PD/cross-track math itself.

Open design questions for the docs re-read to inform (do not answer these from
memory — read `docs/superpowers/specs/2026-08-04-drone-backend-abstraction-design.md`
and `docs/superpowers/plans/2026-08-04-px4-backend-extraction.md` first):

- Where does target-tracking state (last known detection position/bearing,
  staleness/timeout handling when YOLO loses the target mid-approach) live
  relative to the existing `PX4Backend` / `FMU` split? Is it FMU-side state
  (like `m_targetN` etc. today) or does it need its own component given the
  YOLO/VLM integration that's coming next?
- Does GO need a new `CommandID` / verb distinct from the current point-to-
  point GO, or does point-to-point GO become a degenerate case (single frozen
  detection, no re-nudging) of a more general "track and approach" verb?
- How does this interact with the still-unstarted Task 4 (ENU seam)? Worth
  sequencing one before the other?

## Files touched this session (uncommitted — see git ledger note below)

- Modified: `source/llm_to_action/fmu/fmu_node.hpp` (GO controller rewritten
  through 5 iterations, canned cross/speed plans added, settle-dwell added)
- Modified: `source/llm_to_action/fmu/fmu_node_base.hpp` (`kGoApproachGainHz`,
  `kGoCrossTrackGainHz`, `kGoSettleMs`/`kGoSettleTicks` added; earlier
  transient consts `kGoDampingGain`/`kGoMinApproachSpeedMS` added then
  removed again as those approaches were abandoned)
- Modified: `source/llm_to_action/fmu/fmu_node.cpp` (`--canned-cross`,
  `--canned-speed` argv handling)
- Modified: `scripts/simenv_llm.sh` (`[forward|cross|speed]` plan-mode arg)
- Modified: `NOTES.md` (this session's full iteration log + the pivot decision)
- Untracked (from earlier in the day, still uncommitted, not touched this
  continuation): `docs/superpowers/HANDOFF-2026-08-05.md`,
  `docs/superpowers/git-ledger-2026-08-05.md`, `docs/superpowers/plans/`,
  `source/llm_to_action/px4_backend/`
- `output.txt` — scratch SITL capture, gets overwritten every run, not meant
  to be committed.

## GIT — NOT PERFORMED BY CLAUDE (user rule, still in effect)

Zero git commands executed this session. Nothing staged, nothing committed.
`docs/superpowers/git-ledger-2026-08-05.md` has the ledger format from the
prior session if you want to keep using it — this continuation didn't add
entries to it (no commits were proposed or made either).

## How to rebuild + reproduce

Same as the original handoff:
```bash
# operator builds the llm_to_action_fmu target; Claude does not compile ROS.
cd /root/groundstation
./scripts/simenv_llm.sh              # forward 1m smoke test (default)
./scripts/simenv_llm.sh cross        # forward/left/back/right + return, per axis
./scripts/simenv_llm.sh speed        # forward+return at 15cm/s then 80cm/s
# exit tmux: Ctrl+B then :kill-session
```
Debug logs in `output.txt`: `FMU_NODE_DEBUG` (transitions/verbs, includes
`dirNED` at each GO activation now), `FMU_NODE_DIAGNOSTICS` (heartbeat +
250ms GO block with cmdVelNED/measVelNED). Log lines are tmux-wrapped — unwrap
with `open(f).read().replace('\n','')`-style joining keyed on `[INFO]`/`[WARN]`
prefixes before regexing, or lines look truncated (see any of this session's
analysis scripts for the exact join pattern used).

## Resume checklist (next session, in order)

1. Read `docs/superpowers/specs/2026-08-04-drone-backend-abstraction-design.md`
   and `docs/superpowers/plans/2026-08-04-px4-backend-extraction.md` — this was
   explicitly requested before any more code gets written.
2. Design where visual-servoing target state lives (see "Open design
   questions" above) — likely worth a brainstorm/plan pass given it's a real
   architectural fork, not a bite-sized fix.
3. Implement the visual-servoing GO redesign.
4. Only then: YOLO/VLM integration (today's original ask, deferred for the
   docs re-read).
5. Task 4 (ENU seam) still pending from the original handoff — resequence
   relative to the above as needed.
6. Commit manually (Claude does not run git) once something is
   SITL-verified and the user wants it committed.

## Process reminders that still apply

- Claude does NOT compile ROS; operator compiles + runs, Claude diffs logs.
- Claude does NOT run git; all git ops are the user's.
- No hardcoded ROS I/O — topics/QoS/tuning live in `px4_backend_base.hpp`;
  FMU-only tuning lives in `fmu_node_base.hpp`.
- Systematic-debugging lesson from this session, worth internalizing: verify
  each fix against fresh data before layering the next one. Two of the five
  GO iterations (D-term damping, frozen-direction dead-reckoning) were
  theoretically well-motivated and both turned out wrong or actively harmful
  when checked against actual SITL logs. Don't chain fixes off pure
  derivation — rerun and check the specific symptom every time.
- Bite-sized units, reviewed one before the next; caveman prose, normal code.
