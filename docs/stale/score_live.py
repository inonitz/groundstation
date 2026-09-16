def _u(root):  # the per-utterance log: trace.jsonl (2026-09-12), then legacy utterances.jsonl layouts
    import os as _o
    for c in ("trace.jsonl", "asr/utterances.jsonl", "utterances.jsonl"):
        p = _o.path.join(root, *c.split("/"))
        if _o.path.exists(p):
            return p
    return _o.path.join(root, "trace.jsonl")

#!/usr/bin/env python3
"""Side-by-side view of a live-test list and a recorded session, aligned by order.
Usage: python3 score_live.py <list.md> [session_dir|latest] [--offset N]
Each row: list line N (sentence -> expected) above what the recorder logged for utterance N+offset:
heard Hebrew, English, kind/action, wire mission. Scoring is by eye (or by the agent); this only aligns."""
import json, os, re, sys, glob
args = [a for a in sys.argv[1:] if not a.startswith("--")]
offset = int(sys.argv[sys.argv.index("--offset") + 1]) if "--offset" in sys.argv else 0
listfile = args[0]
sess = args[1] if len(args) > 1 else "latest"
root = os.path.join(os.path.dirname(__file__), "..", "..", "projects", "integration_harden", "sessions")
if sess == "latest":
    sess = sorted(glob.glob(os.path.join(root, "session-*")))[-1]
lines = []
for line in open(listfile, encoding="utf-8"):
    m = re.match(r"^\s*(\d+)\.\s*(?:NEW\s+)?(.+?)\s*->\s*(.+?)\s*(?:\|.*)?$", line)
    if m:
        lines.append((int(m.group(1)), m.group(2), m.group(3)))
recs = [json.loads(l) for l in open(_u(sess), encoding="utf-8")]
print(f"list: {listfile} ({len(lines)} lines)   session: {sess} ({len(recs)} utterances)   offset {offset}\n")
for i, (n, he, exp) in enumerate(lines):
    j = i + offset
    print(f"#{n:>2}  SAID : {he}\n     WANT : {exp}")
    if 0 <= j < len(recs):
        r = recs[j]
        print(f"     HEARD: {r.get('heard_he', '')}")
        if r.get("english"):
            print(f"     EN   : {r['english']}")
        print(f"     GOT  : [{r.get('kind') or '?'}] {r.get('action') or ''}  wire={json.dumps(r.get('mission'), ensure_ascii=False)}")
    else:
        print("     (no utterance recorded at this position)")
    print()
