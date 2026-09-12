"""Instance counting from detector boxes (live 2026-09-09, block A: 'count the chairs' said four times on the
same scene returned 2, 5, 4, 6). One SAM3 forward at threshold 0.5 still returns near-duplicate instances
(a part of the chair inside the chair) and the per-frame set jitters. Two pure-python fixes, no model code:
  count_instances: keep conf >= thr, then drop any box mostly CONTAINED in a higher-confidence box
                   (intersection / smaller area >= contain), so a chair back inside the chair is one chair.
  median_count:    the median of the per-frame counts of a few consecutive frames."""


def _inter(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    return max(0, x2 - x1) * max(0, y2 - y1)


def _area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def count_instances(dets, thr=0.5, contain=0.7, frame_area=None, min_frac=0.0):
    """dets: [{'conf': float, 'box': (x1,y1,x2,y2)}, ...]. Returns the kept detections (highest conf first).
    frame_area + min_frac drop specks: real flight 2026-09-09 had 'chairs' at 0.86 conf on boxes under 0.5 % of the
    frame in an open field (SAM3 speck false positives); a 720p frame at min_frac 0.001 needs about a 30x30 px box."""
    min_area = (frame_area or 0) * min_frac
    cand = sorted((d for d in dets if float(d.get("conf", 0.0)) >= thr and _area(d["box"]) >= min_area),
                  key=lambda d: -float(d["conf"]))
    kept = []
    for d in cand:
        b = d["box"]
        if _area(b) <= 0:
            continue
        dup = False
        for k in kept:
            small = min(_area(b), _area(k["box"]))
            if small > 0 and _inter(b, k["box"]) / small >= contain:
                dup = True; break
        if not dup:
            kept.append(d)
    return kept


def median_count(counts):
    """Median of a short list of ints (0 for an empty list); the lower middle for an even length."""
    c = sorted(int(x) for x in counts)
    return c[(len(c) - 1) // 2] if c else 0
