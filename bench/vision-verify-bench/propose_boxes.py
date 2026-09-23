#!/usr/bin/env python3
"""Pre-fill boxes with SAM3 so the human only confirms them in annotate.py.

Two modes:
    (default)  Write each row's single best guess into dataset/queries.jsonl:
               sam3_box and sam3_top_conf. A present row with no box yet also gets
               gt_box = that guess. box_source stays 'sam3-propose' until a human
               accepts it. Absent rows keep sam3_top_conf as a baseline signal.
    --all      Write EVERY hit >= 0.5 per row into dataset/proposals.json, as an
               annotation aid. queries.jsonl is left untouched.

GPU, about a minute. Run: python3 propose_boxes.py [--all]
"""
import json
import os
import sys

import cv2

sys.path.insert(0, "/root/groundstation/projects/integration_harden2")
os.environ.setdefault("MVD_HOME", "integration_harden2")

from perception2.backend import BACKENDS

HERE = os.path.dirname(os.path.abspath(__file__))
QUERIES = os.path.join(HERE, "dataset/queries.jsonl")


def load_rows():
    return [json.loads(line) for line in open(QUERIES)]


def read_frame(cache, image_name):
    """Decode an image once, caching by path. Returns None when the file is missing."""
    path = os.path.join(HERE, "dataset/images", image_name)
    if path not in cache:
        cache[path] = cv2.imread(path)
    return cache[path]


def write_all_proposals(backend, rows):
    """--all: store every SAM3 hit >= 0.5 per row in proposals.json."""
    from perception2.counting import count_instances
    cache = {}
    proposals = {}
    for row in rows:
        frame = read_frame(cache, row["image"])
        if frame is None:
            continue
        frame_area = frame.shape[0] * frame.shape[1]
        dets = backend.detect(frame, row["head"], conf=0.1, topk=16)
        hits = count_instances(dets, 0.5, frame_area=frame_area)
        proposals[row["id"]] = [list(h["box"]) for h in hits]
        print(f'{row["id"]:12s} {row["head"][:28]:28s} hits={len(hits)}', flush=True)
    path = os.path.join(HERE, "dataset/proposals.json")
    json.dump(proposals, open(path, "w"))
    print("proposals written for", len(proposals), "rows")


def write_best_guess(backend, rows):
    """Default: store each row's single best box and confidence in queries.jsonl."""
    cache = {}
    for row in rows:
        frame = read_frame(cache, row["image"])
        if frame is None:
            print("MISSING", row["image"])
            continue
        # A low floor, so we capture the baseline's best guess even when it is weak.
        dets = backend.detect(frame, row["head"], conf=0.05, topk=3)
        row["sam3_box"] = list(dets[0]["box"]) if dets else None
        row["sam3_top_conf"] = round(dets[0]["conf"], 3) if dets else 0.0
        if row.get("gt_box") is None and row.get("present") and dets:
            row["gt_box"] = list(dets[0]["box"])
        print(f'{row["id"]:12s} {row["head"][:28]:28s} '
              f'present={row["present"]!s:5s} sam3_conf={row["sam3_top_conf"]:.2f}', flush=True)
    with open(QUERIES, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("proposed boxes written for", len(rows), "rows")


def main():
    backend = BACKENDS["sam3"]()
    rows = load_rows()
    if "--all" in sys.argv:
        write_all_proposals(backend, rows)
    else:
        write_best_guess(backend, rows)


if __name__ == "__main__":
    main()
