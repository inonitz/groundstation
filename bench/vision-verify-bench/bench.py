#!/usr/bin/env python3
"""Score the highlight path against human-labelled truth, three ways.

The question this bench answers: does the system draw the right object, and does it
refuse when the described object is not in the frame? It runs offline on saved frames,
so the score is repeatable.

Three arms, each matched to the live mvd gate (mvd.py::TextHandler._gate_task):
    control   draws for every query and never refuses. The no-gate anchor.
    baseline  today's path: SAM3 draws when the head noun clears the count gate.
    verify    baseline plus perception2/verify.py: it also checks the related noun,
              the relation geometry and the color, then refuses when a part is absent.

Live-match: the detect cap (HL_TOPK) and the speck floor (MIN_BOX_FRAC) are read from
config, not hardcoded, so the bench cannot drift from the running system.

Run:
    python3 bench.py [--labels human] [--iou 0.5]
        --labels human   score only rows a human labelled (box_source == human).
        --iou N          a drawn box counts as a truth match at IoU >= N (default 0.5).
GPU, about 3 minutes.
"""
import json
import os
import sys
import time

import cv2

sys.path.insert(0, "/root/groundstation/projects/integration_harden2")
os.environ.setdefault("MVD_HOME", "integration_harden2")

import config
from perception2.backend import BACKENDS
from perception2.concept import phrase_concepts
from perception2.counting import count_instances
from perception2.verify import Target, Related, verify_highlight, split_target

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS = ("control", "baseline", "verify")

# Live gate parameters, read from config so the bench matches the running system.
DETECT_TOPK  = config.HL_TOPK        # boxes SAM3 may return per query (the live cap)
DRAW_CAP     = config.HL_MAX         # boxes actually drawn per frame
MIN_BOX_FRAC = config.MIN_BOX_FRAC   # ignore boxes smaller than this fraction of the frame
DETECT_FLOOR = 0.1                   # low floor, so an absent answer can still report near-misses
HEAD_THR     = 0.5                   # the head noun must clear this to be drawn
RELATED_THR  = 0.3                   # the related noun only needs to be plausibly present

# Dataset relation words -> the geometric test verify.py understands.
RELATION_MAP = {
    "none": "none", "next_to": "near", "on_top_of": "on",
    "held_by": "touch", "talking_to": "near", "inside": "in",
}


# ---------------------------------------------------------------- input
def parse_args(argv):
    """Return (human_only, iou_bar) from the command line."""
    human_only = "--labels" in argv and "human" in argv
    iou_bar = 0.5
    if "--iou" in argv:
        iou_bar = float(argv[argv.index("--iou") + 1])
    return human_only, iou_bar


def load_rows(human_only):
    """Load query rows whose presence is known. Keep human labels only when asked."""
    path = os.path.join(HERE, "dataset/queries.jsonl")
    rows = [json.loads(line) for line in open(path)]
    rows = [r for r in rows if r.get("present") is not None]
    if human_only:
        rows = [r for r in rows if r.get("box_source") == "human"]
    return rows


def load_frame(cache, row):
    """Decode a row's image once and cache it. Returns None when the file is missing."""
    path = os.path.join(HERE, "dataset/images", row["image"])
    if path not in cache:
        cache[path] = cv2.imread(path)
    return cache[path]


def build_target(row):
    """Turn a dataset row into a verify.Target (head, related noun, relation)."""
    if not row.get("related"):
        # A raw spoken phrase: split it the same way the live path does.
        return split_target(row["head"])
    related = [Related(item["noun"], item.get("color", "")) for item in row["related"]]
    relation = RELATION_MAP.get(row.get("relation", "none"), "near")
    return Target(head=phrase_concepts(row["head"]), related=related, relation=relation)


# ---------------------------------------------------------------- geometry
def iou(box_a, box_b):
    """Intersection over union of two [x1, y1, x2, y2] boxes."""
    ix1 = max(box_a[0], box_b[0])
    iy1 = max(box_a[1], box_b[1])
    ix2 = min(box_a[2], box_b[2])
    iy2 = min(box_a[3], box_b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def truth_boxes(row):
    """Every ground-truth box for a row, as a list."""
    if row.get("gt_boxes"):
        return row["gt_boxes"]
    if row.get("gt_box"):
        return [row["gt_box"]]
    return []


def match_ious(boxes, truth, iou_bar):
    """IoU of each truth box that a drawn box covers. Each truth matches at most one box."""
    used = set()
    hits = []
    for box in boxes:
        best_iou = 0.0
        best_index = None
        for index, tb in enumerate(truth):
            if index in used:
                continue
            value = iou(box, tb)
            if value > best_iou:
                best_iou = value
                best_index = index
        if best_index is not None and best_iou >= iou_bar:
            used.add(best_index)
            hits.append(best_iou)
    return hits


# ---------------------------------------------------------------- scoring
def score_row(drew, boxes, row, iou_bar):
    """Grade one arm on one row.

    Returns (verdict, matched, missed, extra, matched_ious).
    Absent row  -> "correct" (refused) or "false-draw" (drew anyway).
    Present row -> "miss" (drew nothing), "wrong-box" (drew, nothing matched),
                   "partial" (some truth matched), "correct" (all truth matched).
    """
    if not row["present"]:
        if drew:
            return "false-draw", 0, 0, len(boxes), []
        return "correct", 0, 0, 0, []
    truth = truth_boxes(row)
    if not drew:
        return "miss", 0, len(truth), 0, []
    if not truth:
        return "correct", 0, 0, 0, []
    hits = match_ious(boxes, truth, iou_bar)
    matched = len(hits)
    missed = len(truth) - matched
    extra = len(boxes) - matched
    if missed == 0:
        verdict = "correct"
    elif matched == 0:
        verdict = "wrong-box"
    else:
        verdict = "partial"
    return verdict, matched, missed, extra, hits


# ---------------------------------------------------------------- the three arms
def run_control(detect, frame, target):
    """Never refuse: draw raw SAM3 boxes, or one full-frame box if SAM3 found nothing."""
    frame_h, frame_w = frame.shape[:2]
    dets = detect(frame, target.head, DETECT_FLOOR)
    if dets:
        boxes = [d["box"] for d in dets][:DRAW_CAP]
    else:
        boxes = [[0, 0, frame_w, frame_h]]
    return True, boxes


def run_baseline(detect, frame, target):
    """Today's gate: the SAM3 detections that clear the count threshold."""
    frame_area = frame.shape[0] * frame.shape[1]
    dets = detect(frame, target.head, DETECT_FLOOR)
    hits = count_instances(dets, HEAD_THR, frame_area=frame_area, min_frac=MIN_BOX_FRAC)
    boxes = [h["box"] for h in hits]
    return bool(hits), boxes


def run_verify(detect, frame, target, baseline_drew, baseline_boxes):
    """Baseline, plus verify.py on related-noun rows. It only vetoes; it draws the same boxes."""
    if not target.related:
        # The live path never calls verify without a related noun.
        return baseline_drew, baseline_boxes
    frame_area = frame.shape[0] * frame.shape[1]
    result = verify_highlight(detect, frame, target, floor=DETECT_FLOOR, hit_thr=HEAD_THR,
                              frame_area=frame_area, min_frac=MIN_BOX_FRAC, rel_thr=RELATED_THR)
    drew = baseline_drew and result.verdict == "draw"
    boxes = baseline_boxes if drew else []
    return drew, boxes


def measure_arms(detect, frame, target, latency):
    """Run all three arms on one frame, timing each. Returns arm -> (drew, boxes)."""
    start = time.time()
    baseline = run_baseline(detect, frame, target)
    latency["baseline"].append(time.time() - start)

    start = time.time()
    control = run_control(detect, frame, target)
    latency["control"].append(time.time() - start)

    start = time.time()
    verify = run_verify(detect, frame, target, baseline[0], baseline[1])
    # verify runs SAM3 again only on related rows; time zero on the rest.
    latency["verify"].append((time.time() - start) if target.related else 0.0)

    return {"control": control, "baseline": baseline, "verify": verify}


# ---------------------------------------------------------------- reporting
def percentile(values, q):
    """The q-percentile of the non-zero values, in milliseconds."""
    kept = sorted(v for v in values if v)
    if not kept:
        return 0.0
    index = min(len(kept) - 1, int(q * (len(kept) - 1)))
    return kept[index] * 1000


def print_class_table(tally, classes):
    """One row per (class, arm), every verdict column."""
    print("| class | arm | correct | partial | false-draw | miss | wrong-box |")
    print("|---|---|---|---|---|---|---|")
    for cls in classes:
        for arm in ARMS:
            v = tally[arm].get(cls, {})
            print(f"| {cls} | {arm} | {v.get('correct', 0)} | {v.get('partial', 0)} | "
                  f"{v.get('false-draw', 0)} | {v.get('miss', 0)} | {v.get('wrong-box', 0)} |")


def print_summary(tally, instances, tightness, latency, max_boxes):
    """Instance counts, then one summary row per arm."""
    def total(arm, verdict):
        return sum(v.get(verdict, 0) for v in tally[arm].values())

    print()
    for arm in ARMS:
        inst = instances[arm]
        print(f"instances {arm}: matched {inst['matched']} missed {inst['missed']} extra {inst['extra']}")
    print()
    print("| arm | false-draw | correct | partial | correct+partial | mean IoU | p50 ms | p95 ms | max boxes |")
    print("|---|---|---|---|---|---|---|---|---|")
    for arm in ARMS:
        false_draw = total(arm, "false-draw")
        correct = total(arm, "correct")
        partial = total(arm, "partial")
        ious = tightness[arm]
        mean_iou = sum(ious) / len(ious) if ious else 0.0
        p50 = percentile(latency[arm], 0.5)
        p95 = percentile(latency[arm], 0.95)
        print(f"| {arm} | {false_draw} | {correct} | {partial} | {correct + partial} | "
              f"{mean_iou:.2f} | {p50:.0f} | {p95:.0f} | {max_boxes[arm]} |")


def write_results(human_only, iou_bar, rows, tally, instances, max_boxes, latency):
    """Save the run as JSON next to the other results."""
    out = {
        "setup": {"topk": DETECT_TOPK, "min_frac": MIN_BOX_FRAC, "floor": DETECT_FLOOR,
                  "head_thr": HEAD_THR, "rel_thr": RELATED_THR, "iou_bar": iou_bar},
        "rows": len(rows),
        "tally": tally,
        "instances": instances,
        "max_boxes": max_boxes,
        "latency_ms": {arm: [round(v * 1000) for v in latency[arm]] for arm in ARMS},
    }
    suffix = "human" if human_only else "all"
    name = f"{time.strftime('%Y-%m-%d')}-bench-3arm-{suffix}.json"
    path = os.path.join(HERE, "results", name)
    json.dump(out, open(path, "w"), indent=1)
    return path


# ---------------------------------------------------------------- main
def main():
    human_only, iou_bar = parse_args(sys.argv)
    rows = load_rows(human_only)
    backend = BACKENDS["sam3"]()

    def detect(frame, phrase, floor):
        return backend.detect(frame, phrase, conf=floor, topk=DETECT_TOPK)

    print(f"SETUP topk={DETECT_TOPK} min_frac={MIN_BOX_FRAC} floor={DETECT_FLOOR} "
          f"head_thr={HEAD_THR} rel_thr={RELATED_THR} iou_bar={iou_bar}")

    tally = {arm: {} for arm in ARMS}
    instances = {arm: {"matched": 0, "missed": 0, "extra": 0} for arm in ARMS}
    tightness = {arm: [] for arm in ARMS}
    latency = {arm: [] for arm in ARMS}
    max_boxes = {arm: 0 for arm in ARMS}
    frame_cache = {}

    for row in rows:
        frame = load_frame(frame_cache, row)
        if frame is None:
            continue
        target = build_target(row)
        arms = measure_arms(detect, frame, target, latency)
        for arm, (drew, boxes) in arms.items():
            max_boxes[arm] = max(max_boxes[arm], len(boxes) if drew else 0)
            verdict, matched, missed, extra, hits = score_row(drew, boxes, row, iou_bar)
            per_class = tally[arm].setdefault(row["cls"], {})
            per_class[verdict] = per_class.get(verdict, 0) + 1
            instances[arm]["matched"] += matched
            instances[arm]["missed"] += missed
            instances[arm]["extra"] += extra
            tightness[arm].extend(hits)

    label = "human truth only" if human_only else "all labels"
    print(f"\nrows scored: {len(rows)}  ({label})")
    print_class_table(tally, sorted({row["cls"] for row in rows}))
    print_summary(tally, instances, tightness, latency, max_boxes)
    path = write_results(human_only, iou_bar, rows, tally, instances, max_boxes, latency)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
