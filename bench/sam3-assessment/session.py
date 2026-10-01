"""SAM3 in a real app session: each "sam3" perf record (one detect) matched to its
perception task, the task's concept count (perception2.concept.phrase_concepts), and
whether a Gemma request or an ASR pass ran at the same time. This replaces the synthetic
cadence of bench/hebrew-command-bench/real_cadence.py with the app's own record.
No GPU. Run: python3 bench/sam3-assessment/session.py <session folder>"""
import glob
import json
import os
import sys

import common
from perception2.concept import phrase_concepts

MATCH_S = 0.05       # a pass file is written right after its perf record


def intervals(events, stage):
    out = []
    for event in events:
        if event["stage"] == stage:
            out.append((event["t"] - event["ms"] / 1000, event["t"]))
    return out


def overlaps(start, end, spans):
    for other_start, other_end in spans:
        if other_start < end and other_end > start:
            return True
    return False


def pass_concepts(folder):
    """[(pass end time, concept count)] from every perception pass file."""
    out = []
    request = None
    for task in sorted(glob.glob(os.path.join(folder, "perception", "*"))):
        with open(os.path.join(task, "request.json")) as src:
            request = json.load(src)
        if request.get("kind") not in ("highlight", "count"):
            continue
        n = len(phrase_concepts(request["target_en"]).split(","))
        for path in glob.glob(os.path.join(task, "pass_*.json")):
            with open(path) as src:
                out.append((json.load(src)["t"], n))
    return out


def concepts_at(t, passes):
    for end, n in passes:
        if abs(end - t) < MATCH_S:
            return n
    return "?"          # a pass with no file (a highlight refresh): task unknown


def main():
    folder = sys.argv[1]
    with open(os.path.join(folder, "perf.jsonl")) as src:
        events = [json.loads(line) for line in src]
    gemma = intervals(events, "gemma")
    asr = intervals(events, "asr")
    passes = pass_concepts(folder)
    groups = {}
    key = ""
    start = 0.0

    for event in events:
        if event["stage"] != "sam3":
            continue
        start = event["t"] - event["ms"] / 1000
        key = f"concepts={concepts_at(event['t'], passes)}"
        if overlaps(start, event["t"], gemma + asr):
            key += " gemma/asr busy"
        groups.setdefault(key, []).append(event["ms"])
    everything = [ms for values in groups.values() for ms in values]
    results = {"session": os.path.basename(folder), "all": common.stats(everything)}
    for key in sorted(groups):
        results[key] = common.stats(groups[key])
    for key, row in results.items():
        print(f"{key:32s} {row}", flush=True)
    common.write_result("session", results)
    return


if __name__ == "__main__":
    main()
