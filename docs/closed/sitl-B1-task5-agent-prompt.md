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

**Nobody has run this against real stella_vslam output yet. That's this task.**

## Everything you need is below — you should not need to open another file for orientation

### What this system is

Groundstation is an off-board autonomous flight stack for small drones (primary target: DJI
Tello; PX4 SITL in Gazebo as the simulation fallback). The aircraft is a dumb peripheral that
only streams H.264 video and telemetry over the local network; all perception, planning, and
control run on a ground-station computer. Control philosophy: **the VLM plans, deterministic
math executes.** A local Vision-Language Model (Qwen3-VL via `llama-server`) returns a JSON
plan of discrete verbs (`takeoff`/`go`/`rotate`/`land`/`stop`/`approach`, and `orbit`/`search`);
a deterministic 20Hz control loop executes one task at a time and streams setpoints through a
~100Hz offboard publisher. It is never in the per-command completion loop.

Tech stack: C++17, CMake+Ninja, dependency fetch via CPM; ROS2 Humble; Qwen3-VL local
`llama-server`; YOLO detection + metric depth (OpenCV/cv_bridge); Whisper/Sherpa ASR; GStreamer
(H.264/UDP) video transport; PX4 (`px4_msgs`) and DJI Tello (`ctello`) flight controllers.

The two flight controllers sit behind a compile-time backend interface (CRTP,
`GenericBackend<Derived>`, no virtual dispatch), selected at configure time, producing one FMU
binary per backend. Canonical world frame is **ENU**; PX4 speaks **NED** on the wire, Tello uses
**FLU** stick commands — each backend converts internally.

### Code style — `docs/code-guidelines.md`, condensed (the real house rule, not a suggestion)

**Design priorities, in order: simplicity, human readability, performance.** KISS (simplest
design for the actual problem) and YAGNI (build what's needed now, not what might be needed
later) govern every decision. Practical file-size ceiling: ~2000 LOC is unreviewable as one
unit, ~400 LOC is the practical review ceiling, ~150-200 LOC is the preferred target for one
file/unit — not a hard rule, use judgment.

**Naming:** Types/classes `PascalCase`. Public methods `camelCase`. Internal/OS-facing helper
functions may be `PascalCase` too — match what's already in the file. C API functions
`snake_case` or prefix+PascalCase. Member variables `m_camelCase`; prefix letters compose:
`m`=member, `b`=boolean, `k`=constant (`mb_translateEnglish`, `mk_ChannelCount`). Non-member
constants `kPascalCase`. Macros `ALL_CAPS`. Fixed-width types `u8/u16/u32/u64/i8.../f32/f64`
(from util2) OR standard `uint32_t`/`int8_t` — match whichever the surrounding project already
uses, don't introduce util2 aliases into code that doesn't already pull util2.

**Structure/idioms:** explicit `return;` at the end of void functions even when redundant.
Debug logging via raw `fprintf(stderr/stdout, "[TAG] ...\n", ...)` or `RCLCPP_INFO/WARN/ERROR`
with bracketed subsystem tags — not an abstracted logger. WHY-comments only (non-obvious
reasoning), never WHAT-comments. No exceptions — propagate errors via status/error codes; fatal
invariant failures log then `std::abort()`. No virtual calls/dynamic dispatch in the runtime
path — static polymorphism or explicit tagged dispatch instead. Guard clauses over nesting (bail
early on the unlikely/exit condition). Hoist loop-body locals to the top of the function (except
a `const&`/`auto&` alias binding, which stays in the loop). Don't strip existing commented-out
code you didn't just write — this codebase leaves it in deliberately; ask first if you think it
should go.

**Formatting:** tabs for indentation, spaces for alignment. Column limit ~90-95 chars, wrap
manually past that. Pointers/refs left-aligned (`T* x`). `if (x)` has a space before `(`;
function calls don't (`func(x)`).

**CMake, if you touch a `CMakeLists.txt`:** `OPTION()` flags prefixed by project name. No
`GLOB` — explicit `set()` source lists. Libraries get a namespaced alias
(`NAMESPACE::Target ALIAS project_name`). Use the existing `safe_cpm_add_package(...)` wrapper
for new dependencies, not raw `FetchContent`.

### Git and commits — the repo-wide rule (`code-guidelines.md`'s "Review & commits")

**You run NO git writes.** No `add`/staging, `commit`, `push`, `mv`, `rm`, `merge`/`rebase`/
`reset`. Read-only git (`status`/`log`/`diff`/`show`) is fine. When your work is ready, END YOUR
REPORT with the exact git command(s) for the human to run — never run them yourself. This
overrides anything else that might suggest otherwise.

**Commit message house style**, for the command you suggest: one subject line stating INTENT —
what the change achieves, not a file-by-file recap; the diff already shows the code, the message
says why. Separate distinct logical changes with ` | ` (space-pipe-space), each clause
imperative and self-contained. ASCII only — no em-dashes/arrows/smart quotes, spell them out
(`->`, plain quotes). End with `Co-Authored-By: Claude <noreply@anthropic.com>` on its own line.

Good: `Give the drone a battery failsafe that outranks the model and the pilot | Keep a runaway
plan from growing the command queue unbounded`
Bad (recaps the diff instead of stating intent): `Modified fmu_node.hpp to add
batteryFailsafeTick(), changed enqueue to try_enqueue, added constants to fmu_node_base.hpp`

### Change-impact analysis — required in your final report

State plainly: what existing behavior this changes (or "additive only" — a valid answer, say
it); whether it breaks that behavior; which tests re-run as-is (the regression gate) vs. which
get rewritten (a rewritten test means behavior changed — flag that loudly, don't quietly edit a
test to match new code); which tests are genuinely new. A small table beats paragraphs.

### File-lock protocol — `docs/LOCKS.md` (only matters if this task's Files section lists a
locked file; the live table can have changed since this was written, check it fresh)

Before editing any file in the Locks table: if its `holder` isn't `FREE` and isn't you, don't
edit it — do other work, or stop and report `blocked on <file> held by <holder>`. To acquire:
set `holder` to your session id + `since` to the current UTC time, save `LOCKS.md` first, then
edit the source file. To release: the moment you're done, set `holder` back to `FREE`, clear
`since`, one-line summary in `notes`. Keep holds short — acquire right before the edit, release
right after. Files only you create (new scripts nobody else touches) need no lock.

### Writing style — `docs/writing-style.md`, in full (applies to your report and any prose you write)

Write prose the reader can follow on the first pass. Keep sentences short, one idea each, each
leading into the next. Cut parentheticals — give that content its own sentence, or drop it.
Don't reach for bullet points to avoid writing a clear sentence — fix the sentence itself.

### Tool access — repo-enforced, not optional

Native `Read`/`Grep`/`Glob`/`View`/`Echo` are denied by this repo's settings. Use `rtk read`/
`rtk grep`/`rtk ls`/`rtk find`/`rtk git` via Bash instead. To edit an existing file: native
`Edit` requires a prior native `Read`, which is denied — use a Python heredoc instead (read the
file's text in Python, `assert s.count(old) == 1`, replace, write back). Before each step, pick
the right tool deliberately — LSP (`goToDefinition`/`findReferences`) for C++ symbol
navigation, not text grep by default.

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
