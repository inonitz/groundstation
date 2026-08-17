# Wave 1 testing runbook — A1 (headless SITL runner) + B1 (stella_vslam bring-up)

How to actually run and verify what landed in your checkout this session, not just read the code.
Everything below is uncommitted — this is your review pass before you commit.

## Correction, read this first if you already tried rotate-land

**Don't press Ctrl-C while attached to the tmux session. Detach instead: `Ctrl-B` then `D`.**

While you're attached, Ctrl-C only reaches whichever pane currently has focus — it interrupts that
one process, but the tmux *session* stays alive (other panes, like PX4/Gazebo, are still running).
`run.sh` is blocked inside `tmux attach-session`, which only returns when you detach or the whole
session dies. If it never returns, `run.sh`'s cleanup trap never fires, the bag recorder never gets
its graceful SIGINT, and you end up with exactly what you saw: a `bag_*` directory with no
`metadata.yaml` inside. Confirmed this with an isolated tmux repro before writing it here, not a
guess. Fixed a one-line gap in `sim_core.sh` so this now prints on screen when you attach:
```
[INFO] Attached. When done: press Ctrl-B then D to DETACH (not Ctrl-C) --
[INFO] detaching is what lets this script reach cleanup() and finalize the bag.
```

If you already have a stale `bag_*` directory with no `metadata.yaml`, it's just garbage — delete it
and rerun the test. It's git-ignored either way (`scripts/test/.gitignore`).

### If you use `Ctrl-B` then `:kill-session` instead of detaching

This is a genuinely different code path from plain Ctrl-C, and it does NOT go through `run.sh`'s
cleanup trap at all -- confirmed with real, isolated tests against the actual `ros2 bag record`
binary (not guessed):

- `tmux kill-session` sends `SIGHUP` to every pane's process.
- `ros2 bag record` does not handle `SIGHUP` gracefully -- it dies immediately, with no finalization,
  every time. Verified directly, no tmux involved: `kill -HUP` on a live recorder kills it uncleanly;
  `kill -INT` or `kill -TERM` on the same process finalizes it correctly (writes `metadata.yaml`).
- Because `kill-session` tears down every pane's process more or less at once, there is no reliable
  way for anything running *inside* that pane (a trap, a wrapper script) to intercept it and forward a
  clean `SIGINT` in time -- the pane's own shell and its child both receive the same `SIGHUP`
  simultaneously, and the child (the actual recorder) has no handler for it.

**Bottom line: `:kill-session` will lose the bag, every time, regardless of anything in this
codebase.** This is not a bug introduced by this session's work -- it is `ros2 bag record`'s own
signal-handling behavior. The only fix is procedural: stop the recorder gracefully *before* ending the
session, not as part of ending it.

**If you want to use `:kill-session`,** do this first, in a second terminal (not inside the tmux
session):
```bash
BAGPID=$(pgrep -f "ros2 bag record" | tail -1)   # confirm this is exactly one PID before trusting it
kill -INT "$BAGPID"
# wait until `kill -0 "$BAGPID"` fails (process gone) before touching tmux at all
```
Only once that process is confirmed gone should you `:kill-session`. **Otherwise, detach (`Ctrl-B`
`D`) is the only path this session's own cleanup code actually handles for you** -- it's the safer
default if you don't want to babysit a PID check every time.

**Update: this script now exists.** `scripts/test/lib/stop_session.sh [SESSION_NAME]` (default
`llmsim`) does exactly the check-then-kill sequence above -- finds the live bag recorder, sends it a
real `SIGINT`, waits for it to actually exit, then ends the tmux session. Run it instead of
`:kill-session` directly:
```bash
scripts/test/lib/stop_session.sh
```

## Three more real bugs your testing found (2026-08-09, second pass)

1. **`override` (and `vlm`, `approach-real`) can silently lose their bag.** These three set
   `LAUNCH_VLM=1`, which pushes the pane count high enough that `tmux split-window` can fail with
   "no space for new pane" on a modest terminal -- confirmed from your own `override` run's log. When
   that split fails, `BAG_PANE_ID` ends up empty, `cleanup()`'s bag-stop logic silently no-ops, and
   the recorder never even started. **Fixed:** bag recording in `HEADLESS` mode no longer uses a tmux
   pane at all -- it runs as a plain background process of the script itself, which structurally can't
   hit this. Attended runs still use a pane (confirmed working, no reason to change it).

2. **Bag recording now defaults to OFF for headless runs, ON for attended runs.** Nothing currently
   reads the recorded file automatically -- headless completion detection and B1's comparator both
   poll live topics, not the bag. Recording it by default in unattended runs was pure cost (and, per
   bug 1, actively broken) for zero current payoff. `RECORD_BAG=1` still works as an explicit opt-in
   on a headless run whenever you actually want one to inspect later.

3. **`run_all.sh`'s "PASS=20" was overstating things -- fixed.** 8 of the 20 filters
   (`approach`/`approach-real`/`cross`/`forward`/`speed`/`vlm`/`orbit`/`search`) have no automated
   verdict at all -- they dump a milestone digest and always exit 0. Headless, nobody's there to judge
   them, so their "PASS" was meaningless. `run_all.sh` now **skips these 8 by default**, reported as
   `SKIP (no automated verdict...)` with the exact attended command to run them yourself. Pass
   `--include-unverifiable` to sweep them anyway (hollow verdict, same as before). Also added
   **`--only <scenario>`** for fast single-scenario iteration without touching tmux by hand:
   ```bash
   cd scripts/test && ./run_all.sh --only rotate-land
   ```

4. **4 filters had a genuinely wrong trailing message.** `rotate-land`, `override`, `land-flare`,
   `terrain-land` all compute a real, automated PASS/FAIL from parsed log values -- the old
   `"PASS -- confirm against what you observed"` was leftover boilerplate implying a human still
   needed to judge it. Fixed: these now just print `PASS`. (The other 8 unverifiable filters keep
   language to that effect, honestly, since for those it's still true.)

---

## A1 — SITL harness (`scripts/test/`, `scripts/sandbox/`)

### 1. Baseline — confirm the log tee + bag recording work normally (attached)
```bash
cd scripts/test/rotate-land
./run.sh
```
Watch it fly and land as usual. **When done: run `../lib/stop_session.sh` in a second terminal, or `Ctrl-B` then `D` to detach** (see correction above).
Then:
```bash
cat captured_panes_log.txt        # should contain ROTATE lines -- new log-file tee working
ros2 bag info bag_*/              # should succeed with a nonzero message count
```
If `ros2 bag info` still fails after a proper detach, that's a real bug — stop and report it, don't
just re-run and hope.

### 2. The actual new capability — headless, nobody watching
```bash
cd scripts/test/rotate-land
HEADLESS=1 HEADLESS_TIMEOUT_SECONDS=90 ./run.sh
```
Success: the script returns to your shell **on its own** — no attach at all this time, no detach
needed — once the drone lands. Then:
```bash
tmux ls          # should show no llmsim session (full teardown)
./filter.sh      # should still print PASS, reading the log file
```
If it hangs past 90s, the ground-truth poller isn't seeing PX4's arm/land topics — that's the first
thing to debug.

### 3. Override's scripted trigger (no human at the keyboard)
```bash
cd scripts/test/override
HEADLESS=1 HEADLESS_COMPLETION=fixed HEADLESS_TIMEOUT_SECONDS=60 ./run.sh
./filter.sh
```
Success: `ok engaged x1` and PASS, with nobody touching a key.

### 4. Full matrix
```bash
cd scripts/test
SKIP_HIGH_VRAM=1 ./run_all.sh
```
(`SKIP_HIGH_VRAM=1` skips `vlm`/`approach-real`/`override` — the ~12GiB-VRAM trio, ROADMAP 9.15. Drop
the flag if your machine can take it.)

**Read the result, don't just trust the PASS count.** 8 of the 20 filters (`approach`,
`approach-real`, `cross`, `forward`, `speed`, `vlm`, `orbit`, `search`) are digest-only and **always
exit 0** — pre-existing, not introduced by this work, but it means `PASS=20` isn't 20 real assertions.
Open `scripts/test/run_all_summary.txt` and for those 8, read the actual digest text rather than
trusting the verdict line.

### 5. Sandbox (manual free-flight, recorded)
```bash
cd scripts/sandbox
./run.sh "Take off and orbit the car."
```
Attaches like a normal manual run, plus a bag-recorder pane. Fly it, **then `../../scripts/test/lib/stop_session.sh` (or detach, Ctrl-B D)**, then:
```bash
ros2 bag info bags/<timestamp>/
```
should succeed non-empty.

---

## B1 — stella_vslam bring-up (`source/slam/`, `scripts/test/slam/`)

Build already confirmed independently in your actual checkout (not just the agent's worktree) —
`build/release/slam/bin/stella_vslam_monocular` exists, 1.1MB. To reproduce yourself:
```bash
rm -rf build/release/slam
cmake -S . -B build/release/slam -G Ninja -DGROUNDSTATION_BUILD_SLAM=ON \
  -DGROUNDSTATION_BUILD_EXECUTABLE=OFF -DGROUNDSTATION_BUILD_TESTS=OFF \
  -DGROUNDSTATION_BUILD_BENCHMARKS=OFF -DGROUNDSTATION_BUILD_BACKEND_PX4=ON \
  -DBUILD_SHARED_LIBS=1 -DCMAKE_BUILD_TYPE=Release -DGIT_SUBMODULE=ON
cmake --build build/release/slam --target stella_vslam_monocular -j"$(nproc)"
```

### Static sanity (fast, no flight needed)
```bash
rtk grep "color_order" dependencies/stella_config.yaml   # expect "BGR"
bash -n scripts/test/slam/run.sh
python3 -m py_compile scripts/test/slam/compare_ground_truth.py
```

### The live test — this is the one that actually answers "does it track"
```bash
cd scripts/test/slam
./run.sh
```
Brings up PX4/Gazebo/FMU plus the stella_vslam node in its own pane, flying a canned cross in a
textured world. **When done: `../lib/stop_session.sh`, or detach (Ctrl-B, D) — same rule as above,
this also records a bag.**

Watch the comparator's pane — it prints `[SLAM_CHECK]` lines roughly once a second.

| Field | Healthy | Broken |
|---|---|---|
| `rate` | near the camera's real fps (~30Hz) | near 0 -> SLAM node isn't publishing; check its pane for a config/vocab load error |
| `tracking_frac` | well above 0.5 | near 0 with healthy `rate` -> tracker initializing but losing lock |
| `spread_ratio` | near 1.0 | near 0, `note=collapsed-fit` -> **not actually tracking; ignore `drift_m` when you see this, it reads deceptively small** |
| `drift_m` | small, moving, steady | only trust this when `spread_ratio` is healthy |

On Ctrl-C inside that specific pane (not detach — this is the comparator's own process, fine to
interrupt directly) it prints `[SLAM_CHECK_SUMMARY] verdict=PASS` or `FAIL`.

### Visual check, alongside the numbers (not instead of them)
rviz, fixed frame `map`, add `slam/pose` as Pose and `slam/active_cloud_pts`/`slam/local_cloud_pts`
as PointCloud2 (`scripts/stella_vslam_viz.rviz` has this pre-built):
- Landmarks should trace the world's real geometry, not scatter randomly.
- Trajectory line should be smooth and match the commanded cross, not jagged or frozen.
- No sudden jumps in the pose arrow.

The comparator's numbers are the actual gate. This is a sanity check on top.

### Known gotcha
A hard kill (not a clean detach) can leave a stray `stella_vslam_monocular` process running. If a
rerun misbehaves, `pgrep -f stella_vslam_monocular` and kill anything left over first.

---

## When you're done reviewing

Nothing has been staged or committed. `git status` / `git diff` show the full picture. Suggested
commit messages (house style, from each agent's own handoff) are in the chat above if you want them —
say the word and I'll paste them fresh, or write your own from the diff.
