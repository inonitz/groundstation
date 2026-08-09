# Agent prompt — B2: Tello camera calibration tooling

Paste this whole file as the task for a fresh agent. It has no memory of any prior session — everything
it needs is below or in the referenced spec.

## Your task

Write two standalone Python scripts that don't exist yet. **You are not flying anything or touching real
hardware** — that part is the human's job, on their laptop, next to the actual drone. Your job is to
produce working, syntax-correct tooling so that when the human sits down with the Tello, they can run it
immediately.

Full spec (has the complete script content already, this is largely transcription + verification, not
invention): `docs/active/tello-2026-08-10-spec-B2-tello-camera-calibration.md`.

## Standing rules for this repo

- No git writes — no `add`/`commit`/`push`. Read-only git is fine. End with suggested commit commands for
  the human.
- Native `Read`/`Grep`/`Glob`/`View`/`Echo` are project-denied. Use `rtk read`/`rtk grep`/`rtk ls`/`rtk find`/`rtk git` via Bash.
- These are new files — use `Write`, not `Edit` (no pre-existing content to preserve).

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

The full working source for both scripts is written out in the spec (`docs/active/tello-2026-08-10-spec-B2-tello-camera-calibration.md`,
sections "Capture script" and "Calibration script") — start from that, don't reinvent it, but do verify it
actually runs (imports resolve, syntax is valid) rather than copying blind.

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
