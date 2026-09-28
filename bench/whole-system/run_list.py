#!/usr/bin/env python3
"""Text-mode run of a live-test list through the REAL Recognizer and its Gemma planner.
No mic. Every "N. <hebrew> -> <expected> | ..." line of the list is fed as text: the
parser (recognize_direct), then the ONE Gemma call (Recognizer.plan) with the number and
echo guards, exactly as the app routes it. Each line is judged against the expected
notation (dz+10 / -90 deg / takeoff / land / delay 5 / EMPTY / halt / VLM...); a line
whose expectation says "record", "or", "open" is marked REVIEW and shown, not judged.

    python3 run_list.py <list.md> [--out report.md]
    python3 run_list.py <list.md> --from-clips <session_dir>
        AUDIO REPLAY: the session's recorded push-to-talk clips go through whisper-cli
        (the node's model) instead of the list's text; each clip is matched to the list
        line it overlaps most. Isolates the language stack.

whisper runs first, then Gemma: one model on the GPU at a time.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CMD_BENCH = os.path.join(ROOT, "bench", "hebrew-command-bench")
sys.path.insert(0, CMD_BENCH)       # bench.py puts the harden2 root on sys.path itself

from bench import gemma_server                                  # noqa: E402
import config                                                   # noqa: E402
from recognizer import Recognizer, numbers_vs_mission           # noqa: E402
from recognizer import recognize_direct                         # noqa: E402
from recognizer.guards import is_shot_echo                      # noqa: E402
from util.process import native_env                             # noqa: E402

LINE_RE = re.compile(r"^\s*(\d+)\.\s*(?:NEW\s+)?(.+?)\s*->\s*(.+?)\s*(?:\|.*)?$")
REVIEW_RE = re.compile(
    r"\b(record|open|or a clean|or clean| or |should reach|reject/empty|, or )"
)
STEP_RE = re.compile(
    r"d([xyz])\s*([+-]\s*\d+(?:\.\d+)?)"
    r"|fly_by ([xyz])=([-\d.]+)"
    r"|([+-]?\d+(?:\.\d+)?)\s*deg\b"
    r"|spin_by degrees=\(?'?(?:abs'?,\s*)?([-\d.]+)\)?"
    r"|\b(takeoff|land)\b"
    r"|delay(?: seconds=|\s+)(\d+(?:\.\d+)?)"
)
TOKEN_SPLIT_RE = re.compile(r"[\s,.?!:;\-]+")
MATCH_MIN = 0.34                    # a clip below this overlap with all lines: unmatched
CLIP_DIRS = ("asr_clips", "asr/clips", "clips")     # the 2026-09-12 name, then legacy


def clips_dir(root):
    """The session's clip folder: asr_clips/ (2026-09-12), then the legacy names, so the
    2026-09-08 sessions still replay."""
    for name in CLIP_DIRS:
        path = os.path.join(root, *name.split("/"))
        if os.path.isdir(path):
            return path
    return os.path.join(root, CLIP_DIRS[0])


def transcribe(clip):
    """whisper-cli with the ASR node's model and decode settings (Hebrew forced, beam 4,
    GPU)."""
    proc = subprocess.run(
        [
            os.path.join(config.NATIVE_BIN_DIR, "whisper-cli"),
            "-m", config.ASR_MODEL_PATH,
            "-l", "he",
            "-bs", "4",
            "-nt",
            "-fa",
            "-f", clip,
        ],
        capture_output=True,
        text=True,
        env=native_env()
    )
    return " ".join(proc.stdout.split())


def tokens(text):
    return set(TOKEN_SPLIT_RE.sub(" ", text).split())


def overlap(a, b):
    """Token Jaccard overlap of two sentences."""
    ta = tokens(a)
    tb = tokens(b)
    return len(ta & tb) / max(1, len(ta | tb))


def match_clips(heard, lines):
    """Each clip goes to the list line whose Hebrew it overlaps most, so repeats, skips
    and ad-hoc sentences do not shift the alignment. The HEARD Hebrew is what the
    pipeline gets. -> (matched [(n, heard, expected)], unmatched [(clip, heard)])"""
    matched = []
    unmatched = []
    best = None
    score = 0.0
    line_score = 0.0

    for i in sorted(heard):
        best = None
        score = -1.0
        for line in lines:
            line_score = overlap(heard[i], line[1])
            if line_score > score:
                best = line
                score = line_score

        if score >= MATCH_MIN:
            matched.append((best[0], heard[i], best[2]))
        else:
            unmatched.append((i, heard[i]))
    return matched, unmatched


def parse_step(m, text):
    """One STEP_RE match -> (type, key, value|None)."""
    if m.group(1):
        return ("fly_by", "d" + m.group(1), float(m.group(2).replace(" ", "")))
    if m.group(3):
        return ("fly_by", "d" + m.group(3), float(m.group(4)))
    if m.group(5):
        return ("spin_by", "degrees", float(m.group(5)))
    if m.group(6) and "abs" in text:
        return ("spin_by", "degrees", ("abs", abs(float(m.group(6)))))
    if m.group(6):
        return ("spin_by", "degrees", float(m.group(6)))
    if m.group(7):
        return (m.group(7), None, None)
    return ("delay", "seconds", float(m.group(8)))


def parse_expected(text):
    """-> ("steps", [(type, key, value|None)]) | ("empty",) | ("halt",) | ("perception",)
    | ("review", text)"""
    t = text.strip()
    low = t.lower()

    if REVIEW_RE.search(low) and "never 0.5" not in low:
        return ("review", t)
    if (
        low.startswith("empty")
        or (" empty" in low and "mission" in low and "vlm" not in low)
    ):
        return ("empty",)
    if low.startswith("halt") or low.startswith("stop"):
        return ("halt",)
    if low.startswith("vlm") or "perception" in low or "highlight" in low:
        return ("perception",)

    steps = [parse_step(m, t) for m in STEP_RE.finditer(t)]
    if not steps:
        return ("review", t)
    return ("steps", steps)


def judge_steps(want, mission):
    """The planned mission against the expected steps, in order."""
    got = None
    value = None

    if len(mission) != len(want):
        return f"FAIL(len {len(mission)} vs {len(want)})"
    for got, (typ, key, val) in zip(mission, want):
        if got.get("type") != typ:
            return f"FAIL(type {got.get('type')} vs {typ})"
        if key is None:
            continue
        value = got.get(key)
        if value is None:
            return f"FAIL(missing {key})"
        if isinstance(val, tuple) and abs(float(value)) != val[1]:    # ('abs', 180)
            return f"FAIL({key} {value} vs |{val[1]}|)"
        if not isinstance(val, tuple) and float(value) != val:
            return f"FAIL({key} {value} vs {val})"
    if any("velocity" in step for step in mission):
        return "PASS (+velocity)"
    return "PASS"


def judge(exp, kind, mission, flags):
    last_flag = flags[-1] if flags else ""

    if exp[0] == "review":
        return "REVIEW"
    if exp[0] == "halt":
        if kind == "emergency":
            return "PASS"
        return f"FAIL(no halt: {kind})"
    if exp[0] == "perception":
        if kind == "perception":
            return "PASS"
        if kind == "reject" and flags:
            return f"FAIL(routed {kind}: {last_flag})"
        return f"FAIL(routed {kind})"
    if exp[0] == "empty":
        if kind in ("reject", "perception"):
            return f"PASS(safe: {kind})"
        if not mission:
            return "PASS"
        return f"FAIL(flew {len(mission)} steps)"

    if kind == "reject":
        return f"FAIL(reject: {last_flag})"
    if kind == "perception":
        return "FAIL(routed perception)"
    if not mission:
        return "FAIL(EMPTY)"
    return judge_steps(exp[1], mission)


def run_line(pipe, he):
    """One sentence through the Recognizer's parser and plan, routed the way handle()
    routes it, but nothing is sent. -> (kind, english_or_target, mission, flags)"""
    kind, payload, flags = recognize_direct(he)

    if kind in ("emergency", "manual", "auto"):
        return (kind, "", None, flags)
    if kind == "clear":
        return ("perception", "clear", None, flags)
    if kind == "mission":
        return ("mission", "(bypass)", payload, flags)
    if kind == "reject":
        return ("reject", "", None, flags)

    plan = pipe.plan(payload)
    if plan is None:
        flags.append("not-a-plan")
        return ("reject", "", None, flags)
    kind = plan.get("kind")
    target = (plan.get("target_en") or "").strip()
    mission = plan.get("mission") or []

    if kind in ("highlight", "count", "describe"):
        return ("perception", f"{kind}: {target}", None, flags)
    if kind == "failed":
        return ("failed", "", None, flags)
    if kind != "mission":
        flags.append("planner-reject")
        return ("reject", "", None, flags)
    missing = numbers_vs_mission(payload, mission)
    if missing:
        flags.append(f"REJECT-numbers{missing}")
        return ("reject", "", None, flags)
    if is_shot_echo(payload, mission):
        flags.append("planner-echo")
        return ("reject", "", None, flags)
    return ("command", "", mission, flags)


def read_lines(path):
    """The list's numbered lines -> [(n, hebrew, expected)]."""
    lines = []
    m = None

    with open(path, encoding="utf-8") as f:
        for text in f:
            m = LINE_RE.match(text)
            if m:
                lines.append((int(m.group(1)), m.group(2), m.group(3)))
    return lines


def replay(session, lines):
    """Transcribe the session's clips and match them to the list lines."""
    clips = sorted(glob.glob(os.path.join(clips_dir(session), "*.wav")))
    heard = {}

    print(f"[replay] {len(clips)} clips from {session}; whisper-cli ...", flush=True)
    for i, clip in enumerate(clips):
        heard[i + 1] = transcribe(clip)

    matched, unmatched = match_clips(heard, lines)
    print(
        f"[replay] matched {len(matched)} clips to list lines, "
        f"{len(unmatched)} unmatched",
        flush=True
    )
    for i, text in unmatched[:20]:
        print(f"[replay]   unmatched clip {i}: {text[:70]}", flush=True)
    return matched


def report(args, rows, wall_s):
    """The markdown report: one table row per line, then the tally."""
    mode = "AUDIO REPLAY" if args.from_clips else "Text-mode"
    title = f"# {mode} run of {os.path.basename(args.list)} -- Gemma planner"
    title += f", {time.strftime('%Y-%m-%d %H:%M')}"
    if args.from_clips:
        session = os.path.basename(args.from_clips.rstrip("/"))
        title += f" -- clips from {session}, whisper q5_k beam 4"
    out = [
        title,
        "Fed as text (no mic) through the real Recognizer and its Gemma planner, with",
        "the number and echo guards. English = the bypass or the perception kind and",
        "target. REVIEW = the list has no single expected result.",
        "",
        "| # | Hebrew | English / bypass | kind | flags | mission | expected "
        "| verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]
    tally = {"PASS": 0, "FAIL": 0, "REVIEW": 0}
    verdict = ""
    mission = ""

    for r in rows:
        verdict = judge(
            parse_expected(r["exp"]),
            r["kind"],
            r["mission"],
            r["flags"]
        )
        tally[verdict.split("(")[0].strip()] += 1
        mission = ""
        if r["mission"] is not None:
            mission = json.dumps(r["mission"], ensure_ascii=False)
            mission = mission.replace('"type": ', "").replace('"', "")
        out.append(
            f"| {r['n']} | {r['he']} | {r['en']} | {r['kind']} | "
            f"{','.join(r['flags'])} | {mission} | {r['exp'][:60]} | {verdict} |"
        )
    out.append("")
    out.append(
        f"PASS {tally['PASS']}  FAIL {tally['FAIL']}  REVIEW {tally['REVIEW']}  "
        f"(wall {round(wall_s)} s)"
    )
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("list")
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--from-clips",
        default="",
        help="session dir: replay its clips through whisper instead of the list text"
    )
    args = ap.parse_args()
    lines = read_lines(args.list)
    rows = []
    t0 = 0.0
    t1 = 0.0

    if args.from_clips:
        lines = replay(args.from_clips, lines)

    t0 = time.time()
    with gemma_server() as gemma:
        # plan() only asks Gemma: no control, no vision, nothing is sent
        pipe = Recognizer(None, None, gemma)
        for n, he, exp in lines:
            t1 = time.time()
            kind, en, mission, flags = run_line(pipe, he)
            rows.append({
                "n": n,
                "he": he,
                "exp": exp,
                "kind": kind,
                "en": en,
                "mission": mission,
                "flags": flags,
                "ms": round((time.time() - t1) * 1000),
            })

    text = report(args, rows, time.time() - t0)
    print(text)
    if not args.out:
        return
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("->", args.out)
    return


if __name__ == "__main__":
    main()
