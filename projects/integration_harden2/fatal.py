"""Fatal-crash helper (owner ruling 2026-09-19: NO exceptions in our own code -- crash, loudly).

Call die(msg) for any of OUR error conditions: bad config, a server that will not start, a missing
model. It prints a loud banner and terminates the process hard (os._exit, no exception to catch).
Do NOT use it for third-party code that throws and must be caught -- catch those normally.
"""
import os
import sys
import traceback


def die(msg, *, trace=False):
    """Print a loud reason and crash. No return, no exception -- os._exit(1)."""
    sys.stdout.flush()
    bar = "=" * 72
    sys.stderr.write(f"\n{bar}\nFATAL: {msg}\n{bar}\n")
    if trace:
        traceback.print_stack()
    sys.stderr.flush()
    os._exit(1)
