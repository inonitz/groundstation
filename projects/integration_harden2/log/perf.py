"""The performance record (owner ruling 2026-09-25): one JSON line per measured event
in <session>/perf.jsonl, always on, so every run is measured the same way. `run.sh perf`
(log/perf_report.py) turns it into p50 / p95 / max per stage.

A SERVICE like the session log: the app builds one Perf(folder) and hands it to the parts
it times. A part built without one gets NO_PERF, which records nothing (tests, benches).

Stages: asr (push-to-talk release -> transcript, mic only), turn (the recognizer's
handle), gemma (one request; label plan | vision), sam3 (lock wait + forward per pass),
highlight_gate / count / describe (vision tasks), say (one speech output), frame (per
second: fps and the loop's parts), gpu (per second: memory and load).
"""
import json
import os
import shutil
import subprocess
import threading
import time

from util.guarded import append_line

GPU_SAMPLE_SECONDS = 1.0


class Perf:
    """@folder: the session folder, or None (record nothing)."""

    def __init__(self, folder):
        self._path = os.path.join(folder, "perf.jsonl") if folder else None
        self._lock = threading.Lock()
        self._marks = {}                    # name -> the monotonic time it was marked
        self._stop = threading.Event()
        return

    def record(self, stage, ms, **fields):
        """One event. ms: how long the stage took. A failed write is printed and the run
        goes on: timing is not worth stopping the app for."""
        if self._path is None:
            return

        row = {"t": round(time.time(), 3), "stage": stage, "ms": round(ms, 1)}
        row.update(fields)
        with self._lock:
            append_line(self._path, json.dumps(row, ensure_ascii=False) + "\n")
        return

    def mark(self, name):
        """Remember now under `name` (e.g. the push-to-talk release)."""
        with self._lock:
            self._marks[name] = time.monotonic()
        return

    def take_since(self, name):
        """ms since the mark `name`, and forget it; None when it was not marked."""
        with self._lock:
            t0 = self._marks.pop(name, None)
        if t0 is None:
            return None
        return (time.monotonic() - t0) * 1000

    def start_gpu_sampler(self):
        """Record GPU memory and load every GPU_SAMPLE_SECONDS (NVIDIA only; without
        nvidia-smi there are no samples)."""
        if self._path is None or shutil.which("nvidia-smi") is None:
            return
        threading.Thread(target=self._sample_gpu, name="perf-gpu", daemon=True).start()
        return

    def close(self):
        self._stop.set()
        return

    def _sample_gpu(self):
        out = None
        mem = 0
        load = 0

        while not self._stop.wait(GPU_SAMPLE_SECONDS):
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True
            )
            if out.returncode != 0 or "," not in out.stdout:
                continue
            mem, load = (int(v) for v in out.stdout.split("\n")[0].split(","))
            self.record("gpu", 0, mem_mib=mem, load_pct=load)
        return


NO_PERF = Perf(None)       # for a part built without the app's Perf
