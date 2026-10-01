"""What it costs to hand one app frame (1280x720 BGR, 2.64 MiB) to another process.

Four paths, each timed as a round trip from the sender's side (the reply is one byte):
  pipe:   the frame pickled through a multiprocessing Pipe (the 2.7 MiB per request).
  shm:    the frame copied into a shared-memory slot; the request carries only the slot
          number; the receiver wraps the slot as a numpy view (no copy).
  shm+rgb: as shm, and the receiver makes the RGB PIL image SAM3 needs (the copy SAM3
          already makes today, in the app's own process).
  local:  that same RGB PIL conversion in this process, the floor for comparison.
No GPU. Run: python3 bench/sam3-assessment/transfer.py"""
import multiprocessing as mp
import time
from multiprocessing import shared_memory

import numpy as np
from PIL import Image

import common

REPS = 300
SHAPE = (common.FRAME_H, common.FRAME_W, 3)


def to_pil(frame):
    """The conversion Sam3Backend.detect() does first: BGR -> RGB PIL."""
    return Image.fromarray(frame[:, :, ::-1])


def receiver(conn, shm_name):
    """The other process: answers each request with one byte."""
    shm = shared_memory.SharedMemory(name=shm_name)
    slot = np.ndarray(SHAPE, dtype=np.uint8, buffer=shm.buf)
    request = None

    while True:
        request = conn.recv()
        if request is None:
            break
        if request == "rgb":
            to_pil(slot)
        conn.send(b"k")
    del slot
    shm.close()
    return


def time_pipe(conn, frame):
    out = []
    t0 = 0.0

    for _ in range(REPS):
        t0 = time.perf_counter()
        conn.send(frame)
        conn.recv()
        out.append(common.ms_since(t0))
    return out


def time_shm(conn, slot, frame, request):
    out = []
    t0 = 0.0

    for _ in range(REPS):
        t0 = time.perf_counter()
        np.copyto(slot, frame)
        conn.send(request)
        conn.recv()
        out.append(common.ms_since(t0))
    return out


def time_local(frame):
    out = []
    t0 = 0.0

    for _ in range(REPS):
        t0 = time.perf_counter()
        to_pil(frame)
        out.append(common.ms_since(t0))
    return out


def pipe_receiver(conn):
    """The pipe path's receiver: unpickles the frame, answers one byte."""
    frame = None

    while True:
        frame = conn.recv()
        if frame is None:
            break
        conn.send(b"k")
    return


def main():
    frame = common.frames(1)[0]
    shm = shared_memory.SharedMemory(create=True, size=frame.nbytes)
    slot = np.ndarray(SHAPE, dtype=np.uint8, buffer=shm.buf)
    results = {"frame_mib": round(frame.nbytes / 2**20, 2), "reps": REPS}

    parent, child = mp.Pipe()
    proc = mp.Process(target=pipe_receiver, args=(child,))
    proc.start()
    results["pipe"] = common.stats(time_pipe(parent, frame))
    parent.send(None)
    proc.join()

    parent, child = mp.Pipe()
    proc = mp.Process(target=receiver, args=(child, shm.name))
    proc.start()
    results["shm"] = common.stats(time_shm(parent, slot, frame, "view"))
    results["shm+rgb"] = common.stats(time_shm(parent, slot, frame, "rgb"))
    parent.send(None)
    proc.join()
    results["local rgb"] = common.stats(time_local(frame))

    del slot
    shm.close()
    shm.unlink()
    for key in ("pipe", "shm", "shm+rgb", "local rgb"):
        print(f"{key:10s} {results[key]}", flush=True)
    common.write_result("transfer", results)
    return


if __name__ == "__main__":
    main()
