#!/usr/bin/env python3
"""The plan time, split: the time our Gemma client measures around one plan request,
next to llama-server's own prompt and generation times (owner KI2, 2026-10-01). The
difference ("outside") is the time the server did not spend on the request: HTTP, its
queue, our Python.

Three phases, each on the app's real path (gemma.client.Gemma + Recognizer.plan):
  first   the first plan after each fresh start and the app's own warm-up plan
  warm    PLANS plans on the warm server, the GPU free
  sam3    the same plans while a thread in this process runs SAM3 without a pause:
          the app also shares one process and one GPU (a worst case)

    python3 plan_timing.py [--restarts 5] [--plans 60] [--no-sam3]

Take the GPU first: tools/lock.sh run <agent> gpu -- python3 plan_timing.py
Results: results/<date-time>.json (every request) and results/<date-time>.md (the table).
"""
import argparse
import datetime
import json
import os
import sys
import threading
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "projects", "integration_harden2"))
sys.path.insert(0, os.path.join(ROOT, "bench", "recognizer"))
sys.path.insert(0, os.path.join(ROOT, "projects", "integration_harden2", "test"))

import config                                                   # noqa: E402
from accuracy import BENCH_PORT, percentile, start_gemma        # noqa: E402
from gemma.client import Gemma                                  # noqa: E402
from recognizer import Recognizer                               # noqa: E402
from recognizer.recognizer import warm_up                       # noqa: E402
from runtime.fatal import die                                    # noqa: E402
from runtime.supervisor import Supervisor                        # noqa: E402
from support import RecordingPerf                               # noqa: E402

RESULTS_DIR = os.path.join(HERE, "results")
SENTENCE_FILES = ("commands.json", "perception.json")
SAM3_PHRASE = "person"
SAM3_WARM_TIMEOUT_S = 120   # two passes of a fresh model take seconds, not minutes
COLUMNS = (
    ("ms", "ours"),
    ("server_ms", "server"),
    ("outside_ms", "outside"),
    ("prompt_n", "prompt tokens"),
    ("predicted_n", "answer tokens"),
)


class Sam3Load:
    """A thread that runs SAM3 detects without a pause on a blank camera-size frame.
    A blank frame still runs the full image encoding and the detector step."""

    def __init__(self):
        from sam3.model import Sam3Backend    # torch loads only when this phase runs
        self.backend = Sam3Backend()
        self.frame = np.zeros((config.CAM_H, config.CAM_W, 3), np.uint8)
        self.passes = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="sam3-load", daemon=True)
        return

    def close(self):
        """Stop the loop and drop the model, so its GPU memory can be freed."""
        self.stop.set()
        self.thread.join()
        self.backend = None
        return

    def warm(self):
        """Wait for two passes (the first of a fresh model is slow). -> False when the
        thread died or the passes did not come in SAM3_WARM_TIMEOUT_S."""
        deadline = time.monotonic() + SAM3_WARM_TIMEOUT_S
        while self.passes < 2:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                return False
            time.sleep(0.1)
        return True

    def _run(self):
        while not self.stop.is_set():
            self.backend.detect(self.frame, SAM3_PHRASE)
            self.passes += 1
        return


def sentences(count):
    """`count` Hebrew sentences, taken in turn from the command and the vision files,
    so both kinds of plan are in the sample."""
    pools = []
    picked = []
    for name in SENTENCE_FILES:
        path = os.path.join(ROOT, "datasets", "recognizer", name)
        with open(path, encoding="utf-8") as f:
            pools.append([case["he"] for case in json.load(f)["cases"]])

    for i in range(count):
        pool = pools[i % len(pools)]
        picked.append(pool[(i // len(pools)) % len(pool)])
    return picked


def plan_rows(gemma, recorder, texts, phase):
    """One plan per sentence. -> this phase's rows, each with the server's time and the
    time outside it (None when the reply had no timings)."""
    recognizer = Recognizer(None, None, gemma)
    rows = []
    for he in texts:
        first = len(recorder.rows)
        recognizer.plan(he)
        for row in recorder.rows[first:]:
            row["phase"] = phase
            row["he"] = he
            row["server_ms"] = None
            row["outside_ms"] = None
            if "prompt_ms" in row and "predicted_ms" in row:
                row["server_ms"] = round(row["prompt_ms"] + row["predicted_ms"], 1)
                row["outside_ms"] = round(row["ms"] - row["server_ms"], 1)
            row["ms"] = round(row["ms"], 1)
            rows.append(row)
    return rows


def spread(rows, key):
    """p50 / p90 / max of one column, or "-" when no row has it."""
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return "-"
    p50 = percentile(values, 0.5)
    p90 = percentile(values, 0.9)
    return f"{p50:.0f} / {p90:.0f} / {max(values):.0f}"


def table(rows, sam3_rate):
    lines = [
        "| phase | plans | " + " | ".join(name for _, name in COLUMNS) + " |",
        "|---" * (len(COLUMNS) + 2) + "|",
    ]
    for phase in ("first", "warm", "sam3"):
        mine = [row for row in rows if row["phase"] == phase]
        if not mine:
            continue
        cells = [spread(mine, key) for key, _ in COLUMNS]
        lines.append(f"| {phase} | {len(mine)} | " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("Each cell: p50 / p90 / max; times in ms.")
    if sam3_rate is not None:
        lines.append(f"SAM3 during the sam3 phase: {sam3_rate:.2f} passes per second.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--restarts", type=int, default=5)
    ap.add_argument("--plans", type=int, default=60)
    ap.add_argument("--no-sam3", action="store_true")
    args = ap.parse_args()
    recorder = RecordingPerf()
    texts = sentences(args.plans)
    rows = []
    sam3_rate = None
    supervisor = None
    gemma = None

    if args.restarts < 1:
        die("--restarts must be 1 or more: the other phases use the last start")

    for i in range(args.restarts):
        if supervisor is not None:
            supervisor.stop_all()
        supervisor = Supervisor()
        start_gemma(supervisor, thinking=False)
        warm_up(Gemma(BENCH_PORT))      # as the app does before Gemma's row is UP
        gemma = Gemma(BENCH_PORT, perf=recorder)
        rows += plan_rows(gemma, recorder, [texts[i % len(texts)]], "first")
        print(f"[plan_timing] start {i + 1}: {rows[-1]['ms']} ms", flush=True)

    rows += plan_rows(gemma, recorder, texts, "warm")
    print("[plan_timing] warm phase done", flush=True)

    if not args.no_sam3:
        load = Sam3Load()
        load.thread.start()
        if not load.warm():
            supervisor.stop_all()
            die(f"SAM3 made no two passes in {SAM3_WARM_TIMEOUT_S} s (the error above)")
        passes0 = load.passes
        t0 = time.monotonic()
        rows += plan_rows(gemma, recorder, texts, "sam3")
        sam3_rate = (load.passes - passes0) / (time.monotonic() - t0)
        load.close()
    supervisor.stop_all()

    text = table(rows, sam3_rate)
    print(text)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, stamp + ".json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    with open(os.path.join(RESULTS_DIR, stamp + ".md"), "w", encoding="utf-8") as f:
        f.write(f"# Plan timing, {stamp}\n\n{text}\n")
    return


if __name__ == "__main__":
    main()
