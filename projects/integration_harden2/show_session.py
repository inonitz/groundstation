#!/usr/bin/env python3
"""Pretty-print a desk-test session's recorded utterances: heard Hebrew, English, wire mission.
Usage:  python3 show_session.py [session_dir | latest]   (default: latest)"""
import json, os, sys, glob


def _u(root):  # the per-utterance log: trace.jsonl (2026-09-12), then legacy utterances.jsonl layouts
    import os as _o
    for c in ("trace.jsonl", "asr/utterances.jsonl", "utterances.jsonl"):
        p = _o.path.join(root, *c.split("/"))
        if _o.path.exists(p):
            return p
    return _o.path.join(root, "trace.jsonl")
root = os.environ.get("MVD_SESSION_DIR") or \
    os.path.join(os.path.dirname(__file__), "..", "..", "logs", "sessions")
arg = sys.argv[1] if len(sys.argv) > 1 else "latest"
if arg == "latest":
    dirs = sorted(glob.glob(os.path.join(root, "session-*")))
    if not dirs:
        print("no sessions under", os.path.abspath(root)); sys.exit(1)
    sdir = dirs[-1]
else:
    sdir = arg
jl = _u(sdir)
print("session:", sdir)
if not os.path.exists(jl):
    print("no utterances.jsonl yet"); sys.exit(0)
n = 0
for line in open(jl, encoding="utf-8"):
    r = json.loads(line); n += 1
    print(f'\n#{n}  {r.get("ts","")}  [{r.get("kind") or "?"}]  ({r.get("source","")})')
    print(f'   heard : {r.get("heard_he","")}')
    if r.get("english"):          print(f'   en    : {r["english"]}')
    if r.get("mission") is not None: print(f'   wire  : {json.dumps(r["mission"], ensure_ascii=False)}')
    if r.get("action"):           print(f'   action: {r["action"]}')
print(f'\n{n} utterances in {sdir}')
