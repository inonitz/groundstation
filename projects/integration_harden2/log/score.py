#!/usr/bin/env python3
"""Score a recorded live session against a live-test list (2026-09-09). Matches each
utterance's heard text to the best list line by token overlap after Hebrew number
normalisation (>= 0.3), parses the list's expected notation (dz+20, +45 deg, takeoff,
land, delay N, EMPTY, halt, open, VLM: ...) and judges the recorded mission. Writes
REPORT.md into the session folder.
    python3 log/score.py <list.md> <session dir>
    e.g. tools/desk-test/live-test-e2e-50.md
         logs/sessions/<latest>   (the default: the newest under config.SESSIONS_ROOT)"""
import json
import os
import re
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(
    0,
    os.path.join(ROOT, "projects", os.environ.get("MVD_HOME", "integration_harden2"))
)
from log.session import latest_session, trace_file
from util.hebrew import hebnum_to_digits
from util.mission import step_text


# ---- read the test list and match an utterance to its line ----

def norm(s):
    digits = hebnum_to_digits(s)
    return re.sub(r"[^\w\s]", " ", digits).split()


def parse_list(p):
    out = []
    with open(p, encoding="utf-8") as fh:
        text = fh.read()

    for m in re.finditer(r"^(\d+)\. (.*?) -> (.*?)(?: \| .*)?$", text, re.M):
        out.append((int(m.group(1)), m.group(2).strip(), m.group(3).strip()))
    return out


def match(heard, lines, last):
    """Best line by token overlap (Jaccard); a line just after the last match gets a
    small bonus, because the tester reads the list in order."""
    best = (0.0, None)
    heard_tokens = set(norm(heard))
    line_tokens = set()
    bonus = 0
    j = 0.0

    for n, he, exp in lines:
        line_tokens = set(norm(he))
        bonus = 0.05 if 0 <= n - last <= 2 else 0
        j = (
            len(heard_tokens & line_tokens) / max(1, len(heard_tokens | line_tokens))
            + bonus
        )
        if j > best[0]:
            best = (j, (n, he, exp))
    return best[1] if best[0] >= 0.3 else None


# ---- parse the expected notation of one line ----

def _parse_spin(p):
    """'+45 deg' -> 45.0; '90 deg (either way)' -> ("abs", 90.0); unparsable -> None."""
    m = re.search(r"([+-]?\d+(?:\.\d+)?) ?deg(?: \(either way\))?", p)
    if not m:
        return None
    if "either" in p:
        return ("abs", float(m.group(1)))
    return float(m.group(1))


def _parse_step(p):
    """One comma-separated step -> (type, field, value)."""
    m = None

    if p.startswith("takeoff"):
        return ("takeoff", None, None)
    if p.startswith("land"):
        return ("land", None, None)
    if p.startswith("delay"):
        m = re.search(r"[\d.]+", p)
        return ("delay", "seconds", float(m.group()) if m else None)
    if "deg" in p:
        return ("spin_by", "degrees", _parse_spin(p))

    m = re.search(r"d([xyz])\s*([+-]\d+(?:\.\d+)?)", p)
    if not m:
        return ("?", None, None)
    return ("fly_by", m.group(1), float(m.group(2)))


def parse_exp(exp):
    e = exp.lower()
    steps = []
    p = ""

    if e.startswith("vlm"):
        return ("vlm", None)
    if e.startswith("halt"):
        return ("halt", None)
    if e.startswith("empty"):
        return ("empty", None)
    if e.startswith("open") or "record" in e:
        return ("open", None)

    for part in exp.split(","):
        p = part.strip()
        if not p:
            continue
        steps.append(_parse_step(p))
    return ("steps", steps)


# ---- judge the recorded utterance against the expectation ----

def _judge_step(s, t, k, v):
    """One flown step against one expected step -> a FAIL note, or None when it fits."""
    g = None

    if s.get("type") != t:
        return f"{s.get('type')} vs {t}"
    if not k or v is None:
        return None

    g = s.get("d" + k) if t == "fly_by" else s.get(k)
    if g is None:
        return f"missing {k}"
    if isinstance(v, tuple):
        # ("abs", N): either turn direction passes.
        if abs(abs(float(g)) - v[1]) > 0.01:
            return f"{k} {g} vs {v[1]}"
        return None
    if abs(float(g) - v) > 0.01:
        return f"{k} {g} vs {v}"
    return None


def judge(kind, steps, r):
    act = r.get("action") or ""
    mis = r.get("mission")
    halted = False
    empty = False
    note = None

    if kind == "vlm":
        return ("PASS" if act.startswith("perception") else "FAIL", f"routed {act[:22]}")
    if kind == "halt":
        halted = act in ("stop", "emergency-halt(backup)") or "halt" in act
        return ("PASS" if halted else "FAIL", act[:22])
    if kind == "empty":
        empty = (not mis) and not act.startswith("mission")
        return ("PASS" if empty else "FAIL", act[:22])
    if kind == "open":
        return ("REVIEW", act[:22])

    if not isinstance(mis, list) or not mis:
        return ("FAIL", f"nothing flew: {act[:20]}")
    if len(mis) != len(steps):
        return ("FAIL", f"{len(mis)} steps vs {len(steps)}")
    for s, (t, k, v) in zip(mis, steps):
        note = _judge_step(s, t, k, v)
        if note is not None:
            return ("FAIL", note)
    return ("PASS", "")


# ---- write the report ----

def _mission_text(mis):
    """The recorded mission as one line: 'type k=v k=v; type ...', or '-'."""
    if not isinstance(mis, list):
        return "-"
    return "; ".join(step_text(s) for s in mis)


def main(list_path, sd):
    with open(trace_file(sd), encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    lines = parse_list(list_path)
    out = [
        f"# Live review — {os.path.basename(sd)} vs {os.path.basename(list_path)}",
        "",
        "| # | heard | line | expected | action | mission | verdict | note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    counts = {
        "PASS": 0,
        "FAIL": 0,
        "REVIEW": 0,
        "unmatched": 0,
    }
    last = 0
    fails = []
    m = None
    ms = ""
    n = 0
    exp = ""
    kind = ""
    steps = None
    v = ""
    note = ""

    for i, r in enumerate(rows, 1):
        m = match(r.get("heard_he", ""), lines, last)
        ms = _mission_text(r.get("mission"))

        if not m:
            counts["unmatched"] += 1
            out.append(
                f"| {i} | {r.get('heard_he','')[:55]} | - | (ad-hoc / misheard) | "
                f"{r.get('action','')[:30]} | {ms[:60]} | - | |"
            )
            continue

        n, _, exp = m
        last = n
        kind, steps = parse_exp(exp)
        v, note = judge(kind, steps, r)
        counts[v] += 1
        if v != "PASS":
            fails.append((
                i,
                n,
                r.get("heard_he", "")[:50],
                exp[:40],
                r.get("action", "")[:28],
                ms[:50],
                v,
                note
            ))
        out.append(
            f"| {i} | {r.get('heard_he','')[:55]} | {n} | {exp[:45]} | "
            f"{r.get('action','')[:30]} | {ms[:60]} | {v} | {note} |"
        )

    out.insert(
        2,
        f"Counts: PASS {counts['PASS']}, FAIL {counts['FAIL']}, "
        f"REVIEW {counts['REVIEW']}, unmatched {counts['unmatched']} "
        f"(of {len(rows)} utterances)."
    )
    out.insert(3, "")
    with open(os.path.join(sd, "REPORT.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print(out[2])
    print("non-PASS:")
    for f in fails:
        print("  utt %2d line %2d | %s | exp %s | %s | %s | %s %s" % f)
    return


if __name__ == "__main__":
    main(
        sys.argv[1],
        sys.argv[2] if len(sys.argv) > 2 else latest_session()
    )
