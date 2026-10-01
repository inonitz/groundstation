#!/usr/bin/env python3
"""A/B of SAM3's shared image encoding (owner S1, 2026-09-29: "Just bench it to make
sure"). For every labelled row, every concept the vision system asks SAM3 about (the
head concepts and the related nouns) runs two ways on the same frame:
    per_concept  the full model once per concept (the old detect(): Sam3Backend._run)
    shared       the frame encoded once (_encode), then per concept only the text and
                 detector step (_run_concept), as detect() does now
Pass: the same number of boxes per concept, and every box within 2 px of its partner.
Also reports the time of each path per row (all of its concepts).

Run (GPU, ~3 min; take the gpu lock):
    python3 /root/groundstation/bench/perception/ab_shared_encoding.py [--labels human]
Writes results/<date>-ab-shared-encoding.json."""
import json
import os
import sys
import time

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402  (the dataset helpers; it puts harden2 on sys.path)
from perception2.concept import phrase_concepts  # noqa: E402
from sam3.model import Sam3Backend  # noqa: E402

TOLERANCE_PX = 2


def row_concepts(target):
    """Every bare concept the vision system sends SAM3 for this row."""
    phrases = [target.head] + [phrase_concepts(r.noun) for r in target.related]
    concepts = []
    for phrase in phrases:
        concepts.extend(c.strip() for c in phrase.split(",") if c.strip())
    return concepts


def paired(old, new):
    """-> (same count, the largest px distance between partners). Each old box takes
    the nearest unused new box (max coordinate difference)."""
    worst = 0.0
    used = set()
    best = None
    best_d = 0.0
    if len(old) != len(new):
        return False, float("inf")

    for a in old:
        best = None
        best_d = float("inf")
        for j, b in enumerate(new):
            if j in used:
                continue
            d = float(np.abs(np.asarray(a) - np.asarray(b)).max())
            if d < best_d:
                best = j
                best_d = d
        used.add(best)
        worst = max(worst, best_d)
    return True, worst


def timed(fn, *args):
    """-> (fn(*args), its ms, the GPU finished)."""
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    out = fn(*args)
    torch.cuda.synchronize()
    return out, (time.perf_counter() - t0) * 1000


def main():
    human_only, _ = bench.parse_args(sys.argv)
    rows = bench.load_rows(human_only)
    sam3 = Sam3Backend()
    cache = {}
    results = {"rows": 0, "concepts": 0, "count_equal": 0, "within_px": 0,
               "worst_px": 0.0, "failures": [], "ms_per_concept": [], "ms_shared": []}

    for row in rows:
        frame = bench.load_frame(cache, row)
        if frame is None:
            continue
        pil = Image.fromarray(frame[:, :, ::-1])
        concepts = row_concepts(bench.build_target(row))
        old, ms_old = timed(per_concept, sam3, pil, concepts)
        new, ms_new = timed(shared, sam3, pil, concepts)
        results["rows"] += 1
        results["ms_per_concept"].append(ms_old)
        results["ms_shared"].append(ms_new)
        for concept, a, b in zip(concepts, old, new):
            same, worst = paired(list(a), list(b))
            results["concepts"] += 1
            results["count_equal"] += int(same)
            results["within_px"] += int(same and worst <= TOLERANCE_PX)
            if same:
                results["worst_px"] = max(results["worst_px"], worst)
            if not same or worst > TOLERANCE_PX:
                results["failures"].append(
                    {"image": row["image"], "concept": concept,
                     "old": len(a), "new": len(b), "worst_px": worst}
                )

    for key in ("ms_per_concept", "ms_shared"):
        values = sorted(results[key])
        results[key] = {
            "p50": values[len(values) // 2],
            "mean": sum(values) / len(values),
        }
    path = os.path.join(
        bench.HERE,
        "results",
        f"{time.strftime('%Y-%m-%d')}-ab-shared-encoding.json"
    )
    json.dump(results, open(path, "w"), indent=1)
    print(json.dumps({k: v for k, v in results.items() if k != "failures"}, indent=1))
    print(f"failures: {len(results['failures'])}; wrote {path}")
    return


def per_concept(sam3, pil, concepts):
    """The old path: the full model per concept -> boxes per concept."""
    return [sam3._run(pil, c, bench.DETECT_FLOOR)[0] for c in concepts]


def shared(sam3, pil, concepts):
    """The new path: one encoding, then text + detector per concept."""
    embeds, sizes = sam3._encode(pil)
    return [sam3._run_concept(embeds, sizes, c, bench.DETECT_FLOOR)[0] for c in concepts]


if __name__ == "__main__":
    main()
