#!/usr/bin/env python3
"""The recognizer benchmark: "a benchmark of the recognizer as a function of the backend"
(owner 2026-09-27). Path A: JSON sentence files -> Recognizer.route() -> scorer.score().

route() is the app's own decide step (the guards included), so no routing is copied here.
It sends nothing: the Recognizer gets no control and no vision.

    python3 accuracy.py                        every topical file: each sentence once
    python3 accuracy.py FILE.json [FILE ...]   only these files (topical files or lists)
    --list NAME   run one live list (datasets/recognizer/NAME.json), in its order
    --print NAME  print one live list in order, the Hebrew drawn right to left; no Gemma
    --port P      a llama-server already up on port P (another backend); default: start
                  Gemma the way the app does, on the bench port
    --thinking    start Gemma with thinking on
    --first N     only the first N cases of each file (a quick look)
    --tag T       the results' name (default: the backend)

Results: bench/recognizer/results/<date>-<tag>.json (every case) and .md (the table).
Path B (task B2, not built): a case with "wav" gets whisper's text first, then path A.
"""
import argparse
import datetime
import glob
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "projects", "integration_harden2"))

from bidi.algorithm import get_display       # noqa: E402  a terminal draws Hebrew LTR
import config                                                   # noqa: E402
from gemma import server as gemma_process                       # noqa: E402
from gemma.client import Gemma                                  # noqa: E402
from recognizer import Recognizer                               # noqa: E402
from runtime.fatal import die                                    # noqa: E402
from runtime.supervisor import Supervisor                        # noqa: E402
from scorer import score                                        # noqa: E402

DATASET_DIR = os.path.join(ROOT, "datasets", "recognizer")
RESULTS_DIR = os.path.join(HERE, "results")
BENCH_PORT = 18091                  # never the app's Gemma port
START_TIMEOUT_S = 300


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def topical_files():
    """Every file that holds sentences ("set"). A live list ("list") holds only the
    names of cases, in the order a person speaks them (owner J5, 2026-09-29)."""
    out = []
    for path in sorted(glob.glob(os.path.join(DATASET_DIR, "*.json"))):
        if "set" in read(path):
            out.append(path)
    return out


def case_pool():
    """Every case of the topical files, by name. Each sentence has one home."""
    pool = {}
    for path in topical_files():
        for case in read(path)["cases"]:
            if case["name"] in pool:
                die(f"{path}: the case name {case['name']} is used twice")
            pool[case["name"]] = case
    return pool


def load(path):
    """-> (name, cases). A live list is resolved through the topical files. A recordings
    file (path B) is task B2."""
    data = read(path)
    if "list" in data:
        pool = case_pool()
        return data["list"], [pool[name] for name in data["cases"]]
    for case in data["cases"]:
        if "wav" in case:
            die(f"{path}: a recordings file is path B (task B2), not built yet")
    return data["set"], data["cases"]


def expect_text(expect):
    """An expect as one short line: the kind, then the steps or the keyword groups."""
    if expect["kind"] == "mission":
        return "mission " + ", ".join(
            " ".join(str(part) for part in step if part is not None)
            for step in expect["steps"]
        )
    if expect["kind"] == "perception":
        return "perception " + " + ".join("|".join(g) for g in expect["groups"])
    return expect["kind"]


def print_list(name):
    """One live list, in order: number, case name, the Hebrew, the expected result."""
    _list, cases = load(os.path.join(DATASET_DIR, name + ".json"))
    for i, case in enumerate(cases):
        print(f"{i + 1:3d}. {case['name']:<24} {get_display(case['he'])}")
        print(f"     -> {expect_text(case['expect'])}")
    return


def run_file(recognizer, cases):
    """Every case through route() and the scorer. -> rows."""
    rows = []
    t0 = 0.0

    for case in cases:
        t0 = time.monotonic()
        decision = recognizer.route(case["he"])
        ms = round((time.monotonic() - t0) * 1000)
        verdict, reason = score(case["expect"], decision)
        rows.append({
            "name": case["name"],
            "he": case["he"],
            "expect": case["expect"],
            "kind": decision.kind,
            "tag": decision.tag,
            "mission": decision.mission,
            "target": decision.target,
            "action": decision.action,
            "flags": decision.flags,
            "verdict": verdict,
            "reason": reason,
            "ms": ms,
        })
        if verdict == "FAIL":
            print(f"  FAIL {case['name']}: {reason}", flush=True)
    return rows


def tally(rows):
    counts = {"PASS": 0, "FAIL": 0, "REVIEW": 0}
    for row in rows:
        counts[row["verdict"]] += 1
    return counts


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


def report(backend, results, wall_s):
    """The markdown table: one row per file, then the total and the latency."""
    lines = [
        f"# Recognizer accuracy, {backend}",
        "",
        f"{datetime.datetime.now():%Y-%m-%d %H:%M}; wall {round(wall_s)} s.",
        "",
        "| set | cases | PASS | FAIL | REVIEW |",
        "|---|---|---|---|---|",
    ]
    total = {"PASS": 0, "FAIL": 0, "REVIEW": 0}
    ms = []

    for name, rows in results.items():
        counts = tally(rows)
        for key in total:
            total[key] += counts[key]
        ms += [row["ms"] for row in rows]
        lines.append(
            f"| {name} | {len(rows)} | {counts['PASS']} | {counts['FAIL']} "
            f"| {counts['REVIEW']} |"
        )
    lines.append(
        f"| ALL | {len(ms)} | {total['PASS']} | {total['FAIL']} "
        f"| {total['REVIEW']} |"
    )
    lines.append("")
    lines.append(
        f"route() per case: P50 {percentile(ms, 0.5)} ms, "
        f"P95 {percentile(ms, 0.95)} ms, max {max(ms)} ms."
    )
    return "\n".join(lines)


def start_gemma(supervisor, thinking):
    """Start Gemma the way the app does (supervisor + gemma.server.process), on the bench
    port. -> the client."""
    log_dir = tempfile.mkdtemp(prefix="bench-gemma-")
    spec = gemma_process.process(log_dir, port=BENCH_PORT, thinking=thinking)
    if not supervisor.start(spec).wait_up(START_TIMEOUT_S):
        supervisor.stop_all()
        die(f"Gemma was not ready after {START_TIMEOUT_S} s; log: {log_dir}")
    return Gemma(BENCH_PORT)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--list", default="")
    ap.add_argument("--print", default="", dest="print_name")
    args = ap.parse_args()
    files = args.files or topical_files()
    supervisor = Supervisor()
    results = {}
    t0 = time.time()

    if args.print_name:
        print_list(args.print_name)
        return
    if args.list:
        files = [os.path.join(DATASET_DIR, args.list + ".json")]
    if args.port and not gemma_process.port_up(args.port):
        die(f"no llama-server answers on port {args.port}")
    backend = f"llama-server on port {args.port}"
    if not args.port:
        backend = os.path.basename(config.GEMMA_MODEL_PATH)
        backend += ", thinking " + ("on" if args.thinking else "off")
    print(f"[accuracy] backend: {backend}; {len(files)} files", flush=True)

    if args.port:
        gemma = Gemma(args.port)
    else:
        gemma = start_gemma(supervisor, args.thinking)
    # route() decides only: no control and no vision, so nothing can be sent
    recognizer = Recognizer(None, None, gemma)

    for path in files:
        name, cases = load(path)
        if args.first:
            cases = cases[:args.first]
        print(f"[accuracy] {name}: {len(cases)} cases", flush=True)
        results[name] = run_file(recognizer, cases)
    supervisor.stop_all()

    text = report(backend, results, time.time() - t0)
    print(text)
    tag = args.tag or backend.split(",")[0].replace(" ", "-")
    stem = os.path.join(RESULTS_DIR, f"{datetime.date.today()}-{tag}")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(stem + ".json", "w", encoding="utf-8") as f:
        json.dump(
            {"backend": backend, "results": results},
            f,
            ensure_ascii=False,
            indent=1
        )
    with open(stem + ".md", "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(f"[accuracy] -> {stem}.md", flush=True)
    return


if __name__ == "__main__":
    main()
