# Agent prompt — B1 Task 5: stella_vslam live SITL verification

Paste this whole file as the task for a fresh agent. It has no memory of any prior session — everything
it needs is below or in the referenced files.

---

## Your task

Answer one question with numbers, not a guess: **does stella_vslam actually track in SITL?**

Tasks 1-4 of the B1 spec are already done in this checkout (uncommitted):
- `CMakeLists.txt` wires `source/slam` behind `GROUNDSTATION_BUILD_SLAM` (default OFF).
- `source/slam/slam2.hpp`'s `publish_rviz_pose()` call is uncommented, publishing `geometry_msgs/msg/PoseStamped` to `slam/pose`.
- `dependencies/stella_config.yaml`'s `color_order` is `BGR` (confirmed correct against the real Gazebo stream).
- `scripts/test/slam/run.sh` launches the full stack (PX4/Gazebo/FMU + stella_vslam node) flying a canned
  cross in a textured world.
- `scripts/test/slam/compare_ground_truth.py` subscribes to `slam/pose` and PX4's
  `/fmu/out/vehicle_odometry`, does a time-aligned comparison, and prints `[SLAM_CHECK]` lines with an
  Umeyama-similarity-fit drift metric (validated against synthetic noise, not yet against a real run).

Full spec, with all grounding and file:line citations: `docs/active/sitl-2026-08-10-spec-B1-stella-vslam-sitl-bringup.md`.

**Nobody has run this against real stella_vslam output yet. That's this task.**

## Standing rules for this repo (read once, applies to every step)

- No git writes — no `add`/`commit`/`push`/`mv`/`rm`. Read-only git (`status`/`diff`/`log`) is fine.
  End your report with suggested commit commands for the human; they run them.
- Native `Read`/`Grep`/`Glob`/`View`/`Echo` are project-denied. Use `rtk read`/`rtk grep`/`rtk ls`/`rtk find`/`rtk git` via Bash.
  To edit a file, native `Edit` requires a prior native `Read`, which is denied — use a Python heredoc instead:
  `python3 -c "..."` reading the file, asserting the old string appears exactly once (`assert s.count(old)==1`), replacing, writing back.
- Before each step, pick the right tool. LSP (`goToDefinition`/`findReferences`) for C++ symbol work, not text grep by default.

## Steps

1. **Reproduce the build** (confirms your checkout matches what's described above — don't skip this):
   ```bash
   rm -rf build/release/slam
   cmake -S . -B build/release/slam -G Ninja -DGROUNDSTATION_BUILD_SLAM=ON \
     -DGROUNDSTATION_BUILD_EXECUTABLE=OFF -DGROUNDSTATION_BUILD_TESTS=OFF \
     -DGROUNDSTATION_BUILD_BENCHMARKS=OFF -DGROUNDSTATION_BUILD_BACKEND_PX4=ON \
     -DBUILD_SHARED_LIBS=1 -DCMAKE_BUILD_TYPE=Release -DGIT_SUBMODULE=ON
   cmake --build build/release/slam --target stella_vslam_monocular -j"$(nproc)"
   ```
   Expected: `build/release/slam/bin/stella_vslam_monocular` exists, ~1.1MB. If this fails, stop — report
   the exact error, don't guess a fix blind.

2. **Static sanity:**
   ```bash
   rtk grep "color_order" dependencies/stella_config.yaml   # expect "BGR"
   bash -n scripts/test/slam/run.sh
   python3 -m py_compile scripts/test/slam/compare_ground_truth.py
   ```

3. **Live run.** This is the actual test:
   ```bash
   cd scripts/test/slam
   ./run.sh
   ```
   It brings up PX4/Gazebo/FMU plus the stella_vslam node in a tmux session, flying a canned cross in a
   textured world, with the comparator running in its own pane printing `[SLAM_CHECK]` lines roughly
   once a second.

4. **When the flight completes**, stop the session the safe way — **do not use `:kill-session` or Ctrl-C**,
   both lose the recorded bag (confirmed empirically this session, see
   `docs/active/sitl-2026-08-09-wave1-testing-runbook.md` if you want the full why). Use:
   ```bash
   ../lib/stop_session.sh
   ```

5. **Read the comparator's own verdict.** On completion it should have printed
   `[SLAM_CHECK_SUMMARY] verdict=PASS` or `verdict=FAIL`. Capture the actual numbers, not just the verdict
   word — `rate`, `tracking_frac`, `spread_ratio`, `drift_m` — from several points across the run, not just
   the last line.

   Field interpretation (from the runbook, use this to sanity-check the verdict yourself, don't just trust it blindly):

   | Field | Healthy | Broken |
   |---|---|---|
   | `rate` | near the camera's real fps (~30Hz) | near 0 → SLAM node isn't publishing |
   | `tracking_frac` | well above 0.5 | near 0 with healthy `rate` → tracker losing lock |
   | `spread_ratio` | near 1.0 | near 0, `note=collapsed-fit` → not actually tracking; `drift_m` reads deceptively small here, ignore it |
   | `drift_m` | small, moving, steady | only trust when `spread_ratio` is healthy |

6. **If it fails** (build breaks, `slam/pose` never publishes, tracking never locks): diagnose using the
   stella_vslam node's own pane output first (config/vocab load errors show there), not guesswork. Fix
   what's clearly broken and re-run. If the failure looks like a deeper tracking-quality problem (not a
   wiring bug), don't try to "fix" tracking quality yourself — report the numbers and stop; that's a
   judgment call for the human, not something to paper over.

7. **If it passes**, also do the rviz sanity check as a check on top of the numbers, not instead of them:
   fixed frame `map`, add `slam/pose` as Pose and `slam/active_cloud_pts`/`slam/local_cloud_pts` as
   PointCloud2 (`scripts/stella_vslam_viz.rviz` has this pre-built). Landmarks should trace the world's
   real geometry, trajectory should be smooth and match the commanded cross, no sudden pose jumps.

## Known gotcha

A hard kill (not a clean `stop_session.sh` or detach) can leave a stray `stella_vslam_monocular` process
running. If a rerun misbehaves for no clear reason, `pgrep -f stella_vslam_monocular` and kill anything
left over before assuming the code itself is broken.

## Report back (required — this is what the human reviews)

State plainly and in this order:
1. **Did stage 1 (build) succeed?** Yes/no, exact command output if no.
2. **Did stage 2 (tracking) succeed?** The actual `[SLAM_CHECK_SUMMARY]` verdict, plus 3-5 representative
   `[SLAM_CHECK]` lines showing the numbers over time (not cherry-picked, a real spread across the run).
3. **rviz observation** — one or two sentences, does it match the healthy criteria above or not.
4. **What this determines:** if tracking passed, B3 (wiring SLAM pose into the Tello backend) is reachable
   next. If it failed, say so plainly — the fallback is B4 (position-free Tello demos), already unblocked
   and running independently.
5. Suggested commit command(s) for the human, covering anything you changed to get this working (if
   nothing needed changing beyond Tasks 1-4 already in the tree, say so explicitly — don't invent a commit
   for no change).
