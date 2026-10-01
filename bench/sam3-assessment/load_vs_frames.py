"""What the SAM3 load does to the frame loop (task E1, the start-up dips).

A frame loop like app/ui.py runs on the main thread: read the webcam, draw (a frame
copy and Hebrew text through PIL, as the status and chat panes do), show. At LOAD_AT_S
the SAM3 load starts, in one of three ways:
  none:   no load (the camera's own start-up only)
  thread: Sam3Backend() on a thread of this process, as BackendLoader does today
  child:  Sam3Backend() in its own process (option S2 a of the SAM3 assessment)
  thread-1ms: as thread, with the GIL switch interval at 1 ms instead of Python's 5 ms
The load's phases are timed (torch import, transformers import, model + processor load),
so each slow frame can be matched to a phase.
GPU + webcam + display: ~25 s per mode.
Run: DISPLAY=:97 WEBCAM_DEV=2 python3 bench/sam3-assessment/load_vs_frames.py <mode>"""
import importlib
import multiprocessing as mp
import sys
import threading
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw

import common
import config
from app.draw import FONT_HE

RUN_S = 25.0
LOAD_AT_S = 3.0
TEXT = "מצלמה פעילה  gemma UP  sam3 STARTING  dji app UP  asr UP"


def load(marks, t0):
    """The SAM3 load in phases; marks gets (phase, seconds since t0) at each end."""
    marks.append(("load start", time.perf_counter() - t0))
    from sam3.model import Sam3Backend
    marks.append(("torch imported", time.perf_counter() - t0))
    importlib.import_module("transformers.models.sam3")
    marks.append(("transformers imported", time.perf_counter() - t0))
    Sam3Backend()
    marks.append(("model loaded", time.perf_counter() - t0))
    return


def child_load(conn, t0_epoch):
    """The child: the same phases, sent back on the pipe (epoch-based clock)."""
    marks = []
    load(marks, time.perf_counter() - (time.time() - t0_epoch))
    conn.send(marks)
    return


def draw(frame):
    """The draw stand-in: a frame copy plus twelve lines of PIL text on a pane."""
    display = frame.copy()
    pane = Image.new("RGB", (display.shape[1], 300))
    pen = ImageDraw.Draw(pane)
    for i in range(12):
        pen.text((10, 24 * i), TEXT, font=FONT_HE, fill=(230, 230, 230))
    return np.vstack([display, np.asarray(pane)[:, :, ::-1]])


def phase_at(t, marks):
    name = "before load"
    for phase, at in marks:
        if at <= t:
            name = "after " + phase
    return name


def main():
    mode = sys.argv[1]
    if mode == "thread-1ms":
        # a waiting thread gets the GIL after 1 ms of another thread's Python code
        sys.setswitchinterval(0.001)
    capture = cv2.VideoCapture(config.WEBCAM_DEVICE_INDEX)
    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_W)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_H)
    marks = []
    rows = []
    t0 = time.perf_counter()
    started = False
    parent = None
    proc = None
    t_read = 0.0
    t_draw = 0.0
    t_end = 0.0
    previous = t0
    ok = False
    frame = None

    while time.perf_counter() - t0 < RUN_S:
        if not started and time.perf_counter() - t0 >= LOAD_AT_S:
            started = True
            if mode in ("thread", "thread-1ms"):
                threading.Thread(target=load, args=(marks, t0), daemon=True).start()
            if mode == "child":
                parent, conn = mp.get_context("spawn").Pipe()
                proc = mp.get_context("spawn").Process(
                    target=child_load,
                    args=(conn, time.time() - (time.perf_counter() - t0))
                )
                proc.start()
        start = time.perf_counter()
        ok, frame = capture.read()
        t_read = time.perf_counter()
        if not ok:
            continue
        canvas = draw(frame)
        t_draw = time.perf_counter()
        cv2.imshow("load_vs_frames", canvas)
        cv2.waitKey(1)
        t_end = time.perf_counter()
        rows.append({
            "t": round(start - t0, 3),
            "gap": (t_end - previous) * 1000,
            "read": (t_read - start) * 1000,
            "draw": (t_draw - t_read) * 1000,
            "show": (t_end - t_draw) * 1000,
        })
        previous = t_end
    if proc is not None:
        marks = parent.recv()
        proc.join()
    report(mode, rows, marks)
    return


def report(mode, rows, marks):
    after_first = rows[1:]               # the first frame opens the camera
    slow = sorted(after_first, key=lambda r: -r["gap"])[:10]
    results = {"mode": mode, "marks": marks, "frames": len(rows)}
    for key in ("gap", "read", "draw", "show"):
        results[key] = common.stats([r[key] for r in after_first])
    results["over_100ms"] = sum(1 for r in after_first if r["gap"] > 100)
    results["slowest"] = []
    for r in slow:
        row = {}
        for key, value in r.items():
            row[key] = round(value, 1)
        row["phase"] = phase_at(r["t"], marks)
        results["slowest"].append(row)
    print(mode, "marks", [(p, round(t, 2)) for p, t in marks], flush=True)
    for key in ("gap", "read", "draw", "show", "over_100ms"):
        print(f"  {key:10s} {results[key]}", flush=True)
    for r in results["slowest"]:
        print("  slow", r, flush=True)
    common.write_result(f"load-vs-frames-{mode}", results)
    return


if __name__ == "__main__":
    main()
