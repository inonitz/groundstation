"""The vision service (owner design 2026-09-23; API: docs/api-harden2/perception.h).

count / highlight / clear / describe each run as ONE task on its own thread, started by
the dispatcher (at most config.VISION_MAX_TASKS alive). Every SAM3 forward pass takes the
SAM3 priority lock: a user request outranks a highlight refresh. A task sleeps OUTSIDE
the lock, so a waiting task never blocks another.

  count     -> fire and forget: COUNT_FRAMES frames, COUNT_GAP apart, median; then it
               highlights what it counted.
  highlight -> gate (is it there?), then track: re-detect every SAM3_PERIOD, counted from
               the START of the last detect, until cleared, or HL_GIVEUP seconds without
               a hit. One highlight at a time: a new one clears the old one.
  describe  -> one Gemma question about the frame (no SAM3, no lock).

It never draws, speaks or logs. Every result goes to the app through the Sinks
callbacks."""
import functools
import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import config
from perception2 import vlm_client
from perception2.backend import DETECT_OK
from perception2.boxes import frame_area
from perception2.concept import phrase_concepts
from perception2.counting import count_instances, median_count
from perception2.dispatcher import SUBMIT_OK, Dispatcher
from perception2.engine import PerceptionEngine
from perception2.sam3_lock import PRIORITY_COMMAND, PRIORITY_REFRESH, PriorityLock
from perception2.verify import split_target, verify_highlight
from log.perf import NO_PERF

TASK_OK = "ok"
TASK_FULL = "full"                # too many tasks alive: refused, not queued
TASK_NOT_READY = "not_ready"      # SAM3 still loading (or every forward failed)

HL_TRACKING = "tracking"          # present: boxes + masks, updated every period
HL_ABSENT = "absent"              # the gate says it is not in view (reason says why)
HL_LOST = "lost"                  # tracked, then no hit for HL_GIVEUP seconds
HL_CLEARED = "cleared"            # the user cleared it, or a new highlight replaced it
HL_NOT_READY = "not_ready"


@dataclass
class HighlightUpdate:
    task: int
    state: str
    phrase: str
    concepts: str = ""
    dets: list = field(default_factory=list)
    masks: list = field(default_factory=list)
    reason: str = ""
    best: float = 0.0
    first: bool = False           # the first TRACKING update after the gate


@dataclass
class Sinks:
    """The app's callbacks. on_start runs on the SUBMITTING thread, before the task
    exists, so the app can open the task's log record in the right turn."""
    on_start: Callable            # (task, kind, phrase)
    on_count: Callable            # (task, status, n, phrase, per_frame_counts)
    on_highlight: Callable        # (HighlightUpdate)
    on_describe: Callable         # (task, ok, long_text, spoken_text, frame)
    on_pass: Callable             # (task, frame, raw_dets, forward_ms): one SAM3 forward


def absent_reason(veto, raw, best):
    """Why a highlight was refused, in plain words, for the chat."""
    if veto:
        return veto
    if not raw:
        return "SAM3 found nothing"
    if best < 0.5:
        return f"SAM3 best {best:.2f} < 0.50 gate"
    return f"SAM3 best {best:.2f} but below the size floor"


class Vision:
    def __init__(
        self,
        sam3,
        gemma,
        snapshot,
        sinks,
        use_masks,
        max_tasks=config.VISION_MAX_TASKS,
        perf=NO_PERF
    ):
        """@sam3: the SAM3 service (perception2.backend.BackendLoader).
        @gemma: the Gemma service (gemma.client.Gemma), for describe and the Gemma gate.
        @snapshot: () -> a private copy of the latest video frame, or None.
        @sinks: the app's callbacks (Sinks). @use_masks: () -> bool, the masks switch.
        @perf: the performance record (log.perf)."""
        self._perf = perf
        self._snapshot = snapshot
        self._sinks = sinks
        self._use_masks = use_masks
        self._sam3 = PriorityLock()
        self._dispatch = Dispatcher(max_tasks, name="vision")
        self._ids = itertools.count(1)
        self._tl = threading.local()                # this task thread's id and priority
        self._hl_lock = threading.Lock()
        self._highlights = {}                       # task -> stop Event

        # The engine's every SAM3 call goes through the SAM3 priority lock.
        self._engine = PerceptionEngine(
            detect=self._locked_detect(sam3.detect),
            mask_for_box=sam3.mask_for_box,
            vlm_ask=functools.partial(vlm_client.ask, gemma),
            floor=config.DETECT_FLOOR,
            draw_conf=config.HL_CONF,
            rel=config.HL_REL,
            mask_k=config.HL_MAX,     # "highlight all the cars" needs many masks
        )
        return

    def close(self):
        """Stop every highlight and stop starting tasks."""
        self.clear()
        self._dispatch.shutdown()
        return

    # --- the one SAM3 entry: every forward pass goes through here ------------------
    def _locked_detect(self, raw_detect):
        """Wrap a backend detect(frame, phrase, floor) -> (status, dets) so each call
        holds the SAM3 lock at this thread's priority and reports the pass to on_pass."""
        def detect(frame, phrase, floor):
            priority = getattr(self._tl, "priority", PRIORITY_COMMAND)
            t0 = time.monotonic()
            with self._sam3.hold(priority):
                t_forward = time.monotonic()
                status, dets = raw_detect(frame, phrase, floor)
                t_end = time.monotonic()
            self._perf.record(
                "sam3",
                (t_end - t_forward) * 1000,
                wait_ms=round((t_forward - t0) * 1000, 1),
                priority=priority
            )
            if status != DETECT_OK:
                return status, dets

            ms = round((t_end - t0) * 1000)
            self._sinks.on_pass(getattr(self._tl, "task", 0), frame, dets, ms)
            return status, dets
        return detect

    # --- requests (called from the recognizer's thread) --------------------------------
    def count(self, phrase):
        """-> (TASK_OK | TASK_FULL, task)."""
        return self._submit("count", phrase, self._count_task)

    def highlight(self, phrase):
        """-> (TASK_OK | TASK_FULL, task). Replaces the live highlight."""
        return self._submit("highlight", phrase, self._highlight_task)

    def describe(self, question):
        return self._submit("describe", question, self._describe_task)

    def clear(self):
        """Stop every live highlight. Each one reports HL_CLEARED from its own thread."""
        with self._hl_lock:
            stops = list(self._highlights.values())
        for stop in stops:
            stop.set()
        return

    def alive(self):
        return self._dispatch.alive()

    def _submit(self, kind, phrase, body):
        task = next(self._ids)
        frame = self._snapshot()           # the frame at the moment of the request
        self._sinks.on_start(task, kind, phrase)    # a FULL result closes it (the app)

        status = self._dispatch.submit(
            functools.partial(self._run, task, body, frame, phrase),
            name=f"{kind}-{task}"
        )
        if status != SUBMIT_OK:
            return TASK_FULL, task
        return TASK_OK, task

    def _run(self, task, body, frame, phrase):
        self._tl.task = task
        self._tl.priority = PRIORITY_COMMAND
        body(task, frame, phrase)
        return

    def _timed(self, stage, t0, **fields):
        self._perf.record(stage, (time.monotonic() - t0) * 1000, **fields)
        return

    # --- task bodies (each on its own thread) ------------------------------------------
    def _count_task(self, task, frame, phrase):
        status = DETECT_OK
        raw = []
        area = 0
        kept = []
        counts = []
        concepts = phrase_concepts(phrase)
        t0 = time.monotonic()

        for i in range(config.COUNT_FRAMES):
            if i:
                time.sleep(config.COUNT_GAP)        # outside the SAM3 lock
                frame = self._snapshot()
            if frame is None:
                continue

            status, raw = self._engine.detect(frame, concepts, 0.5)
            if status != DETECT_OK:                 # a failed frame is not a zero count
                continue

            area = frame_area(frame)
            kept = count_instances(
                raw,
                0.5,
                frame_area=area,
                min_frac=config.MIN_BOX_FRAC
            )
            counts.append(len(kept))

        if not counts:
            self._sinks.on_count(task, TASK_NOT_READY, 0, phrase, [])
            return

        n = median_count(counts)
        self._timed("count", t0, frames=len(counts))
        self._sinks.on_count(task, TASK_OK, n, phrase, counts)
        if n:
            self._track(task, phrase, concepts)     # highlight what was counted
        return

    def _highlight_task(self, task, frame, phrase):
        concepts = phrase_concepts(phrase)
        t0 = time.monotonic()
        present, raw, best, veto, ready = self._gate(frame, phrase, concepts)
        self._timed("highlight_gate", t0, present=present)
        if not ready:
            update = HighlightUpdate(task, HL_NOT_READY, phrase, concepts)
            self._sinks.on_highlight(update)
            return

        if not present:
            update = HighlightUpdate(
                task,
                HL_ABSENT,
                phrase,
                concepts,
                reason=absent_reason(veto, raw, best),
                best=best
            )
            self._sinks.on_highlight(update)
            return

        self._track(task, phrase, concepts, best)
        return

    def _gate(self, frame, phrase, concepts):
        """Is it in view? -> (present, raw, best, veto, ready). SAM3 decides (GATE=sam3,
        the default); GATE=either also asks Gemma; VERIFY checks a related-noun
        clause."""
        present = True
        raw = []
        hits = []
        veto = None

        if frame is None:
            return False, [], 0.0, "no video frame yet", True
        area = frame_area(frame)

        # GATE=vlm or either: Gemma answers first
        if config.GATE != "sam3":
            present, _ = self._engine.presence_gate(frame, phrase)

        # GATE=sam3, or GATE=either when Gemma said no: SAM3 decides
        if config.GATE == "sam3" or (config.GATE == "either" and not present):
            status, raw = self._engine.detect(frame, concepts, 0.1)
            if status != DETECT_OK:        # SAM3 not ready: never a false "absent"
                return False, [], 0.0, None, False
            hits = count_instances(
                raw,
                0.5,
                frame_area=area,
                min_frac=config.MIN_BOX_FRAC
            )
            if config.GATE == "sam3":
                present = bool(hits)
            else:
                present = present or bool(hits)
        best = max((float(d["conf"]) for d in raw), default=0.0)

        # VERIFY: a related-noun clause must hold too
        target = split_target(phrase)
        if config.VERIFY != "on" or not present or not target.related:
            return present, raw, best, veto, True

        verdict = verify_highlight(
            self._engine.detect,
            frame,
            target,
            floor=0.1,
            frame_area=area,
            min_frac=config.MIN_BOX_FRAC
        )
        print(f"[vision] verify '{phrase}': {verdict.verdict} -- {verdict.reason}",
              flush=True)
        if verdict.verdict not in ("draw", "failed"):   # failed = a SAM3 call failed
            present = False
            veto = verdict.reason
        return present, raw, best, veto, True

    def _track(self, task, phrase, concepts, best=0.0):
        """Re-detect every SAM3_PERIOD, counted from the START of each detect, until
        the highlight is cleared or lost."""
        started = 0.0
        elapsed = 0.0
        miss_since = None
        first = True

        self.clear()  # One highlight at a time: stop the old one, register this one.
        stop = threading.Event()
        with self._hl_lock:
            self._highlights[task] = stop

        self._tl.priority = PRIORITY_REFRESH  # refresh < user command at the SAM3 lock.
        while not stop.is_set():
            started = time.monotonic()
            frame = self._snapshot()

            if frame is None:
                # Wait out the rest of the period, then try the next frame.
                elapsed = time.monotonic() - started
                stop.wait(max(0.0, config.SAM3_PERIOD - elapsed))
                continue

            use_masks = self._use_masks()
            dets, masks, _ = self._engine.highlight_step(
                frame,
                concepts,
                None,
                use_masks
            )
            dets, masks = _drop_specks(frame, dets, masks)

            update = HighlightUpdate(
                task,
                HL_TRACKING,
                phrase,
                concepts,
                dets,
                masks,
                best=best,
                first=first
            )
            self._sinks.on_highlight(update)
            first = False

            # The give-up clock runs only while nothing is found.
            if dets:
                miss_since = None
            elif miss_since is None:
                miss_since = started
            if miss_since is not None and started - miss_since > config.HL_GIVEUP:
                self._end(task, HighlightUpdate(task, HL_LOST, phrase, concepts))
                return

            # Wait out the rest of the period: the period counts from the start.
            elapsed = time.monotonic() - started
            stop.wait(max(0.0, config.SAM3_PERIOD - elapsed))

        self._end(task, HighlightUpdate(task, HL_CLEARED, phrase, concepts))
        return

    def _end(self, task, update):
        with self._hl_lock:
            self._highlights.pop(task, None)
        self._sinks.on_highlight(update)
        return

    def _describe_task(self, task, frame, question):
        if frame is None:
            self._sinks.on_describe(task, False, "", "", None)
            return

        t0 = time.monotonic()
        ok, reply = self._engine.vlm_ask(frame, question, [])
        self._timed("describe", t0, ok=ok)
        if not ok:
            self._sinks.on_describe(task, False, "", "", frame)
            return

        long_text, _, _, spoken = reply
        self._sinks.on_describe(task, True, long_text, spoken, frame)
        return


def _drop_specks(frame, dets, masks):
    """Drop boxes under MIN_BOX_FRAC of the frame (the same floor as the gate and the
    count)."""
    keep = []
    if not dets or config.MIN_BOX_FRAC <= 0:
        return dets, masks

    min_area = frame_area(frame) * config.MIN_BOX_FRAC
    ms = list(masks) if masks else []
    for i, d in enumerate(dets):
        x0, y0, x1, y1 = d["box"]
        if (x1 - x0) * (y1 - y0) >= min_area:
            keep.append(i)
    return [dets[i] for i in keep], [ms[i] for i in keep if i < len(ms)]
