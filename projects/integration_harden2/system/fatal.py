"""Fatal-crash helper (owner ruling 2026-09-19: NO exceptions in our own code --
crash, loudly).

Call die(msg) for any of OUR error conditions: bad config, a server that will not
start, a missing model. It prints a loud banner and terminates the process hard
(os._exit, no exception to catch). A third-party call that throws is caught only in
util/guarded.py; a throw nobody catches reaches install_crash_hooks() -> die().

The cleanup loop below is the ONE try/except outside util/guarded.py: the crash path
must reach os._exit even when a cleanup throws.

on_die(fn) registers a cleanup that runs before the exit: the supervisor uses it to
stop every child process, so a crash never leaves Gemma or the ASR server orphaned
(2026-09-22).
"""
import os
import sys
import threading
import traceback

_CLEANUPS = []
# the first die() runs the cleanups; a second one waits for it
_DYING = threading.Lock()


def on_die(fn):
    """Run fn() inside die(), before the process exits. fn must not call die()."""
    _CLEANUPS.append(fn)
    return


def die(msg):
    """Print a loud reason and crash. No return, no exception -- os._exit(1)."""
    sys.stdout.flush()
    bar = "=" * 72
    sys.stderr.write(f"\n{bar}\nFATAL: {msg}\n{bar}\n")
    sys.stderr.flush()
    # a second die() WAITS here: the first finishes every cleanup, then its os._exit
    # ends the whole process (exiting early raced it)
    _DYING.acquire()

    for fn in _CLEANUPS:
        try:
            fn()
        # the crash path MUST reach os._exit; a failing cleanup is reported
        except Exception as e:
            sys.stderr.write(f"FATAL: a cleanup failed during die(): {e!r}\n")
    sys.stderr.flush()
    os._exit(1)


def install_crash_hooks():
    """Turn an uncaught exception ANYWHERE into die(): our code does not throw, so one
    that escapes is a bug, and a thread that dies silently is worse than a crash (a
    dead SAM3 consumer queues every task forever -- review finding R5). Covers every
    thread and the main thread. Call once, at start-up."""
    def on_thread(args):
        thread = args.thread.name if args.thread else "?"
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
        die(f"uncaught {args.exc_type.__name__} in thread {thread}: {args.exc_value}")

    def on_main(exc_type, exc_value, exc_tb):
        traceback.print_exception(exc_type, exc_value, exc_tb)
        die(f"uncaught {exc_type.__name__} in the main thread: {exc_value}")

    threading.excepthook = on_thread
    sys.excepthook = on_main
    return


def asyncio_crash_handler(loop, context):
    """For loop.set_exception_handler: an exception escaping an asyncio task is a bug
    -> die()."""
    exc = context.get("exception")
    if exc is not None:
        traceback.print_exception(type(exc), exc, exc.__traceback__)
    die(f"uncaught error in an asyncio task: {context.get('message')} {exc!r}")
