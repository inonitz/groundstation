"""Instance counting from detector boxes (live 2026-09-09, block A: 'count the chairs'
said four times on the same scene returned 2, 5, 4, 6). One SAM3 forward at threshold 0.5
still returns near-duplicate instances (a part of the chair inside the chair) and the
per-frame set jitters. Two pure-python fixes, no model code:
  count_instances: keep conf >= thr, then drop any box mostly CONTAINED in a
                   higher-confidence box (intersection / smaller area >= contain), so a
                   chair back inside the chair is one chair.
  median_count:    the median of the per-frame counts of a few consecutive frames."""
from perception2.boxes import area, intersection


def _by_conf(d):
    return -float(d["conf"])


def count_instances(dets, thr=0.5, contain=0.7, frame_area=None, min_frac=0.0):
    """dets: [{'conf': float, 'box': (x1,y1,x2,y2)}, ...]. Returns the kept detections
    (highest conf first). frame_area + min_frac drop specks: real flight 2026-09-09 had
    'chairs' at 0.86 conf on boxes under 0.5 % of the frame in an open field (SAM3 speck
    false positives); a 720p frame at min_frac 0.001 needs about a 30x30 px box."""
    b = None
    small = 0
    dup = False
    cand = []
    kept = []
    min_area = (frame_area or 0) * min_frac

    for d in dets:
        if float(d.get("conf", 0.0)) >= thr and area(d["box"]) >= min_area:
            cand.append(d)
    cand.sort(key=_by_conf)

    for d in cand:
        b = d["box"]
        if area(b) <= 0:
            continue

        dup = False
        for k in kept:
            small = min(area(b), area(k["box"]))
            if small > 0 and intersection(b, k["box"]) / small >= contain:
                dup = True
                break
        if not dup:
            kept.append(d)
    return kept


def median_count(counts):
    """Median of a short list of ints (0 for an empty list); the lower middle for an even
    length."""
    c = sorted(int(x) for x in counts)
    if not c:
        return 0
    return c[(len(c) - 1) // 2]
