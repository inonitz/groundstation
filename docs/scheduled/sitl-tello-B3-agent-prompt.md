# Agent prompt — B3: SLAM pose → FMU (Tello position + return-to-start)

Paste this whole file as the task for a fresh agent. It has no memory of any prior session — everything
it needs is below or in the referenced spec.

## Before you start — check this is actually ready

This task is gated on **B1 Task 5** (does stella_vslam actually track in SITL — see
`docs/active/sitl-B1-task5-agent-prompt.md`). Check
`docs/closed/sitl-2026-08-10-spec-B1-stella-vslam-sitl-bringup.md`'s Status line before starting (moved to `closed/` once its content was absorbed into `docs/active/sitl-B1-task5-agent-prompt.md`, but its Status line is still the live record of where Task 5 stands):
- If it still says Task 5 open / no verdict recorded: **you can still do the code-writing steps below**
  (they don't need live SLAM data), but the final SITL acceptance test (return-to-start driven by real
  `slam/pose`) can't run yet — stop after the code + the synthetic sanity-check test, and say so plainly
  in your report rather than skipping or faking the live test.
- If it says B1 tracking failed: still write the code (it's needed regardless, and B4's fallback doesn't
  make this dead work), but flag in your report that the live acceptance test has no path to pass yet.
- If it says B1 passed with real numbers: do everything below including the live SITL test.

## Your task

The Tello's x/y position is a **literal hardcoded zero** today — not a drifting estimate, an actual
constant (`tello_backend.cpp:154`: `od.pos = { 0.0f, 0.0f, height }`). Make it real by feeding
`slam/pose` in, and give the drone a working return-to-start.

## Key facts (verified against this checkout 2026-08-09 — don't re-derive these, they're already checked)

- **`TelloBackend` is ROS-free by design** — it cannot subscribe to `slam/pose` itself.
  `make_active_backend()` in `active_backend.hpp:26-29` explicitly discards the node/callback-group args
  for Tello (`(void)node; (void)cbg;`). This means real new plumbing: (a) a `slam/pose` subscription in
  `FmuNode` itself (`fmu_node.hpp` — this file is locked, see below), and (b) a new setter on
  `TelloBackend`, e.g. `set_external_pose(f32 x, f32 y, f32 yaw)`, that the FMU's subscription callback
  calls. This is not "just wire a topic" — it's cross-file plumbing.
- **`returnToOrigin()` already exists and needs zero changes to serve as return-to-start.**
  `fmu_node.hpp:1155-1177` (currently called from the battery-RTH failsafe path) works purely off
  `m_backend->odometry()`'s `pos`/`yaw`. Once your setter makes `od.pos.x/y` real, call this function
  directly for B3's return-to-start — do not write new fly-home logic.
- **No existing fallback to sanity-check pose against** — because position was always zero, there's no
  dead-reckoning estimate to compare an incoming `slam/pose` reading to. This means a sanity/bounds check
  on the incoming pose (reject an implausible jump) is the *only* guard against a bad SLAM reading
  corrupting `od.pos` — treat this as required, not optional polish.
- **ToF is parsed but discarded** — `TelloState` (`tello_backend_base.hpp:94-103`) has a `tof` (cm) field;
  `stateLoop()` (`tello_backend.cpp:171`) only stores `st.h` (baro) into `m_heightCm`, `st.tof` is dropped.
  Add an `m_tof` atomic + store it in `stateLoop()` + a getter — this is prep for a scale anchor, not
  fully wiring scale correction (out of scope here, just make the value available).

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

## Files

- Modify: `source/llm_to_action/fmu/fmu_node.hpp` (new `slam/pose` subscription, wiring to
  `set_external_pose`, plus a call to `returnToOrigin()` on whatever trigger the spec/your judgment
  decides for return-to-start — check how the existing battery-RTH path triggers it as precedent).
- Modify: `source/llm_to_action/tello_backend/tello_backend.hpp` (`set_external_pose` declaration, `m_tof`
  member).
- Modify: `source/llm_to_action/tello_backend/tello_backend.cpp` (`set_external_pose` implementation,
  `stateLoop()` storing `st.tof`).

## Steps

1. Take the `docs/LOCKS.md` entry for the four files above.
2. Add `set_external_pose(f32 x, f32 y, f32 yaw)` to `TelloBackend` — implementation should set the
   backing fields that `odometry_impl()` reads for `pos.x`/`pos.y` (and yaw if applicable — check how yaw
   is currently sourced before assuming it needs to change too).
3. Add the sanity/bounds check: reject a pose update that implies an implausible jump (pick a reasonable
   bound — e.g. max plausible displacement between consecutive updates given the Tello's real speed
   envelope, check `tello_backend_base.hpp` for existing velocity constants to ground this
   number, don't invent one arbitrarily).
4. Add `m_tof` atomic + getter to `TelloBackend`; store `st.tof` in `stateLoop()` alongside the existing
   `st.h` handling.
5. Add the `slam/pose` subscription in `fmu_node.hpp`, calling `set_external_pose()` in its callback.
6. Wire return-to-start to call the existing `returnToOrigin()` (`fmu_node.hpp:1155`) — do not duplicate
   its logic.
7. Build:
   ```bash
   cmake --build build/release/tello --target all -j"$(nproc)"
   ```
   (or whichever Tello build tree already exists from B4 — check `rtk ls build/release/` first rather
   than assuming the path.)
8. Release the `docs/LOCKS.md` entry once your edits are done (even if tests are still pending).

## Tests

- **[if B1 has a passing verdict] Live SITL test:** run a canned return-to-start scenario driven by real
  `slam/pose` from B1's pipeline (`scripts/test/slam/run.sh` or a variant), assert the drone returns to
  origin within a reasonable tolerance using sim ground truth — same shape of assertion as the existing
  battery-RTH test's return-distance check (find that test and mirror its structure, don't invent a new
  pattern).
- **[always, regardless of B1's status] Synthetic sanity-check test:** feed `set_external_pose()` a wild,
  implausible jump directly (bypassing SLAM entirely — just call the setter in a small standalone test) and
  assert it's rejected, `od.pos` unchanged. This doesn't need B1 or live SLAM at all — write and run it
  either way.

## Report back (required)

1. Confirm the four-file lock was taken and released in `docs/LOCKS.md`.
2. Whether B1 had a passing verdict at the time you ran — and therefore whether the live SITL test ran,
   and its result if so.
3. The synthetic sanity-check test result — this should always be reportable regardless of B1's status.
4. Build confirmation (exact binary path).
5. Anything you found that contradicts the "Key facts" section above — if `returnToOrigin()` or the
   `TelloBackend` ROS-free assumption turned out stale by the time you're running this, say so explicitly,
   don't silently work around it.
6. Suggested commit command(s) for the human.
