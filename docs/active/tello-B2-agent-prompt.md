# Agent prompt — B2: Tello camera calibration tooling

Paste this whole file as the task for a fresh agent. It has no memory of any prior session — everything
it needs is below or in the referenced spec.

## Your task

Write two standalone Python scripts that don't exist yet. **You are not flying anything or touching real
hardware** — that part is the human's job, on their laptop, next to the actual drone. Your job is to
produce working, syntax-correct tooling so that when the human sits down with the Tello, they can run it
immediately.

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

## What to produce

1. **`scripts/tello/capture_calibration_frames.py`** — connects to the Tello over WiFi
   (`192.168.10.1:8889` command socket, `udp://0.0.0.0:11111` video stream via `cv2.VideoCapture` +
   FFMPEG), sends `command`/`streamon`, shows a live preview with chessboard-corner overlay, saves frames
   on SPACE, quits on ESC. **Must print the actual confirmed resolution from the first captured frame** —
   the spec is explicit that ~960x720 is an unverified estimate, not a fact, and the script must not
   assume it. Must also measure and print the actual delivered stream fps (count frames over the capture
   session), not assume 30.

2. **`scripts/tello/calibrate_camera.py`** — runs `cv2.calibrateCamera` over the saved checkerboard
   frames, prints reprojection RMS error (warn if ≥1.0px), and writes `dependencies/stella_config_tello.yaml`
   with a `Camera:` block matching the exact schema in `dependencies/stella_config.yaml` (the existing sim
   config) — `fx, fy, cx, cy, k1, k2, p1, p2, k3, fps, cols, rows, color_order`. `fps` and `cols`/`rows`
   come from the capture script's measured values, not assumed ones — take them as CLI args, don't
   hardcode.

Start from the working source below — verified against this checkout's `dependencies/stella_config.yaml`
schema — don't reinvent it, but do verify it actually runs (imports resolve, syntax is valid) rather than
copying blind.

**`scripts/tello/capture_calibration_frames.py`:**
```python
#!/usr/bin/env python3
"""Grab checkerboard frames from a real Tello for B2 camera calibration.
Standalone -- no ROS2/FMU build needed. Connect to the Tello's WiFi first,
then: python3 capture_calibration_frames.py [out_dir] [board_cols] [board_rows]
Press SPACE to save a frame, ESC to quit. Aim for 20-40 frames, varied angle/distance."""
import sys, os, time
import cv2

TELLO_CMD_ADDR = ("192.168.10.1", 8889)
STREAM_URL = "udp://0.0.0.0:11111"

def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "calib_frames"
    board_cols = int(sys.argv[2]) if len(sys.argv) > 2 else 9
    board_rows = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    os.makedirs(out_dir, exist_ok=True)

    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(b"command", TELLO_CMD_ADDR)
    time.sleep(0.5)
    sock.sendto(b"streamon", TELLO_CMD_ADDR)
    time.sleep(2.0)

    cap = cv2.VideoCapture(STREAM_URL, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("ERROR: could not open Tello video stream -- check WiFi connection.")
        sys.exit(1)

    ok, frame = cap.read()
    if not ok:
        print("ERROR: stream opened but no frame read.")
        sys.exit(1)
    h, w = frame.shape[:2]
    print(f"CONFIRMED resolution: {w}x{h} -- use this for cols/rows below, not an assumed value.")

    saved = 0
    t_start = time.time()
    frame_count = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        frame_count += 1
        found, corners = cv2.findChessboardCorners(frame, (board_cols, board_rows))
        disp = frame.copy()
        if found:
            cv2.drawChessboardCorners(disp, (board_cols, board_rows), corners, found)
        cv2.putText(disp, f"saved={saved}  SPACE=save  ESC=quit", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("Tello calibration capture", disp)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        if key == 32:
            path = os.path.join(out_dir, f"frame_{saved:03d}.png")
            cv2.imwrite(path, frame)
            print(f"saved {path} (checkerboard {'found' if found else 'NOT found'})")
            saved += 1

    elapsed = time.time() - t_start
    print(f"measured stream fps ~= {frame_count / elapsed:.1f} over {elapsed:.1f}s -- use this in the YAML, not an assumed 30.0")
    print(f"saved {saved} frames to {out_dir}/ (target 20-40)")
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
```

**`scripts/tello/calibrate_camera.py`:**
```python
#!/usr/bin/env python3
"""Run OpenCV calibrateCamera over captured checkerboard frames and write
dependencies/stella_config_tello.yaml in the schema stella_vslam expects.
Usage: python3 calibrate_camera.py <frames_dir> <board_cols> <board_rows> <square_size_m> <measured_fps>"""
import sys, glob
import cv2
import numpy as np
import yaml

def main():
    frames_dir, board_cols, board_rows, square_size, fps = (
        sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
    )
    objp = np.zeros((board_rows * board_cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:board_cols, 0:board_rows].T.reshape(-1, 2) * square_size

    objpoints, imgpoints = [], []
    img_size = None
    files = sorted(glob.glob(f"{frames_dir}/*.png"))
    if len(files) < 10:
        print(f"WARNING: only {len(files)} frames -- 20-40 recommended for a stable calibration.")

    for f in files:
        img = cv2.imread(f)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_size = gray.shape[::-1]
        found, corners = cv2.findChessboardCorners(gray, (board_cols, board_rows))
        if not found:
            print(f"skip {f}: checkerboard not found")
            continue
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
        objpoints.append(objp)
        imgpoints.append(corners)

    print(f"using {len(objpoints)}/{len(files)} frames with a detected checkerboard")
    rms, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
        objpoints, imgpoints, img_size, None, None)

    print(f"reprojection RMS error: {rms:.4f} px (target < ~1.0 px)")
    fx, fy = camera_matrix[0, 0], camera_matrix[1, 1]
    cx, cy = camera_matrix[0, 2], camera_matrix[1, 2]
    k1, k2, p1, p2, k3 = dist_coeffs.ravel()[:5]

    out = {
        "Camera": {
            "name": "Tello_Real_Camera",
            "setup": "monocular",
            "model": "perspective",
            "fx": float(fx), "fy": float(fy), "cx": float(cx), "cy": float(cy),
            "k1": float(k1), "k2": float(k2), "p1": float(p1), "p2": float(p2), "k3": float(k3),
            "fps": fps,
            "cols": img_size[0], "rows": img_size[1],
            "color_order": "RGB",
        }
    }
    out_path = "dependencies/stella_config_tello.yaml"
    with open(out_path, "w") as fh:
        yaml.safe_dump(out, fh, default_flow_style=False, sort_keys=False)
    print(f"wrote {out_path}")
    if rms >= 1.0:
        print("WARNING: reprojection error >= 1.0 px -- recapture with more/better-varied frames before trusting this.")

if __name__ == "__main__":
    main()
```
(`FeatureExtractor:` and any other non-`Camera:` sections in `dependencies/stella_config.yaml` are
unrelated to calibration — after this script writes the `Camera:` block, copy those sections over
unchanged into the Tello variant by hand. B1 owns tuning those, not B2.)

## Steps

1. Write both scripts to `scripts/tello/` (create the directory).
2. `python3 -m py_compile scripts/tello/capture_calibration_frames.py scripts/tello/calibrate_camera.py`
   — must pass with no errors.
3. Check what's actually importable in this environment: `python3 -c "import cv2, numpy, yaml"` — if any
   of these aren't installed, say so plainly in your report rather than silently leaving broken tooling;
   don't try to pip-install anything without flagging it first (this repo doesn't own its Python env
   management, don't assume you're allowed to change it).
4. Sanity-check the YAML schema by hand: does `dependencies/stella_config.yaml`'s `Camera:` block have
   exactly the keys your `calibrate_camera.py` writes? `rtk read dependencies/stella_config.yaml` and
   compare field-for-field. If there's a mismatch, fix your script, not the reference file.
5. Write `scripts/tello/README.md` — three sections: (a) prerequisites (connect laptop to Tello's WiFi
   AP first), (b) exact commands to run both scripts in order with realistic example args, (c) what a
   good result looks like (reprojection error under ~1px) vs a bad one (recapture with more/better-varied
   frames).

## What you're explicitly NOT doing

- Not flying the drone or capturing real frames — no hardware access.
- Not touching `rx_node.cpp`, the FMU build, or anything ROS2/CMake — B2 has no dependency on B4's
  video-pipeline fix (the spec corrected this explicitly: the capture script uses a direct
  `cv2.VideoCapture`/FFMPEG path, not `rx_node`).
- Not tuning `FeatureExtractor:` or any other non-`Camera:` section of the stella config — that's B1's
  territory; your script should note in its output that those sections need copying over by hand from
  `dependencies/stella_config.yaml` afterward, not attempt to generate them.

## Report back (required)

1. Both scripts written, `py_compile` clean — confirm both.
2. Any missing Python dependencies found in step 3 — list them plainly, don't paper over.
3. Confirmed the YAML schema match in step 4.
4. The exact commands the human should run, in order, once they're at the drone with the laptop:
   ```
   python3 scripts/tello/capture_calibration_frames.py <out_dir> <cols> <rows>
   # ... capture 20-40 frames, note the printed resolution + measured fps ...
   python3 scripts/tello/calibrate_camera.py <out_dir> <cols> <rows> <square_size_m> <measured_fps>
   ```
5. Suggested commit command for the human.
