"""Split-and-verify for the highlight path (owner ruling 2026-09-19). Switch: SCENE_VERIFY=on.

Why: SAM3 scores the parts of a phrase that match and never checks the parts that are missing.
"backpack held by a child" draws guitar cases when no child is in view. phrase_concepts() even strips
the relation clause on purpose (it made SAM3 jitter). This module keeps that clause, splits it into
(head, related noun, relation), asks SAM3 for the related noun too, checks the relation with plain
geometry and the color with a hue check, and refuses when a required part is not there.

Pure functions. No engine import. Needs only a detect(frame, phrase, floor) -> (status, hits) callable.
"""
import re
from dataclasses import dataclass, field

from perception2.concept import phrase_concepts, _LEAD
from perception2.backend import DETECT_OK
from perception2.counting import count_instances

# relation words -> the geometric test that verifies them
_RELS = [
    (r"held by|carried by|in the hand of|holding|carrying",                       "touch"),
    (r"on the roof of|on top of|standing on|sitting on|lying on|on",              "on"),
    (r"under|below|beneath|underneath",                                            "under"),
    (r"above|over",                                                                "above"),
    (r"inside|within",                                                             "in"),
    (r"talking to|speaking to|next to|beside|near|by|behind|in front of|opposite|"
     r"across from|between|to the right of|to the left of|leaning on|parked between", "near"),
]
_REL_RE = re.compile(r"\s+(?:" + "|".join(p for p, _ in _RELS) + r")\s+(?:the\s+|a\s+|an\s+)?(.+)$", re.I)
_REL_KIND = [(re.compile(r"^\s*(?:" + p + r")\b", re.I), k) for p, k in _RELS]
_COLORS = ("red", "green", "blue", "yellow", "black", "white", "grey", "gray", "orange", "purple", "pink", "brown")
_COLOR_RE = re.compile(r"\b(" + "|".join(_COLORS) + r")\b", re.I)


@dataclass
class Related:
    noun: str            # what SAM3 is asked for, attributes kept: "child with green shirt"
    color: str = ""      # first color word in the clause, checked by hue on the found box


@dataclass
class Target:
    head: str                                  # SAM3 concept string for the thing to draw
    related: list = field(default_factory=list)  # [Related]; v1 parses the first clause only
    relation: str = "none"                     # touch | on | under | above | in | near | none


def split_target(phrase):
    """'man with glasses talking to woman in yellow shirt' ->
    head='man with glasses', related=[Related('woman in yellow shirt','yellow')], relation='near'."""
    p = (phrase or "").strip().strip(".?! ,")
    m = _REL_RE.search(p)
    if not m:
        return Target(head=phrase_concepts(p))
    head_part = p[:m.start()]
    clause = p[m.start():].strip()
    kind = "near"
    for rx, k in _REL_KIND:
        if rx.search(clause):
            kind = k; break
    rel_noun = _LEAD.sub("", m.group(1).strip()).strip()
    if rel_noun.split(" ")[0] in ("left", "right", "top", "bottom", "middle", "center", "centre", "back", "front", "side"):
        return Target(head=phrase_concepts(p))                     # "window on the left": a side, not an object
    # a color belongs to the related noun only before a nested "of": "roof of the white building" is not a white roof
    cm = _COLOR_RE.search(re.split(r"\s+of\s+", rel_noun, 1)[0])
    return Target(head=phrase_concepts(head_part), related=[Related(rel_noun, cm.group(1).lower() if cm else "")],
                  relation=kind)


# ---------------- geometry ----------------
def _iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]); ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _gap(a, b):
    """Shortest edge-to-edge distance between two boxes (0 when they overlap)."""
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2])); dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


def _h_overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    return w / max(1, min(a[2] - a[0], b[2] - b[0])) if w > 0 else 0.0


def _contain(a, b):
    """Fraction of a inside b."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]); ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    return inter / max(1, (a[2] - a[0]) * (a[3] - a[1]))


def rel_holds(relation, a, b):
    """Does head box a stand in `relation` to related box b? Plain geometry, tolerant."""
    if relation == "none":
        return True
    small = min(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1])
    bh = max(1, b[3] - b[1])
    if relation == "touch":
        return _iou(a, b) > 0 or _gap(a, b) < 0.25 * small
    if relation == "near":
        return _iou(a, b) > 0 or _gap(a, b) < 1.0 * small
    if relation == "on":                           # standing on: bottom meets top. sitting/lying on: overlap
        return _h_overlap(a, b) >= 0.3 and (abs(a[3] - b[1]) <= 0.25 * bh or _iou(a, b) > 0.25
                                            or _contain(a, b) > 0.5 or _contain(b, a) > 0.5)
    if relation == "under":
        return _h_overlap(a, b) >= 0.3 and a[1] >= b[3] - 0.25 * bh
    if relation == "above":
        return _h_overlap(a, b) >= 0.3 and a[3] <= b[1] + 0.25 * bh
    if relation == "in":
        return _contain(a, b) >= 0.8
    return True


# ---------------- color ----------------
def region_is_color(frame_bgr, box, color):
    """Dominant color of the box's middle, in HSV, against a small name table."""
    import cv2, numpy as np
    x1, y1, x2, y2 = [int(v) for v in box]
    h, w = frame_bgr.shape[:2]
    x1, x2 = max(0, x1), min(w, x2); y1, y2 = max(0, y1), min(h, y2)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return False
    mx, my = (x2 - x1) // 4, (y2 - y1) // 4                 # the middle half, away from the edges
    roi = frame_bgr[y1 + my:y2 - my, x1 + mx:x2 - mx]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    H, S, V = hsv[:, 0], hsv[:, 1] / 255.0, hsv[:, 2] / 255.0
    c = color.lower()
    if c == "white":  return float(np.mean((V > 0.7) & (S < 0.25))) > 0.4
    if c == "black":  return float(np.mean(V < 0.25)) > 0.4
    if c in ("grey", "gray"): return float(np.mean((S < 0.2) & (V >= 0.25) & (V <= 0.7))) > 0.4
    hue = {"red": ((0, 10), (170, 180)), "orange": ((10, 22),), "yellow": ((22, 38),), "green": ((38, 85),),
           "blue": ((85, 130),), "purple": ((130, 155),), "pink": ((155, 170),), "brown": ((8, 22),)}.get(c)
    if not hue:
        return True                                          # unknown color word: do not block
    chroma = (S > 0.3) & (V > 0.2)
    if c == "brown": chroma = (S > 0.3) & (V > 0.15) & (V < 0.6)
    inr = np.zeros_like(H, dtype=bool)
    for lo, hi in hue: inr |= (H >= lo) & (H < hi)
    return float(np.mean(inr & chroma)) > 0.25


# ---------------- the verdict ----------------
@dataclass
class Verified:
    verdict: str          # draw | absent | misplaced | failed (a SAM3 call failed; the caller fails open)
    head: dict = None     # the det to draw when verdict == draw
    reason: str = ""


def verify_highlight(detect, frame, target, floor=0.1, hit_thr=0.5, frame_area=None, min_frac=0.0, rel_thr=0.3):
    """Once per query. detect(frame, phrase, floor) -> (status, hits). Returns a Verified.
    The head must clear hit_thr (it is what gets drawn). The related noun only needs to be plausibly
    there, so it clears the lower rel_thr -- a weakly seen window must not refuse a true 'next to the window'."""
    fa = frame_area or frame.shape[0] * frame.shape[1]
    status, head_hits = detect(frame, target.head, floor)
    if status != DETECT_OK:
        return Verified("failed", None, "SAM3 call failed")
    heads = count_instances(head_hits, hit_thr, frame_area=fa, min_frac=min_frac)
    if not heads:
        return Verified("absent", None, f"no {target.head}")
    if not target.related:
        return Verified("draw", heads[0], "simple")
    rel = target.related[0]
    status, rel_hits = detect(frame, rel.noun, floor)
    if status != DETECT_OK:
        return Verified("failed", None, "SAM3 call failed")
    hits = count_instances(rel_hits, rel_thr, frame_area=fa, min_frac=min_frac)
    if rel.color and hits:
        hits = [d for d in hits if region_is_color(frame, d["box"], rel.color)]
    if not hits:
        return Verified("absent", None, f"no {rel.color + ' ' if rel.color else ''}{rel.noun}".strip())
    for h in heads:
        for r in hits:
            if rel_holds(target.relation, h["box"], r["box"]):
                return Verified("draw", h, f"{target.relation} {rel.noun}")
    return Verified("misplaced", None, f"{target.head} not {target.relation} {rel.noun}")
