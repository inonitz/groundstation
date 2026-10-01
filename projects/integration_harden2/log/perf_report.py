#!/usr/bin/env python3
"""Summarize a session's perf.jsonl (owner rulings C.1 and V1 a, 2026-09-28): per stage
n, min, P25, P50, P75, P95, P99, max; the GPU peaks; then the slowest frames with their
times, so they can be matched to the other events of that moment.
    python3 log/perf_report.py [session_dir | latest]      (run.sh perf)"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config  # noqa: E402
from log.session_files import latest_session  # noqa: E402

PERCENTILES = (25, 50, 75, 95, 99)
# a field of a stage's events that gets its own row under the stage: (field, label)
PARTS = {
    "sam3": [("wait_ms", "of which waiting for the lock")],
    "frame": [("read_ms", "read"), ("draw_ms", "draw"), ("show_ms", "show")],
}
# a field that splits a stage into groups: "gemma (plan)", "e2e (ptt) (command)"
GROUP_FIELDS = ("label", "kind", "output", "row", "start", "end")


def percentile(values, p):
    """The p-th percentile (0-100) of a non-empty list, nearest rank."""
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(p / 100 * len(ordered)) - 1))
    return ordered[rank]


def summarize(rows):
    """-> {key: [rows]}; key is the stage, plus its label, kind, output or row."""
    groups = {}
    key = ""

    for row in rows:
        key = row["stage"]
        for extra in GROUP_FIELDS:
            if extra in row:
                key += f" ({row[extra]})"
        groups.setdefault(key, []).append(row)
    return groups


def stats_line(name, values):
    """One table row: name, n, min, the percentiles, max (ms, one decimal)."""
    cells = [min(values)]
    cells.extend(percentile(values, p) for p in PERCENTILES)
    cells.append(max(values))
    numbers = " ".join(f"{v:8.1f}" for v in cells)
    return f"{name:34s} {len(values):6d} {numbers}"


def stage_table(rows):
    """The stats table: one row per stage group, and one per part of a stage."""
    heads = ["min"] + [f"P{p}" for p in PERCENTILES] + ["max"]
    lines = [f"{'stage (ms)':34s} {'n':>6s} " + " ".join(f"{h:>8s}" for h in heads)]
    stage = ""

    for key, group in sorted(summarize(rows).items()):
        stage = group[0]["stage"]
        if stage == "gpu":
            continue
        lines.append(stats_line(key, [r["ms"] for r in group]))
        for field, label in PARTS.get(stage, []):
            lines.append(stats_line("  " + label, [r.get(field, 0) for r in group]))
    return lines


def gpu_line(rows):
    gpu = [r for r in rows if r["stage"] == "gpu"]
    if not gpu:
        return []
    load = [r["load_pct"] for r in gpu]
    return [
        f"gpu: {len(gpu)} samples; memory max {max(r['mem_mib'] for r in gpu)} MiB; "
        f"load P50 {percentile(load, 50)} %, max {max(load)} %"
    ]


def slowest_frames(rows, count):
    """The `count` frames with the longest gap, slowest first, with their wall time."""
    frames = [r for r in rows if r["stage"] == "frame"]
    if not frames:
        return []

    slowest = sorted(frames, key=lambda r: r["ms"], reverse=True)[:count]
    lines = [
        f"the {len(slowest)} slowest frames of {len(frames)} "
        "(gap = the time since the previous frame):",
        f"{'time':>12s} {'gap ms':>8s} {'read':>8s} {'draw':>8s} {'show':>8s}",
    ]
    for r in slowest:
        stamp = datetime.fromtimestamp(r["t"]).strftime("%H:%M:%S.%f")[:-3]
        lines.append(
            f"{stamp} {r['ms']:8.1f} {r['read_ms']:8.1f} "
            f"{r['draw_ms']:8.1f} {r['show_ms']:8.1f}"
        )
    return lines


def report(session_dir, slowest=config.PERF_SLOWEST_FRAMES):
    path = os.path.join(session_dir, "perf.jsonl")
    rows = []
    if not os.path.exists(path):
        return [f"no perf.jsonl in {session_dir}"]

    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]

    lines = [f"# perf: {os.path.basename(session_dir)} ({len(rows)} events)"]
    lines.extend(stage_table(rows))
    lines.extend(gpu_line(rows))
    lines.extend(slowest_frames(rows, slowest))
    return lines


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "latest"
    session_dir = latest_session() if arg == "latest" else arg
    print("\n".join(report(session_dir)))
    return


if __name__ == "__main__":
    main()
