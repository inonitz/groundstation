#!/usr/bin/env python3
"""Pretty-print a desk-test session's recorded utterances: heard Hebrew, English, the
mission sent.
Usage:  python3 log/show.py [session_dir | latest]   (default: latest)"""
import json
import os
import sys


# harden2 root
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from log.session import latest_session, trace_file


def _pick_session(arg):
    """'latest' -> the newest session folder; else arg."""
    if arg != "latest":
        return arg
    return latest_session()


def _print_utterance(n, r):
    print(f'\n#{n}  {r.get("ts","")}  [{r.get("kind") or "?"}]  ({r.get("source","")})')
    print(f'   heard : {r.get("heard_he","")}')
    if r.get("english"):
        print(f'   en    : {r["english"]}')
    if r.get("mission") is not None:
        print(f'   dji   : {json.dumps(r["mission"], ensure_ascii=False)}')
    if r.get("action"):
        print(f'   action: {r["action"]}')
    return


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "latest"
    sdir = _pick_session(arg)
    jl = trace_file(sdir)
    n = 0
    r = None

    print("session:", sdir)
    if not os.path.exists(jl):
        print(f"no {os.path.basename(jl)} yet")
        return

    with open(jl, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            n += 1
            _print_utterance(n, r)
    print(f'\n{n} utterances in {sdir}')
    return


if __name__ == "__main__":
    main()
