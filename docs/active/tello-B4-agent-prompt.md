# Agent prompt — B4: Tello bring-up (rx_node fix + launch script)

Paste this whole file as the task for a fresh agent. It has no memory of any prior session — everything
it needs is below or in the referenced spec.

## Your task

Make the real Tello's video actually reach the FMU/VLM, and produce a hardware launch script. This is
the code half of B4 — the human does the actual flying afterward, on their laptop, next to the drone.

Full spec, with all grounding and file:line citations:
`docs/active/tello-2026-08-10-spec-B4-tello-bringup-position-free-demos.md`.

## The core problem (read this before touching code)

`source/llm_to_action/gstreamer_udp_cam_rx/rx_node.cpp:24-25` hardcodes an **RTP** gstreamer pipeline
(`udpsrc ... caps="application/x-rtp..." ! rtph264depay ! avdec_h264 ! ...`) — correct for Gazebo's
simulated camera, **wrong for the real Tello**, which sends raw H.264 over UDP port 11111, no RTP framing.
`gstreamer_rx` is one binary shared by both backends (confirmed via its `CMakeLists.txt` — no
`FMU_BACKEND_*` compile definitions reach this target), so this can't be a compile-time `#if` the way
`active_backend.hpp` picks a backend. It needs a **runtime CLI flag** selecting the pipeline string at
startup — this matches the existing convention in this codebase (the FMU binary already takes
`$FMU_CANNED_FLAG` as a runtime mode-selector).

## Standing rules for this repo

- No git writes. Read-only git (`status`/`diff`/`log`) is fine. End with suggested commit commands.
- Native `Read`/`Grep`/`Glob`/`View`/`Echo` are project-denied. Use `rtk read`/`rtk grep`/`rtk ls`/`rtk find`/`rtk git`.
- To edit an existing file, native `Edit` requires a prior native `Read`, which is denied — use a Python
  heredoc instead: read the file's text in Python, assert the old string appears exactly once
  (`assert s.count(old) == 1`), replace, write back.
- Before each step, pick the right tool — LSP (`goToDefinition`/`findReferences`) for C++ navigation
  instead of defaulting to text grep.
- Lock scope: `source/llm_to_action/gstreamer_udp_cam_rx/rx_node.cpp` + new `scripts/tello/` files.
  Confirmed via `docs/LOCKS.md` that nothing else touches `rx_node.cpp` today — no lock entry needed
  unless that changes mid-task (check `docs/LOCKS.md` again if you're picking this up later than
  2026-08-09).

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
