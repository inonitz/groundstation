"""The SAM3 priority lock. SAM3 is one model on one GPU: one forward pass at a time.
Every vision thread takes this lock for exactly one forward pass. When the lock is free,
the waiter with the highest priority gets it; waiters with the same priority get it in
arrival order (like the Linux rt_mutex waiter tree). So a user's command never waits
behind a queue of highlight refreshes.

A Python threading.Lock gives no order at all, which is why this is not one."""
import contextlib
import heapq
import itertools
import threading

PRIORITY_COMMAND = 0     # a fresh user request: count, highlight gate, verify
PRIORITY_REFRESH = 1     # a live highlight's periodic re-detect


class PriorityLock:
    """@_waiting: a heap of (priority, arrival) tickets.
    @_held: True while one thread owns it."""

    def __init__(self):
        self._cond = threading.Condition()
        self._waiting = []
        self._held = False
        self._arrival = itertools.count()
        return

    def acquire(self, priority):
        """Block until this caller is the best waiter and the lock is free. No timeout: a
        forward pass always ends (a GPU error inside it dies the app)."""
        ticket = (priority, next(self._arrival))
        with self._cond:
            heapq.heappush(self._waiting, ticket)
            while self._held or self._waiting[0] != ticket:
                self._cond.wait()
            heapq.heappop(self._waiting)
            self._held = True
        return

    def release(self):
        with self._cond:
            self._held = False
            # every waiter re-checks; only the best one proceeds
            self._cond.notify_all()
        return

    @contextlib.contextmanager
    def hold(self, priority):
        """`with lock.hold(PRIORITY_COMMAND): <one forward pass>`. No try/finally: an
        error inside a forward pass reaches the crash hook and the app dies, lock and
        all."""
        self.acquire(priority)
        yield
        self.release()
        return
