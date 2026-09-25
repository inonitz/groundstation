#!/usr/bin/env python3
"""Summarize a session's perf.jsonl: p50 / p95 / max per stage, the frame rate, the GPU
peaks.
    python3 log/perf_report.py [session_dir | latest]      (run.sh perf)"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from log.session import latest_session  # noqa: E402


def percentile(values, p):
    """The p-th percentile (0-100) of a non-empty list, nearest rank."""
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(p / 100 * len(ordered)) - 1))
    return ordered[rank]


def summarize(rows):
    """-> {key: [rows]}; key is the stage, plus its label or kind when it has one."""
    groups = {}
    key = ""

    for row in rows:
        key = row["stage"]
        for extra in ("label", "kind", "output"):
            if extra in row:
                key += f" ({row[extra]})"
        groups.setdefault(key, []).append(row)
    return groups


def report(session_dir):
    lines = []
    path = os.path.join(session_dir, "perf.jsonl")
    if not os.path.exists(path):
        return [f"no perf.jsonl in {session_dir}"]

    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]

    lines.append(f"# perf: {os.path.basename(session_dir)} ({len(rows)} events)")
    lines.append(f"{'stage':32s} {'n':>5s} {'p50 ms':>9s} {'p95 ms':>9s} {'max ms':>9s}")
    for key, group in sorted(summarize(rows).items()):
        if key in ("gpu", "frame"):
            continue
        ms = [r["ms"] for r in group]
        lines.append(
            f"{key:32s} {len(ms):5d} {percentile(ms, 50):9.0f} "
            f"{percentile(ms, 95):9.0f} {max(ms):9.0f}"
        )
        if key == "sam3":
            waits = [r.get("wait_ms", 0) for r in group]
            lines.append(
                f"{'  of which waiting for the lock':32s} {len(waits):5d} "
                f"{percentile(waits, 50):9.0f} {percentile(waits, 95):9.0f} "
                f"{max(waits):9.0f}"
            )

    frames = [r for r in rows if r["stage"] == "frame"]
    if frames:
        fps = [r["fps"] for r in frames]
        lines.append(
            f"frame loop: fps p50 {percentile(fps, 50)}, min {min(fps)}; loop ms p50 "
            f"{percentile([r['ms'] for r in frames], 50):.0f} (read / draw / show p50: "
            f"{percentile([r['read_ms'] for r in frames], 50):.0f} / "
            f"{percentile([r['draw_ms'] for r in frames], 50):.0f} / "
            f"{percentile([r['show_ms'] for r in frames], 50):.0f})"
        )
    gpu = [r for r in rows if r["stage"] == "gpu"]
    if gpu:
        lines.append(
            f"gpu: memory max {max(r['mem_mib'] for r in gpu)} MiB, load p50 "
            f"{percentile([r['load_pct'] for r in gpu], 50)} %, max "
            f"{max(r['load_pct'] for r in gpu)} %"
        )
    return lines


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "latest"
    session_dir = latest_session() if arg == "latest" else arg
    print("\n".join(report(session_dir)))
    return


if __name__ == "__main__":
    main()
