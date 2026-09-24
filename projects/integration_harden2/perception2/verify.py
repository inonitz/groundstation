"""Split-and-verify for the highlight path (owner ruling 2026-09-19).
Switch: SCENE_VERIFY=on.

Why: SAM3 scores the parts of a phrase that match and never checks the parts that are
missing. "backpack held by a child" draws guitar cases when no child is in view.
phrase_concepts() even strips the relation clause on purpose (it made SAM3 jitter). This
module keeps that clause, splits it into (head, related noun, relation), asks SAM3 for
the related noun too, checks the relation with plain geometry and the color with a hue
check, and refuses when a required part is not there.

Pure functions. No engine import. Needs only a
detect(frame, phrase, floor) -> (status, hits) callable.
"""
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from perception2.concept import phrase_concepts, _LEAD
from perception2.backend import DETECT_OK
from perception2 import boxes
from perception2.boxes import inside, iou
from perception2.counting import count_instances

# relation words -> the geometric test that verifies them
_RELS = [
    (r"held by|carried by|in the hand of|holding|carrying",          "touch"),
    (r"on the roof of|on top of|standing on|sitting on|lying on|on", "on"),
    (r"under|below|beneath|underneath",                              "under"),
    (r"above|over",                                                  "above"),
    (r"inside|within",                                               "in"),
    (r"talking to|speaking to|next to|beside|near|by|behind|in front of|opposite|"
     r"across from|between|to the right of|to the left of|leaning on|"
     r"parked between",                                              "near"),
]
_REL_RE = re.compile(
    r"\s+(?:" + "|".join(p for p, _ in _RELS) + r")\s+(?:the\s+|a\s+|an\s+)?(.+)$",
    re.I
)
_REL_KIND = [(re.compile(r"^\s*(?:" + p + r")\b", re.I), k) for p, k in _RELS]
_COLORS = (
    "red", "green", "blue", "yellow", "black", "white", "grey", "gray", "orange",
    "purple", "pink", "brown"
)
_COLOR_RE = re.compile(r"\b(" + "|".join(_COLORS) + r")\b", re.I)
# a related "noun" that is only a side ("window on the left") is not an object
_SIDE_WORDS = (
    "left", "right", "top", "bottom", "middle", "center", "centre", "back", "front",
    "side"
)


@dataclass
class Related:
    noun: str        # what SAM3 is asked for, attributes kept: "child with green shirt"
    color: str = ""  # first color word in the clause, checked by hue on the found box


@dataclass
class Target:
    # SAM3 concept string for the thing to draw
    head: str
    # [Related]; v1 parses the first clause only
    related: list = field(default_factory=list)
    # touch | on | under | above | in | near | none
    relation: str = "none"


def split_target(phrase):
    """'man with glasses talking to woman in yellow shirt' ->
    head='man with glasses', related=[Related('woman in yellow shirt','yellow')],
    relation='near'."""
    kind = "near"
    color = ""

    p = (phrase or "").strip().strip(".?! ,")
    m = _REL_RE.search(p)
    if not m:
        return Target(head=phrase_concepts(p))

    head_part = p[:m.start()]
    clause = p[m.start():].strip()
    for rx, k in _REL_KIND:
        if rx.search(clause):
            kind = k
            break

    rel_noun = _LEAD.sub("", m.group(1).strip()).strip()
    if rel_noun.split(" ")[0] in _SIDE_WORDS:
        return Target(head=phrase_concepts(p))

    # a color belongs to the related noun only before a nested "of": "roof of the white
    # building" is not a white roof
    cm = _COLOR_RE.search(re.split(r"\s+of\s+", rel_noun, 1)[0])
    if cm:
        color = cm.group(1).lower()
    return Target(
        head=phrase_concepts(head_part),
        related=[Related(rel_noun, color)],
        relation=kind
    )


# ---------------- geometry (overlap math: perception2/boxes.py) ----------------
def _gap(a, b):
    """Shortest edge-to-edge distance between two boxes (0 when they overlap)."""
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


def _h_overlap(a, b):
    """The horizontal overlap, as a fraction of the narrower box."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    if w <= 0:
        return 0.0
    return w / max(1, min(a[2] - a[0], b[2] - b[0]))


def rel_holds(relation, a, b):
    """Does head box a stand in `relation` to related box b? Plain geometry, tolerant."""
    if relation == "none":
        return True
    small = min(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1])
    bh = max(1, b[3] - b[1])

    if relation == "touch":
        return iou(a, b) > 0 or _gap(a, b) < 0.25 * small
    if relation == "near":
        return iou(a, b) > 0 or _gap(a, b) < 1.0 * small
    # standing on: bottom meets top. sitting/lying on: overlap
    if relation == "on":
        return _h_overlap(a, b) >= 0.3 and (
            abs(a[3] - b[1]) <= 0.25 * bh
            or iou(a, b) > 0.25
            or inside(a, b) > 0.5
            or inside(b, a) > 0.5
        )
    if relation == "under":
        return _h_overlap(a, b) >= 0.3 and a[1] >= b[3] - 0.25 * bh
    if relation == "above":
        return _h_overlap(a, b) >= 0.3 and a[3] <= b[1] + 0.25 * bh
    if relation == "in":
        return inside(a, b) >= 0.8
    return True


# ---------------- color ----------------
# OpenCV hue ranges (0-180) per color name; red wraps around 0.
_HUES = {
    "red": ((0, 10), (170, 180)),
    "orange": ((10, 22),),
    "yellow": ((22, 38),),
    "green": ((38, 85),),
    "blue": ((85, 130),),
    "purple": ((130, 155),),
    "pink": ((155, 170),),
    "brown": ((8, 22),),
}


def region_is_color(frame_bgr, box, color):
    """Dominant color of the box's middle, in HSV, against a small name table."""
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    x1 = max(0, x1)
    x2 = min(w, x2)
    y1 = max(0, y1)
    y2 = min(h, y2)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return False

    # the middle half, away from the edges
    mx = (x2 - x1) // 4
    my = (y2 - y1) // 4
    roi = frame_bgr[y1 + my:y2 - my, x1 + mx:x2 - mx]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    H = hsv[:, 0]
    S = hsv[:, 1] / 255.0
    V = hsv[:, 2] / 255.0

    # the colorless names test brightness and saturation only
    c = color.lower()
    if c == "white":
        return float(np.mean((V > 0.7) & (S < 0.25))) > 0.4
    if c == "black":
        return float(np.mean(V < 0.25)) > 0.4
    if c in ("grey", "gray"):
        return float(np.mean((S < 0.2) & (V >= 0.25) & (V <= 0.7))) > 0.4

    hue = _HUES.get(c)
    if not hue:
        return True                 # unknown color word: do not block
    chroma = (S > 0.3) & (V > 0.2)
    if c == "brown":
        chroma = (S > 0.3) & (V > 0.15) & (V < 0.6)
    inr = np.zeros_like(H, dtype=bool)
    for lo, hi in hue:
        inr |= (H >= lo) & (H < hi)
    return float(np.mean(inr & chroma)) > 0.25


# ---------------- the verdict ----------------
@dataclass
class Verified:
    # draw | absent | misplaced | failed (a SAM3 call failed; the caller fails open)
    verdict: str
    head: dict = None     # the det to draw when verdict == draw
    reason: str = ""


def verify_highlight(detect, frame, target, floor=0.1, hit_thr=0.5, frame_area=None,
                     min_frac=0.0, rel_thr=0.3):
    """Once per query. detect(frame, phrase, floor) -> (status, hits). Returns a
    Verified. The head must clear hit_thr (it is what gets drawn). The related noun only
    needs to be plausibly there, so it clears the lower rel_thr -- a weakly seen window
    must not refuse a true 'next to the window'."""
    fa = frame_area or boxes.frame_area(frame)

    # the head: what gets drawn
    status, head_hits = detect(frame, target.head, floor)
    if status != DETECT_OK:
        return Verified("failed", None, "SAM3 call failed")
    heads = count_instances(head_hits, hit_thr, frame_area=fa, min_frac=min_frac)
    if not heads:
        return Verified("absent", None, f"no {target.head}")
    if not target.related:
        return Verified("draw", heads[0], "simple")

    # the related noun, with its color when one was said
    rel = target.related[0]
    status, rel_hits = detect(frame, rel.noun, floor)
    if status != DETECT_OK:
        return Verified("failed", None, "SAM3 call failed")
    hits = count_instances(rel_hits, rel_thr, frame_area=fa, min_frac=min_frac)
    if rel.color and hits:
        hits = [d for d in hits if region_is_color(frame, d["box"], rel.color)]
    if not hits:
        what = f"{rel.color} {rel.noun}".strip()
        return Verified("absent", None, f"no {what}".strip())

    # the relation: any head/related pair that stands in it
    for h in heads:
        for r in hits:
            if rel_holds(target.relation, h["box"], r["box"]):
                return Verified("draw", h, f"{target.relation} {rel.noun}")
    return Verified("misplaced", None, f"{target.head} not {target.relation} {rel.noun}")
