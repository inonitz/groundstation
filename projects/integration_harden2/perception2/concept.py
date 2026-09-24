"""The concept front-end: turn a user phrase into the bare concept(s) SAM3 needs.

Why this exists (measured): SAM3 is a CONCEPT segmenter. It wants bare nouns and does NOT
generalize one class to another. Ask it for 'car' and it returns cars only -- the vans
stay unmarked (proven on the OCR street scene, RESULTS.md). So a user phrase must become
an explicit set of class synonyms before it reaches SAM3.

phrase_concepts() is the ONE live path (SCENE_SEG=sam3): a deterministic,
attribute-preserving transform. It strips the leading article, drops a relational or
positional clause SAM3 cannot use, and fans a bare category word out through the synonym
table. No model call, zero latency, so the tests and the live loop run the same code. The
old VLM concept extractor and its learned cache were removed 2026-09-21 (dead: the app
and verify call only phrase_concepts).
"""
import re

# Class synonym sets. A user concept on the left expands to every SAM3 noun on the right,
# because SAM3 will not cross classes on its own. Kept small and evidence-driven; extend
# as cases appear.
SYNONYMS = {
    "vehicle": ["car", "van", "truck", "bus", "motorcycle", "scooter", "bicycle"],
    "car": ["car", "van", "truck"],
    "person": ["person"],
    "people": ["person"],
    "bike": ["bicycle", "motorcycle"],
    # room objects (live 2026-09-09 block B: SAM3 scored 'screens' 0.25 while 'monitor'
    # is a strong SAM3 noun)
    "screen": ["monitor", "television", "screen"],
    "monitor": ["monitor", "screen"],
    "television": ["television", "tv"],
    "tv": ["television", "tv"],
    "cabinet": ["cabinet", "cupboard", "wardrobe"],
    "cupboard": ["cupboard", "cabinet"],
    "closet": ["closet", "wardrobe", "cabinet"],
    "wardrobe": ["wardrobe", "closet", "cabinet"],
    "drawer": ["drawer", "dresser"],
    "dresser": ["dresser", "chest of drawers", "cabinet"],
    "window pane": ["window"],
}

# Positional words SAM3 cannot use ('top left window' scored NOTHING live 2026-09-09);
# the concept keeps the noun.
_POS = re.compile(
    r"\b(?:top|bottom|left|right|upper|lower|leftmost|rightmost|middle|center|centre|"
    r"central|nearest|"
    r"closest|farthest|furthest|far|near|first|second|third|last)"
    r"(?:-(?:left|right|most))?\b\s*",
    re.I
)
_ONSIDE = re.compile(
    r"\s+(?:on|at|to|in) the "
    r"(?:top|bottom|left|right|middle|center|centre|back|front)\b.*$",
    re.I
)
_LEAD = re.compile(r"^(?:(?:the|a|an|that|this|my|some|all|any|these|those)\s+)+", re.I)
# Relational clauses SAM3 cannot use: the concept keeps the part before them.
_REL = re.compile(
    r"\s+(?:talking to|speaking to|next to|beside|behind|in front of|between|opposite|"
    r"across from|to the (?:right|left) of|"
    r"on the roof of|on top of|under|below|above|near|by|who|that|which|standing on|"
    r"sitting on|leaning on|parked between|"
    r"holding|carrying|walking|running|driving|toward|towards|going)\b.*$",
    re.I
)


def _singular(w):
    """Naive singularizer so plural user words hit the synonym table
    ('vehicles' -> 'vehicle')."""
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("ses"):
        return w[:-2]                       # buses -> bus
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _expand(concepts):
    """Apply the synonym table (plural-tolerant); drop duplicates,
    keep first-seen order. When a word is in no table entry, keep
    it verbatim -- never emit an over-stripped singular."""
    syns = []
    out = []

    for c in concepts:
        c = c.strip().lower()
        if not c:
            continue

        if c in SYNONYMS:
            syns = SYNONYMS[c]
        elif _singular(c) in SYNONYMS:
            syns = SYNONYMS[_singular(c)]
        else:
            syns = [c]
        for syn in syns:
            if syn not in out:
                out.append(syn)
    return out


def phrase_concepts(phrase):
    """Attribute-PRESERVING concept string for the live highlight path (SCENE_SEG=sam3).
    Strips only the leading article and fans a bare category word out through the synonym
    table: 'the red backpack' -> 'red backpack', 'all the vehicles' -> 'car, van, truck,
    ...'. Unlike a bare head-noun strip it KEEPS colours and other attributes: SAM3
    discriminates attribute phrases (sam3-mask-bench RESULTS.md, 'Web candidates' finding
    2), and dropping the colour would highlight every car when the user asked for the
    white one. No model call, zero latency."""
    p = (phrase or "").strip().strip(".?! ,").lower()
    p = _LEAD.sub("", p).strip()
    # 'man with glasses talking to woman in yellow shirt' -> 'man with glasses'
    # (live 2026-09-08: the full phrase scored 0.2-0.5 and jittered)
    p = _REL.sub("", p).strip() or p
    p = _ONSIDE.sub("", p).strip() or p     # 'window on the left' -> 'window'
    p = _POS.sub("", p).strip() or p        # 'top left window' -> 'window' (2026-09-09)
    if not p:
        return ""
    return ", ".join(_expand([p]))
