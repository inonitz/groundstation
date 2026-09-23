"""One-consumer task queue: the producer/consumer core for every SAM3 call.

Producers (the command dispatch) submit tasks. ONE consumer thread runs them, one at a time, so only
that thread ever touches the SAM3 backend and the highlight state it writes. There is no shared model
and no shared mask cache to race (owner ruling 2026-09-22; bench/sam3-concurrency-bench shows extra
threads give no speed anyway).

Scheduling:
  - A task has a priority and a due time. The consumer runs the due task with the lowest priority
    number; ties go to the earliest due time, then to submission order.
  - PRIORITY_COMMAND (a fresh user command) beats PRIORITY_REFRESH (a highlight re-detect).
  - A task can be delayed. A highlight re-detect uses this to run once per SAM3 period.
  - The consumer sleeps on a condition variable: no work means zero CPU, not a poll loop. With future
    work only, it sleeps exactly until that task is due.
  - A new command is refused (SUBMIT_FULL) while max_active tasks wait; a refresh is never refused.

A task is a plain callable with no arguments. Our code does not throw, so the consumer does not catch.
"""
import threading
import time

PRIORITY_COMMAND = 0
PRIORITY_REFRESH = 1

SUBMIT_OK = 0
SUBMIT_FULL = 1


class _Task:
    """@fn: the callable to run. @priority: lower runs first. @due: monotonic time it may start.
    @seq: submission order, the last tie-break. @tag: a label cancel() matches (a highlight id)."""
    __slots__ = ("fn", "priority", "due", "seq", "tag")

    def __init__(self, fn, priority, due, seq, tag):
        self.fn = fn
        self.priority = priority
        self.due = due
        self.seq = seq
        self.tag = tag


class TaskQueue:
    def __init__(self, max_active, name="vision-worker"):
        self.mk_maxActive = max_active
        self._pending = []
        self._seq = 0
        self._cond = threading.Condition()
        self.mb_running = True
        self._thread = threading.Thread(target=self._consume, name=name, daemon=True)
        self._thread.start()

    # --- producer side ----------------------------------------------------------------
    def submit(self, fn, priority=PRIORITY_COMMAND, delay=0.0, tag=None):
        """Queue fn to run after `delay` seconds. Returns SUBMIT_OK, or SUBMIT_FULL at the cap. Only a new
        COMMAND counts against the cap: a refresh continues an accepted highlight and is never refused, or
        the refresh loop would end silently with frozen boxes (review R25)."""
        with self._cond:
            if priority == PRIORITY_COMMAND and len(self._pending) >= self.mk_maxActive:
                return SUBMIT_FULL
            self._seq += 1
            self._pending.append(_Task(fn, priority, time.monotonic() + delay, self._seq, tag))
            self._cond.notify()
        return SUBMIT_OK

    def cancel(self, tag):
        """Drop every waiting task with this tag. Returns how many were dropped."""
        with self._cond:
            before = len(self._pending)
            self._pending = [t for t in self._pending if t.tag != tag]
            dropped = before - len(self._pending)
        return dropped

    def pending(self):
        with self._cond:
            count = len(self._pending)
        return count

    def shutdown(self, timeout=2.0):
        with self._cond:
            self.mb_running = False
            self._cond.notify()
        self._thread.join(timeout)
        return

    # --- consumer side ----------------------------------------------------------------
    def _take_due(self, now):
        """Remove and return the due task that should run next, or None."""
        due = [t for t in self._pending if t.due <= now]
        if not due:
            return None
        task = min(due, key=lambda t: (t.priority, t.due, t.seq))
        self._pending.remove(task)
        return task

    def _wait_seconds(self, now):
        """How long to sleep: until the earliest future task, or forever (None) when empty."""
        if not self._pending:
            return None
        return max(0.0, min(t.due for t in self._pending) - now)

    def _consume(self):
        task = None
        while True:
            with self._cond:
                task = None
                while self.mb_running:
                    now = time.monotonic()
                    task = self._take_due(now)
                    if task is not None:
                        break
                    self._cond.wait(self._wait_seconds(now))
                if not self.mb_running:
                    return
            task.fn()            # outside the lock: producers can submit while SAM3 runs
