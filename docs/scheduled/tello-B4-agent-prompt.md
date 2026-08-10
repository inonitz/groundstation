# Agent prompt — B4: Tello bring-up (rx_node fix + launch script)

Paste this whole file as the task for a fresh agent. It has no memory of any prior session — everything
it needs is below or in the referenced spec.

## Your task

Make the real Tello's video actually reach the FMU/VLM, and produce a hardware launch script. This is
the code half of B4 — the human does the actual flying afterward, on their laptop, next to the drone.

## The core problem (read this before touching code)

`source/llm_to_action/gstreamer_udp_cam_rx/rx_node.cpp:24-25` hardcodes an **RTP** gstreamer pipeline
(`udpsrc ... caps="application/x-rtp..." ! rtph264depay ! avdec_h264 ! ...`) — correct for Gazebo's
simulated camera, **wrong for the real Tello**, which sends raw H.264 over UDP port 11111, no RTP framing.
`gstreamer_rx` is one binary shared by both backends (confirmed via its `CMakeLists.txt` — no
`FMU_BACKEND_*` compile definitions reach this target), so this can't be a compile-time `#if` the way
`active_backend.hpp` picks a backend. It needs a **runtime CLI flag** selecting the pipeline string at
startup — this matches the existing convention in this codebase (the FMU binary already takes
`$FMU_CANNED_FLAG` as a runtime mode-selector).

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

### 1. Make `rx_node.cpp` platform-aware

- Read the current pipeline construction in `source/llm_to_action/gstreamer_udp_cam_rx/rx_node.cpp`
  (`rtk read` it fully first — line numbers above are from the 2026-08-09 checkout, confirm they still
  match).
- Add a Tello pipeline variant: `udpsrc port=11111 ! h264parse ! avdec_h264 ! videoconvert !
  video/x-raw,format=BGR ! ...` (no `rtph264depay` — raw H.264, not RTP) — keep the same downstream
  elements/caps the existing PX4 pipeline uses after decode, just swap the source/depay stage.
- Select between the two pipelines via a runtime CLI arg, e.g. `--tello` (absent = existing PX4/Gazebo
  behavior, byte-for-byte unchanged — this must be default-preserving, don't break the 20 existing SITL
  scenarios).
- Build and confirm it still compiles for the default (no-flag) path:
  ```bash
  cmake -S . -B build/release/shared -G Ninja -DGROUNDSTATION_BUILD_EXECUTABLE=ON \
    -DGROUNDSTATION_BUILD_BACKEND_PX4=ON -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=1 \
    -DGIT_SUBMODULE=ON 2>&1 | tail -30
  cmake --build build/release/shared --target all -j"$(nproc)" 2>&1 | tail -60
  ```
  (Use whatever build dir already exists in this checkout if `build/release/shared` isn't it — check
  first with `rtk ls build/release/` rather than assuming.)

### 2. Build a Tello binary (separate tree — `build.sh` can't do this today, don't edit `build.sh`)

`build.sh` unconditionally sets `-DGROUNDSTATION_BUILD_BACKEND_PX4=ON` and never sets
`GROUNDSTATION_BUILD_BACKEND_TELLO` (tracked debt, ROADMAP 9.6 — out of scope here, don't fix it).
Workaround, configure directly:
```bash
mkdir -p build/release/tello
cmake -S . -B build/release/tello -G Ninja \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=1 \
    -DGROUNDSTATION_BUILD_EXECUTABLE=ON \
    -DGROUNDSTATION_BUILD_TESTS=OFF \
    -DGROUNDSTATION_BUILD_BENCHMARKS=OFF \
    -DGROUNDSTATION_BUILD_BACKEND_TELLO=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=1 \
    -DGIT_SUBMODULE=ON
cd build/release/tello && cmake --build . --target all -j"$(($(nproc)-2>0?$(nproc)-2:1))"
```
Expected output binary: `build/release/tello/bin/llm_to_action_fmu_tello` (confirm the exact name from
`source/llm_to_action/fmu/CMakeLists.txt`'s target-naming logic — don't assume, check).

### 3. Write `scripts/tello/run.sh`

New file, playing the same role `scripts/test/lib/sim_core.sh` plays for SITL but for real hardware — no
Gazebo/PX4 panes, just: the Tello-backend FMU binary from step 2, `gstreamer_rx --tello`, and the keyboard
teleop node, all pointed at the drone's fixed IP `192.168.10.1`. Follow the `scripts/test/<feature>/run.sh`
tmux-pane convention already used everywhere else in this repo for consistency (check an existing one,
e.g. `scripts/test/rotate-land/run.sh`, for the pattern before writing this from scratch).

### 4. Write `scripts/tello/README.md`

Mirror `scripts/test/README.md`'s structure, adapted for real hardware: no `filter.sh`/log-capture
concept needed for a manual flight, but do note: battery life (~10-13 min per battery, charge several
before starting), the 20Hz `rc` keepalive requirement (already satisfied by the FMU's existing control
loop — this is a note, not new code), and re-arm/land steps.

### 5. Syntax/build verification

```bash
bash -n scripts/tello/run.sh
```
Both build trees (step 1's PX4 rebuild, step 2's Tello build) must succeed with no new errors.

## What you're explicitly NOT doing

- Not flying the drone — no hardware access. Bring-up smoke test (`command`→`streamon`, telemetry parse,
  video decode, keepalive) is the human's job once your code is ready.
- Not touching `fmu_node.hpp` or any FMU control logic — this task is the video pipeline and launch
  script only.
- Not fixing `build.sh` itself (ROADMAP 9.6) — the separate-build-tree workaround above is intentional,
  don't refactor the real fix in as a side effect.
- Not attempting APPROACH/ORBIT/SEARCH/GO — those need position, which doesn't exist until B3. Scope here
  is strictly T1 (yaw-scan & describe, needs the RX fix) and T2 (safety stack) prerequisites — the actual
  T1/T2 flights are the human's job.

## Report back (required)

1. Exact diff summary of `rx_node.cpp` (what changed, confirm the PX4/no-flag path is byte-for-byte
   preserved).
2. Confirmed both builds succeed — paste the actual binary paths that resulted.
3. `scripts/tello/run.sh` and `README.md` written, `bash -n` clean.
4. The exact commands the human runs next, in order, once at the drone:
   ```
   cd scripts/tello && ./run.sh
   ```
   and what a successful bring-up looks like (frames decoding, `rc` keepalive holding past 15s) vs a
   failure (what to check first — the `gstreamer_rx --tello` pane's own stderr, most likely place a
   pipeline mistake shows up).
5. Suggested commit command(s) for the human.
