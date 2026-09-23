#!/usr/bin/env python3
"""Score a recorded live session against a live-test list (2026-09-09). Matches each utterance's heard text to the best list
line by token overlap after Hebrew number normalisation (>= 0.3), parses the list's expected notation (dz+20, +45 deg, takeoff,
land, delay N, EMPTY, halt, open, VLM: ...) and judges the recorded mission. Writes REPORT.md into the session folder.
    python3 score_session.py <list.md> <session dir>        e.g. tools/desk-test/live-test-e2e-50.md projects/integration_harden2/sessions/<latest>"""
import json, re, sys, os


def _u(root):  # the per-utterance log: trace.jsonl (2026-09-12), then legacy utterances.jsonl layouts
    import os as _o
    for c in ("trace.jsonl", "asr/utterances.jsonl", "utterances.jsonl"):
        p = _o.path.join(root, *c.split("/"))
        if _o.path.exists(p):
            return p
    return _o.path.join(root, "trace.jsonl")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "projects", os.environ.get("MVD_HOME", "integration_harden2"), "recognizer"))
from recognizer import hebnum_to_digits

def norm(s): return re.sub(r"[^\w\s]", " ", hebnum_to_digits(s)).split()
def parse_list(p):
    out = []
    for m in re.finditer(r"^(\d+)\. (.*?) -> (.*?)(?: \| .*)?$", open(p, encoding="utf-8").read(), re.M):
        out.append((int(m.group(1)), m.group(2).strip(), m.group(3).strip()))
    return out
def match(heard, lines, last):
    best = (0.0, None)
    for n, he, exp in lines:
        a, b = set(norm(heard)), set(norm(he)); j = len(a & b) / max(1, len(a | b)) + (0.05 if 0 <= n - last <= 2 else 0)
        if j > best[0]: best = (j, (n, he, exp))
    return best[1] if best[0] >= 0.3 else None
def parse_exp(exp):
    e = exp.lower()
    if e.startswith("vlm"): return ("vlm", None)
    if e.startswith("halt"): return ("halt", None)
    if e.startswith("empty"): return ("empty", None)
    if e.startswith("open") or "record" in e: return ("open", None)
    steps = []
    for part in exp.split(","):
        p = part.strip()
        if not p: continue
        if p.startswith("takeoff"): steps.append(("takeoff", None, None))
        elif p.startswith("land"): steps.append(("land", None, None))
        elif p.startswith("delay"): m = re.search(r"[\d.]+", p); steps.append(("delay", "seconds", float(m.group()) if m else None))
        elif "deg" in p:
            m = re.search(r"([+-]?\d+(?:\.\d+)?) ?deg(?: \(either way\))?", p)
            steps.append(("spin_by", "degrees", (("abs", float(m.group(1))) if "either" in p else float(m.group(1))) if m else None))
        else:
            m = re.search(r"d([xyz])\s*([+-]\d+(?:\.\d+)?)", p)
            steps.append(("fly_by", m.group(1), float(m.group(2))) if m else ("?", None, None))
    return ("steps", steps)
def judge(kind, steps, r):
    act = r.get("action") or ""; mis = r.get("mission")
    if kind == "vlm": return ("PASS" if act.startswith("perception") else "FAIL", f"routed {act[:22]}")
    if kind == "halt": return ("PASS" if act in ("stop", "emergency-halt(backup)") or "halt" in act else "FAIL", act[:22])
    if kind == "empty": return ("PASS" if (not mis) and not act.startswith("mission") else "FAIL", act[:22])
    if kind == "open": return ("REVIEW", act[:22])
    if not isinstance(mis, list) or not mis: return ("FAIL", f"nothing flew: {act[:20]}")
    if len(mis) != len(steps): return ("FAIL", f"{len(mis)} steps vs {len(steps)}")
    for s, (t, k, v) in zip(mis, steps):
        if s.get("type") != t: return ("FAIL", f"{s.get('type')} vs {t}")
        if k and v is not None:
            g = s.get("d" + k) if t == "fly_by" else s.get(k)
            if g is None: return ("FAIL", f"missing {k}")
            if isinstance(v, tuple):
                if abs(abs(float(g)) - v[1]) > 0.01: return ("FAIL", f"{k} {g} vs {v[1]}")
            elif abs(float(g) - v) > 0.01: return ("FAIL", f"{k} {g} vs {v}")
    return ("PASS", "")
def main(list_path, sd):
    rows = [json.loads(l) for l in open(_u(sd), encoding="utf-8")]; lines = parse_list(list_path)
    out = [f"# Live review — {os.path.basename(sd)} vs {os.path.basename(list_path)}", "", "| # | heard | line | expected | action | mission | verdict | note |", "|---|---|---|---|---|---|---|---|"]
    counts = {"PASS": 0, "FAIL": 0, "REVIEW": 0, "unmatched": 0}; last = 0; fails = []
    for i, r in enumerate(rows, 1):
        m = match(r.get("heard_he", ""), lines, last); mis = r.get("mission")
        ms = ("; ".join(f"{s.get('type')}" + "".join(f" {k}={v}" for k, v in s.items() if k != "type") for s in mis) if isinstance(mis, list) else "-")
        if m:
            n, he, exp = m; last = n; kind, steps = parse_exp(exp); v, note = judge(kind, steps, r); counts[v] += 1
            if v != "PASS": fails.append((i, n, r.get("heard_he", "")[:50], exp[:40], r.get("action", "")[:28], ms[:50], v, note))
            out.append(f"| {i} | {r.get('heard_he','')[:55]} | {n} | {exp[:45]} | {r.get('action','')[:30]} | {ms[:60]} | {v} | {note} |")
        else:
            counts["unmatched"] += 1; out.append(f"| {i} | {r.get('heard_he','')[:55]} | - | (ad-hoc / misheard) | {r.get('action','')[:30]} | {ms[:60]} | - | |")
    out.insert(2, f"Counts: PASS {counts['PASS']}, FAIL {counts['FAIL']}, REVIEW {counts['REVIEW']}, unmatched {counts['unmatched']} (of {len(rows)} utterances)."); out.insert(3, "")
    open(os.path.join(sd, "REPORT.md"), "w", encoding="utf-8").write("\n".join(out) + "\n"); print(out[2]); print("non-PASS:")
    for f in fails: print("  utt %2d line %2d | %s | exp %s | %s | %s | %s %s" % f)
if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else sorted(__import__("glob").glob(os.path.join(ROOT, "logs", "sessions", "session-*")))[-1])
