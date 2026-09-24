"""The vision dispatcher (owner design 2026-09-22/23): producers submit tasks; ONE
dispatcher thread sleeps on a condition variable (zero CPU when idle, no polling) and
starts ONE thread per task. At most `max_tasks` tasks are alive or waiting; a submit past
that is refused (FULL), never queued. A task thread ends when its function returns: a
count at once, a highlight when it is cleared or gives up. Tasks do not block each other:
only the SAM3 forward pass is serialized, by the SAM3 priority lock (sam3_lock.py)."""
import collections
import threading

SUBMIT_OK = 0
SUBMIT_FULL = 1


class Dispatcher:
    def __init__(self, max_tasks, name="vision"):
        self.mk_maxTasks = max_tasks
        self.mk_name = name
        self._cond = threading.Condition()
        self._pending = collections.deque()     # submitted, thread not started yet
        self._active = 0                        # task threads running
        self.mb_stop = False
        self._thread = threading.Thread(
            target=self._run,
            name=f"{name}-dispatcher",
            daemon=True
        )
        self._thread.start()
        return

    def submit(self, fn, name="task"):
        """Hand one task (a no-argument callable) to the dispatcher. -> SUBMIT_OK, or
        SUBMIT_FULL when max_tasks tasks are already alive or waiting."""
        with self._cond:
            if self._active + len(self._pending) >= self.mk_maxTasks:
                return SUBMIT_FULL
            self._pending.append((fn, name))
            self._cond.notify_all()
        return SUBMIT_OK

    def alive(self):
        """Tasks running or waiting to start."""
        with self._cond:
            return self._active + len(self._pending)

    def shutdown(self):
        """Stop starting tasks. Running task threads end on their own (daemons)."""
        with self._cond:
            self.mb_stop = True
            self._cond.notify_all()
        self._thread.join()
        return

    def _run(self):
        fn = None
        name = ""

        while True:
            with self._cond:
                while not self._pending and not self.mb_stop:
                    self._cond.wait()
                if self.mb_stop:
                    return
                fn, name = self._pending.popleft()
                self._active += 1

            threading.Thread(
                target=self._task,
                args=(fn,),
                name=f"{self.mk_name}-{name}",
                daemon=True
            ).start()

    def _task(self, fn):
        fn()
        with self._cond:
            self._active -= 1
            self._cond.notify_all()
        return
