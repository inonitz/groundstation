"""SAM3 in the app's process vs SAM3 in its own process with a shared frame buffer.

own process: a child loads Sam3Backend; the parent copies each frame into a
shared-memory slot and sends only (slot, phrase); the child runs detect() on a numpy view
of the slot and answers (its detect ms, hits). The round trip minus the child's detect is
the cost of the split.
in process: the same detects on a thread of this process, as the app runs them today.
A UI probe (a 30 Hz draw loop on the main thread, like app/ui.py) measures what SAM3 does
to the frame loop in each layout: the draw time, and how late each tick starts.
GPU: ~3 min. Run: python3 bench/sam3-assessment/process_split.py"""
import multiprocessing as mp
import threading
import time
from multiprocessing import shared_memory

import cv2
import numpy as np

import common

REPS = 24
PROBE_S = 10.0
TICK_S = 1 / 30
SHAPE = (common.FRAME_H, common.FRAME_W, 3)


def sam3_child(conn, shm_name):
    """The SAM3 process: load, say ready, then answer (slot, phrase) requests."""
    from sam3.model import Sam3Backend
    shm = shared_memory.SharedMemory(name=shm_name)
    slots = np.ndarray((2,) + SHAPE, dtype=np.uint8, buffer=shm.buf)
    sam3 = Sam3Backend()
    request = None
    t0 = 0.0
    dets = []

    conn.send("ready")
    while True:
        request = conn.recv()
        if request is None:
            break
        t0 = time.perf_counter()
        _status, dets = sam3.detect(slots[request[0]], request[1], conf=0.3)
        conn.send((common.ms_since(t0), len(dets)))
    del slots
    shm.close()
    return


def probe(stop, frame):
    """The UI stand-in: every tick, draw boxes, a label and a mask blend on a copy of
    the frame. -> (draw ms list, late ms list)."""
    draw = []
    late = []
    next_tick = time.perf_counter()
    t0 = 0.0
    canvas = None

    while not stop.is_set():
        t0 = time.perf_counter()
        late.append(max(0.0, (t0 - next_tick) * 1000))
        canvas = frame.copy()
        for i in range(8):
            cv2.rectangle(
                canvas,
                (40 + 60 * i, 40),
                (90 + 60 * i, 200),
                (60, 220, 60),
                2
            )
        cv2.putText(
            canvas,
            "probe",
            (40, 260),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255)
        )
        canvas[300:500, 300:700] = cv2.addWeighted(
            canvas[300:500, 300:700], 0.6, frame[0:200, 0:400], 0.4, 0
        )
        draw.append(common.ms_since(t0))
        next_tick += TICK_S
        time.sleep(max(0.0, next_tick - time.perf_counter()))
    return draw, late


def run_with_probe(frame, work):
    """Run work() on a thread while the probe runs here -> (work result, probe row)."""
    stop = threading.Event()
    box = {}
    worker = threading.Thread(target=run_then_stop, args=(work, box, stop), daemon=True)
    worker.start()
    draw, late = probe(stop, frame)
    worker.join()
    return box["out"], {"draw_ms": common.stats(draw), "late_ms": common.stats(late)}


def run_then_stop(work, box, stop):
    box["out"] = work()
    stop.set()
    return


def in_process(frames):
    from sam3.model import Sam3Backend
    sam3 = Sam3Backend()
    sam3.detect(frames[0], common.PHRASE_ONE, conf=0.3)          # warm-up
    ms = []

    def work():
        t0 = 0.0
        for i in range(REPS):
            t0 = time.perf_counter()
            sam3.detect(frames[i % len(frames)], common.PHRASE_ONE, conf=0.3)
            ms.append(common.ms_since(t0))
        return ms
    return run_with_probe(frames[0], work)


def own_process(frames):
    shm = shared_memory.SharedMemory(create=True, size=2 * frames[0].nbytes)
    slots = np.ndarray((2,) + SHAPE, dtype=np.uint8, buffer=shm.buf)
    parent, child = mp.get_context("spawn").Pipe()
    proc = mp.get_context("spawn").Process(target=sam3_child, args=(child, shm.name))
    t0 = time.perf_counter()
    proc.start()
    parent.recv()
    start_ms = common.ms_since(t0)
    rows = {"round_trip": [], "child_detect": [], "overhead": []}

    def work():
        t = 0.0
        for i in range(REPS + 1):
            t = time.perf_counter()
            np.copyto(slots[i % 2], frames[i % len(frames)])
            parent.send((i % 2, common.PHRASE_ONE))
            child_ms, _hits = parent.recv()
            if i == 0:
                continue              # the warm-up detect
            rows["round_trip"].append(common.ms_since(t))
            rows["child_detect"].append(child_ms)
            rows["overhead"].append(rows["round_trip"][-1] - child_ms)
        return rows
    rows, probe_row = run_with_probe(frames[0], work)
    parent.send(None)
    proc.join()
    shm.close()
    shm.unlink()
    return start_ms, rows, probe_row


def main():
    frames = common.frames(8)
    stop = threading.Event()
    threading.Timer(PROBE_S, stop.set).start()
    draw, late = probe(stop, frames[0])
    results = {"reps": REPS, "probe_alone": {
        "draw_ms": common.stats(draw), "late_ms": common.stats(late)}}

    start_ms, rows, probe_row = own_process(frames)
    results["own_start_ms"] = round(start_ms)
    results["own"] = {key: common.stats(val) for key, val in rows.items()}
    results["probe_own"] = probe_row
    ms, probe_row = in_process(frames)
    results["in_process_detect"] = common.stats(ms)
    results["probe_in_process"] = probe_row
    for key, val in results.items():
        print(f"{key:18s} {val}", flush=True)
    common.write_result("process-split", results)
    return


if __name__ == "__main__":
    main()
