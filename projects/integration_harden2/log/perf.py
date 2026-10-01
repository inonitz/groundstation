"""The performance record (owner rulings 2026-09-25, C.1 draft 2026-09-28): every event,
every frame included, goes into a memory buffer; a writer thread appends the buffer to
<session>/perf.jsonl every config.PERF_FLUSH_SECONDS, and die() writes it first, so a
crash keeps its timings. A hard kill loses at most one flush period. `run.sh perf`
(log/perf_report.py) computes the metrics later: "Record everything and calculate
metrics later!" (owner, C.1).

A SERVICE like the session log: the app builds one Perf(folder) and hands it to the parts
it times. A part built without one gets NO_PERF, which records nothing (tests, benches).

Stages: startup (per status row: launch -> the row is first UP; also "imports" and
"every row"), asr (push-to-talk release -> transcript, mic only), turn (the recognizer's
handle), gemma (one request; label plan | vision), sam3 (lock wait + forward per pass),
highlight_gate / count / describe (vision tasks), say (one speech output), e2e (command
-> action, ROADMAP: under 1 s: start = the push-to-talk release, a phone transcript, or a
ROS transcript with no release (the scripted run); end = the command reaches the phone
app, or the first highlight box is drawn), frame (EVERY
frame: ms = the gap since the previous frame; read / draw / show ms), gpu (memory and
load every config.PERF_GPU_SAMPLE_SECONDS, through pynvml: 0.018 ms a sample).
"""
import json
import os
import shutil
import threading
import time

import pynvml

import config
from runtime.fatal import on_die
from runtime.status import UP
from util.guarded import append_line

MIB = 1024 * 1024


class Perf:
    """@folder: the session folder, or None (record nothing, start no thread)."""

    def __init__(self, folder):
        self._path = os.path.join(folder, "perf.jsonl") if folder else None
        self._lock = threading.Lock()         # the buffer and the marks
        self._write_lock = threading.Lock()   # one flush at a time, in order
        self._rows = []                       # the events not yet written
        self._marks = {}                      # name -> (monotonic time, its fields)
        self._stop = threading.Event()
        self._threads = []
        self._gpu = None                      # the pynvml handle, once sampling
        if self._path is None:
            return

        # a crash writes the buffer before any other cleanup (the supervisor's)
        on_die(self.flush, first=True)
        self._start_thread(self._write_every_period, "perf-writer")
        return

    def record(self, stage, ms, **fields):
        """One event. ms: how long the stage took. Only buffered here: the writer thread
        encodes and writes it, so a caller (the frame loop) pays microseconds."""
        row = None
        if self._path is None:
            return

        row = {"t": round(time.time(), 3), "stage": stage, "ms": round(ms, 1)}
        row.update(fields)
        with self._lock:
            self._rows.append(row)
        return

    def mark(self, name, ago_ms=0.0, **fields):
        """Remember now (or ago_ms before now) under `name`, with fields that end() adds
        to its record. A new mark replaces an older one of that name."""
        t = time.monotonic() - ago_ms / 1000
        with self._lock:
            self._marks[name] = (t, fields)
        return

    def take_since(self, name):
        """ms since the mark `name`, and forget it; None when it was not marked."""
        entry = None
        with self._lock:
            entry = self._marks.pop(name, None)
        if entry is None:
            return None
        return (time.monotonic() - entry[0]) * 1000

    def move_mark(self, name, new_name):
        """Keep the mark `name` under new_name (its time and fields); nothing when
        `name` is not marked."""
        with self._lock:
            if name not in self._marks:
                return
            self._marks[new_name] = self._marks.pop(name)
        return

    def end(self, name, stage, **fields):
        """Record `stage`: ms since the mark `name`, the mark's fields plus these; then
        forget the mark. Nothing when `name` is not marked (e.g. already ended)."""
        entry = None
        row_fields = {}
        with self._lock:
            entry = self._marks.pop(name, None)
        if entry is None:
            return

        row_fields = dict(entry[1])
        row_fields.update(fields)
        self.record(stage, (time.monotonic() - entry[0]) * 1000, **row_fields)
        return

    def flush(self):
        """Append every buffered event to perf.jsonl (one write, one fsync). A failed
        write is printed and the run goes on: timing is not worth stopping the app
        for."""
        rows = []
        text = ""
        if self._path is None:
            return

        # the write lock spans the swap AND the write, so two flushes keep their order
        with self._write_lock:
            with self._lock:
                rows = self._rows
                self._rows = []
            if not rows:
                return
            text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
            append_line(self._path, text)
        return

    def start_gpu_sampler(self):
        """Record GPU memory and load every config.PERF_GPU_SAMPLE_SECONDS (NVIDIA only:
        without the NVIDIA driver, whose tools include nvidia-smi, there are no
        samples; pynvml would throw at init)."""
        if self._path is None or shutil.which("nvidia-smi") is None:
            return

        pynvml.nvmlInit()
        self._gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
        self._start_thread(self._sample_gpu, "perf-gpu")
        return

    def watch_startup(self, rows, launched):
        """Record a "startup" event per status row: ms from `launched` (a monotonic
        time) until the row is first UP, then one for "every row". @rows: () -> [(name,
        state, detail), ...], the status board's snapshot. The thread ends when every
        row has been UP, or at close()."""
        if self._path is None:
            return
        self._start_thread(self._watch_rows, "perf-startup", rows, launched)
        return

    def close(self):
        """Stop the threads, then write what is left."""
        self._stop.set()
        for thread in self._threads:
            thread.join()
        if self._gpu is not None:
            pynvml.nvmlShutdown()
            self._gpu = None
        self.flush()
        return

    def _start_thread(self, target, name, *args):
        thread = threading.Thread(target=target, name=name, args=args, daemon=True)
        self._threads.append(thread)
        thread.start()
        return

    def _write_every_period(self):
        while not self._stop.wait(config.PERF_FLUSH_SECONDS):
            self.flush()
        return

    def _sample_gpu(self):
        mem = 0
        load = 0

        while not self._stop.wait(config.PERF_GPU_SAMPLE_SECONDS):
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._gpu).used // MIB
            load = pynvml.nvmlDeviceGetUtilizationRates(self._gpu).gpu
            self.record("gpu", 0, mem_mib=mem, load_pct=load)
        return

    def _watch_rows(self, rows, launched):
        up = set()
        names = []
        ms = 0.0

        while not self._stop.wait(config.PERF_STARTUP_POLL_SECONDS):
            names = []
            ms = (time.monotonic() - launched) * 1000
            for name, state, _detail in rows():
                names.append(name)
                if state != UP or name in up:
                    continue
                up.add(name)
                self.record("startup", ms, row=name)

            if up.issuperset(names):
                self.record("startup", ms, row="every row")
                return
        return


NO_PERF = Perf(None)       # for a part built without the app's Perf
