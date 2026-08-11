# Audit — git, docs, and code state as of 2026-08-10

> **Status update (later pass, 2026-08-10):** every item in this report's "Suggested cleanup" list
> is now done — `feature-calibrate-slam` merged (`a2f1626`), ROADMAP 7.1 updated, the B1 closed-spec
> status line fixed, A3's stale-line-number warning added to the spec itself, `2026-08-08-poc-status.html`
> moved to `closed/`, `all_panes.txt` gone, `.gitignore` has `__pycache__/`/`*.py[cod]`, and
> `docs/LOCKS.md` refreshed. **The headline SLAM-collapse finding below is also superseded, and its
> framing was too strong:** `docs/NOTES.md`'s "colors showcase" 2026-08-10 update traced the same
> `slam_check.log` collapse to the drone never taking off (`altENU` never exceeded 0.06m, a
> takeoff-ordering plan bug), not a SLAM/world problem — it explicitly says re-run before drawing
> any SLAM conclusion from this data. Kept below for the git/doc hygiene findings, which still hold.

Read-only investigation, no files changed. Covers everything committed since this session's start
(`b50f286` → `be3db5d`, 7 commits) plus the current uncommitted working tree. Findings ranked by
what actually matters, not file order.

## Headline: the one real technical finding nobody's captured yet

**`scripts/test/colors/slam_check.log` shows stella_vslam collapsed (not tracking) for the entire
run — 215 of 287 lines are `note=collapsed-fit`, 0 are `note=ok`.** `spread_ratio` sits at 0.04-0.05
throughout (healthy is "near 1.0"; the comparator's own documented threshold for "not actually
tracking" is "near 0, note=collapsed-fit — drift_m reads deceptively small here, ignore it"). This
is a real SLAM failure in the new lightweight "colors" showcase world, not a fluke reading.

Compare against the real B1 verification (`docs/NOTES.md`, "B1 stella_vslam live SITL verification +
OpenMP fix"): the `cross` maneuver in `rubicon_targets` got a marginal-but-real 2 PASS / 1 FAIL
(`spread_ratio` 0.60-0.86 on passes) after the OpenMP fix. The colors run is categorically worse —
100% collapsed, not "marginal." Plausible cause from reading the flight log: the APPROACH commands in
that run were tiny (`cmdVelENU` ~0.03-0.09 m/s, repeatedly cycling "target lost/reacquired") — SLAM
needs real parallax motion to triangulate, and a near-stationary hover-ish flight starves it. That's
a hypothesis from the data, not something I root-caused by reading the SLAM code itself.

**This matters because:** the colors world exists specifically to dodge the 9.15 VRAM constraint for
field showcases, and if SLAM can't track in it, that world is only safe for the pure-vision
(YOLO+depth) showcase track, not anything claiming SLAM. Nobody has written this down — not
`docs/NOTES.md`'s own "colors showcase" entry (which says "Not yet run," written *before* this log was
produced), not `docs/ROADMAP.md`. Worth a deliberate follow-up run before this world is used to
demo anything SLAM-adjacent.

## Docs that are now stale or misleading

1. **`docs/ROADMAP.md` 7.1 ("SLAM/VIO pose... `[~]` scaffolding only") understates what actually
   happened.** Real live SITL tracking verification ran (multiple trials, real root-cause fix
   for a threading bug, honest marginal-pass numbers) — that's not "scaffolding," that's a
   completed spike with a known reliability ceiling. The ROADMAP line hasn't been touched to
   reflect it (checked: only 9.6/9.15/1.1.6/1.1.7/3.x lines got updated this session, 7.1 didn't).

2. **`docs/closed/sitl-2026-08-10-spec-B1-stella-vslam-sitl-bringup.md`'s Status line** (which I
   wrote in an earlier turn this session) says *"Task 5 (live SITL run...) is the one open item"* —
   that's now wrong. Task 5 ran and is documented in `docs/NOTES.md`. This is exactly the kind of
   drift that happens when a status line lives in a file nobody's obligated to revisit — I'm
   flagging my own stale claim here, not just other people's.

3. **`docs/scheduled/sitl-2026-08-10-spec-A3-voice-interrupt-and-termination.md`'s cited
   `fmu_node.hpp` line numbers are stale** (file grew from whatever it was to 2109 lines across
   today's edits). This is already self-flagged in `docs/NOTES.md`'s "ASR status check" entry —
   good that it was caught — but the warning lives only in NOTES.md, not in the spec file itself,
   so whoever opens the spec first won't see it. Worth a one-line addition to the spec directly.

4. **Two `poc-status.html` files coexist in `docs/active/`** (`2026-08-08-poc-status.html`,
   `2026-08-10-poc-status.html`). Diffed them (tags stripped): materially different, the 08-10 one is
   clearly the successor (1185 vs 1437 words, restructured). The 08-08 one is dead weight now, same
   situation as the manager-handoff pair from earlier this session — should move to `closed/`.

5. **`docs/active/2026-08-09-manager-session-handoff.md` is aging** — a lot has landed since it was
   written (everything in this report). Not yet actively wrong, but a new session cold-starting from
   it will be missing today's entire B-track landing. Not urgent, but next handoff should supersede it
   explicitly the way the 08-09 one superseded 08-08's.

## Git / commit hygiene

**The 7 commits since session start are real, substantive, and well-formed** — intent-first
subjects, `|`-separated clauses, ASCII, ending in `Co-Authored-By` where agent-written. No junk
commits, no placeholder work. Specifically landed: A1+B1's build wiring and the agent-prompt
consolidation (`870ac40`), B4's `rx_node.cpp --tello` fix + Tello bring-up scripts (`c2af950`), B2's
calibration tooling (`193d7fb`), a genuinely proper fix for ROADMAP 9.6 — `build.sh`/`build.ps1` now
take a real `<backend>` arg instead of the workaround I'd specified (`e9de4fc`) — a fail-loud harness
fix (`a330b3e`), and the OpenMP root-cause fix for SLAM tracking (`be3db5d`). Branch is in sync with
`origin/feature-llm-driver` (0 ahead/behind).

**Two real hygiene misses:**

- **3 tracked `__pycache__/*.pyc` binaries** (`scripts/tello/__pycache__/*.pyc` x2,
  `scripts/test/slam/__pycache__/*.pyc`), and `.gitignore` still has no `__pycache__/`/`*.pyc` rule
  today. Good news: already caught and fixed on `origin/feature-calibrate-slam` (see below) — not
  yet merged into this branch, so it's still live here.
- **`all_panes.txt` at the repo root, 427KB, untracked.** A stray full tmux-pane capture, not caught
  by any `.gitignore` rule (the existing `captured_*.txt`/`*_log.txt` rules only apply under
  `scripts/test/`). Should be deleted, not committed.
- Minor, already self-corrected: `870ac40` committed `scripts/test/slam/slam_check.log` (a log file),
  `be3db5d` deleted it again and added a `.gitignore` rule for it. Net zero, but a symptom of the
  same underlying gap — log/cache output isn't consistently excluded.

**An unmerged sibling branch carries real hardware fixes.** `origin/feature-calibrate-slam` (2 commits
ahead of the shared `be3db5d` base) has genuine hardware debugging work: a missing SDK keepalive that
was timing out real Tello hardware, an OpenCV/GStreamer-vs-FFMPEG hang risk, a firewall-drop root
cause (container missing `devenv.sh`'s `iptables` setup), and a real perf fix
(`findChessboardCorners` → `findChessboardCornersSB`, ~600x faster). This was reviewed read-only by
whoever's working alongside you tonight, who called it "low-risk, merge soon." I'd affirm that read —
everything else I checked on this branch has been high-quality, and the longer these two branches
diverge the harder that merge gets. This is the most consequential open action item in this whole
report.

**Current uncommitted work is coherent, not broken.** `fmu_node.hpp`/`fmu_node_base.hpp`/
`llamaclient.hpp`/`llm_base.hpp`/`plan_parse.hpp` + its test, `ARCHITECTURE.md`/`NOTES.md`/
`ROADMAP.md` — this is the plan-parse bracket-depth rewrite (with new edge-case tests), grammar-
constrained VLM JSON output, SEARCH return-to-start-on-failure, and a new system-prompt rule about
reading command-history failure statuses. I read the actual diffs, not just the doc claims: the code
matches what the docs say it does. Good WHY-comments, guard-clause style, consistent with
`docs/code-guidelines.md`. Nothing here looks unfinished or contradicts its own documentation.

## Docs folder placement — mostly holds up

The `active`/`scheduled`/`closed` split from earlier this session is still structurally sound:
scheduled correctly holds only genuinely-deferred work (A2/A3/A4/B5), closed correctly holds only
finished specs (A1/B1/B2/B3-code/B4), active correctly holds the in-flight prompts + runbooks. The
staleness issues are all *content* drift inside otherwise-correctly-placed files (see above), not
misplacement.

**One real gap: the "colors" showcase has no spec file and no ROADMAP entry at all.**
`dependencies/rubicon_colors.sdf` + `scripts/test/colors/` exist purely as one `docs/NOTES.md`
paragraph and a working script. Given the SLAM-collapse finding above, this deserves at least a
ROADMAP line (or a note folded into 9.15) so the result doesn't get lost the next time someone reaches
for "colors" as a quick low-VRAM demo world.

## Code-guidelines compliance

Spot-checked the new/changed C++ (`rx_node.cpp`'s `--tello` pipeline switch, the `fmu_node.hpp`
SEARCH-return and VLM-logging changes, `plan_parse.hpp`'s rewrite) against `docs/code-guidelines.md`:
naming, WHY-comments, guard clauses, no-exceptions, explicit `return;` — all consistent, no
violations found. The Python calibration scripts match what I'd specified almost verbatim, including
keeping the "measure resolution from a real frame, don't assume 960x720" logic I'd flagged as
required — good fidelity between the agent prompt and what shipped.

**`docs/LOCKS.md` was not touched by any of today's work**, despite `fmu_node.hpp`/
`fmu_node_base.hpp`/`llm_base.hpp` all being edited repeatedly (including right now, uncommitted).
Every entry in its table still references spec-1/2/3 work from several sessions ago. Not dangerous
today (no real concurrent contention happened), but the file is now actively misleading rather than
neutral — a fresh reader checking it before editing `fmu_node.hpp` would draw conclusions from
stale notes instead of today's real state.

## Cross-check: do the B-track docs match what actually shipped?

| Item | Doc claim | Code reality | Verdict |
|---|---|---|---|
| B1 Tasks 1-4 | build wiring done | `CMakeLists.txt` SLAM option, `publish_rviz_pose()` uncommented, `color_order: BGR` — all present | matches |
| B1 Task 5 | (closed spec says "still open" — stale, see above) | ran, real OpenMP root-cause fix, marginal-pass (2/3) results honestly documented | **doc is stale, code is ahead of it** |
| B2 | scripts written, measure-first logic required | both scripts committed, logic intact, plus real hardware fixes on the sibling branch | matches, exceeds |
| B3 | gated on B1 | no `set_external_pose`, no `slam/pose` subscription anywhere in `fmu_node.hpp` | correctly not started |
| B4 | rx_node platform-aware + build workaround | rx_node fix clean and default-preserving; build.sh got a *real* fix (backend arg), better than the workaround I'd specified | matches, exceeds |

## How far to finishing the POC

ROADMAP tally: **57 `[x]`, 12 `[~]` (partial), 27 `[ ]` (open), 6 `[DEFER]`, 1 dropped** — 103 line
items total. Section 7 ("Being B" — SLAM/OctoMap/A*) is explicitly `[DEFER] horizon` at the top level,
so it doesn't gate the POC; treat sections 1-6/8-9 as the real scope.

**The SITL showcase half is essentially done and proven:** flight core, backend abstraction, VLM
planner, safety/failsafe are all `[x]` or `[~]`-with-the-remainder-being-low-priority-debt; the
15-test SITL suite is green (8.6). This is demo-ready.

**The real-Tello half is the actual remaining POC work, roughly half-through its own plan:**
video pipeline (B4) done, camera calibration tooling (B2) done but not yet run against real hardware,
SLAM tracking works but marginally (2/3 pass rate, SITL-only, untested on real Tello video) and not
yet wired to the Tello backend at all (B3 not started), voice control (A3) not started, stick
calibration (B5) not started. `2.3 TelloBackend` itself is still `[~] first real-hardware` — flown
once, not through the full feature set.

**Straight answer:** if "the POC" means the SITL showcase, it's done modulo the housekeeping above.
If it means real-Tello autonomy with SLAM, you're past the highest-risk unknown (does SLAM track at
all — yes, marginally) but B3, the hardware calibration merge, and a real-camera SLAM test are all
still ahead, plus A3/B5 which are lower-priority. Nothing found in this audit suggests the plan is
wrong or the remaining work is bigger than the docs already say — the gaps are documentation drift,
not surprise scope.

## Suggested cleanup (not done — reporting only, per this task's read-only scope)

- Merge `origin/feature-calibrate-slam` before more calibration work continues (highest-value item).
- Update ROADMAP 7.1 to reflect the real B1 verification result instead of "scaffolding only."
- Fix the B1 closed-spec Status line (my own stale claim).
- Add the stale-line-numbers warning directly into the A3 spec file, not just NOTES.md.
- Move `2026-08-08-poc-status.html` to `closed/`.
- Delete `all_panes.txt`; add `__pycache__/`, `*.pyc` to `.gitignore` (will land automatically via
  the `feature-calibrate-slam` merge, but only for the files it touches — the root `.gitignore` rule
  itself should still be added so it's caught everywhere going forward).
- Give the "colors" world a ROADMAP line or fold it into 9.15, and re-run it deliberately (with more
  translational motion) before trusting it for anything SLAM-related.
- Refresh `docs/LOCKS.md`'s table to reflect today's actual touched files instead of days-old spec-1/2/3 notes.
