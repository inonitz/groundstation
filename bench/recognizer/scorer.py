"""The recognizer benchmark's ONE scorer (owner 2026-09-27, U2.3: "Scorer: Should only be
one. Definitely doesn't belong in log/*").

    score(expect, decision) -> (verdict, reason)   verdict: PASS | FAIL | REVIEW
    read_notation(text) -> expect                   the live lists' notation -> an expect

`expect` is a case's expected result (the JSON format: bench/recognizer/README.md).
`decision` is recognizer.Decision, what route() decided. The scorer grades the steps,
the reject, the emergency, and for perception the kind and the target words (X1).
"""
import re

# a perception answer is graded on "<kind words> the <target>": the words a kind stands
# for, so a keyword group like ["highlight", "mark"] is met by the kind itself
KIND_WORDS = {
    "highlight": "highlight find mark follow track focus",
    "count": "count how many",
    "describe": "describe tell what see look scene area frame image",
}
TOLERANCE = 0.01

# the live lists' notation (the "note" of a case): "dz+10", "+90 deg", "+90", "takeoff",
# "delay 5s", "EMPTY", "halt", "VLM ..."
REVIEW_RE = re.compile(
    r"\b(record|open|or a clean|or clean| or |should reach|reject/empty|, or )"
)
STEP_RE = re.compile(
    r"\bd([xyz])\s*([+-]?\s*\d+(?:\.\d+)?)"
    # a turn: a number with "deg", or a SIGNED number alone. The 2026-09-26 run failed
    # two right plans because "+90" without "deg" was not read.
    r"|(?<![\w.])([+-]?\d+(?:\.\d+)?)\s*deg\b"
    r"|(?<![\w.])([+-]\d+(?:\.\d+)?)(?![\w.])"
    r"|\b(takeoff|land)\b"
    r"|\bdelay\s*(\d+(?:\.\d+)?)"
)


def read_notation(text):
    """A live list's expected text -> an expect (see the module doc)."""
    t = text.strip()
    low = t.lower()
    steps = []

    if REVIEW_RE.search(low) and "never 0.5" not in low:
        return {"kind": "review"}
    if (
        low.startswith("empty")
        or (" empty" in low and "mission" in low and "vlm" not in low)
    ):
        return {"kind": "none"}
    if low.startswith("halt") or low.startswith("stop"):
        return {"kind": "emergency"}
    if low.startswith("vlm") or "perception" in low or "highlight" in low:
        return {"kind": "perception", "groups": []}

    for m in STEP_RE.finditer(t):
        steps.append(notation_step(m, "either way" in low))
    if not steps:
        return {"kind": "review"}
    return {"kind": "mission", "steps": steps}


def notation_step(m, either_way=False):
    """One STEP_RE match -> [type, key, value]. either_way: a turn in either direction
    passes ("180 deg (either way)" -> ["abs", 180])."""
    if m.group(1):
        return ["fly_by", "d" + m.group(1), float(m.group(2).replace(" ", ""))]
    if m.group(3) or m.group(4):
        return turn_step(float(m.group(3) or m.group(4)), either_way)
    if m.group(5):
        return [m.group(5), None, None]
    return ["delay", "seconds", float(m.group(6))]


def turn_step(degrees, either_way):
    if either_way:
        return ["spin_by", "degrees", ["abs", abs(degrees)]]
    return ["spin_by", "degrees", degrees]


def score(expect, decision):
    """-> (verdict, reason). The reason names what route() did when it is wrong."""
    want = expect["kind"]
    kind = decision.kind

    if want == "review":
        return "REVIEW", kind
    if kind == "gemma_failed":
        # a backend failure is never a right answer, whatever was expected
        return "FAIL", "gemma failed"
    if want == "emergency":
        return verdict(kind == "emergency", kind)
    if want == "none":
        return verdict(kind != "mission", f"flew {len(decision.mission)} steps")
    if want == "open":
        return verdict(kind == "mission", why_not(decision))
    if want == "perception":
        return score_perception(expect["groups"], decision, expect.get("vision"))
    if kind == "emergency" and "halt" in expect.get("alternatives", []):
        # owner J4 (2026-09-28): "if we wanted to halt in some sort of way or another,
        # then the halt should pass"
        return "PASS", ""
    if kind != "mission":
        return "FAIL", why_not(decision)
    if "alternatives" in expect:
        return score_alternatives(expect["alternatives"], decision.mission)
    return score_steps(expect["steps"], decision.mission)


def score_alternatives(alternatives, mission):
    """The plan passes when it matches any one accepted step list (owner J4)."""
    reasons = []
    for steps in alternatives:
        if steps == "halt":
            continue
        verdict_, reason = score_steps(steps, mission)
        if verdict_ == "PASS":
            return "PASS", ""
        reasons.append(reason)
    return "FAIL", "; ".join(reasons)


def verdict(ok, reason):
    if ok:
        return "PASS", ""
    return "FAIL", reason


def why_not(decision):
    """What route() did instead of a mission."""
    if decision.kind == "reject":
        return decision.action
    if decision.kind in KIND_WORDS:
        return f"routed {decision.kind}: {decision.target}"
    return f"routed {decision.kind}"


def score_perception(groups, decision, vision=None):
    """The kind must be a vision request, and the expected one when `vision` names it
    (highlight, count or describe; owner SC1, 2026-09-30). Every keyword group needs one
    synonym in "<kind words> the <target>"."""
    if decision.kind not in KIND_WORDS:
        return "FAIL", why_not(decision)
    if vision is not None and decision.kind != vision:
        return "FAIL", f"a {decision.kind} request, expected {vision}"

    text = f"{KIND_WORDS[decision.kind]} the {decision.target}".lower()
    missed = []
    for group in groups:
        if not any(word in text for word in group):
            missed.append("|".join(group))
    if missed:
        return "FAIL", f"words missed: {', '.join(missed)} in '{decision.target}'"
    return "PASS", ""


def score_steps(want, mission):
    """The mission against the expected steps, in order."""
    if len(mission) != len(want):
        return "FAIL", f"{len(mission)} steps, expected {len(want)}"

    for got, (typ, key, value) in zip(mission, want):
        if got.get("type") != typ:
            return "FAIL", f"step {got.get('type')}, expected {typ}"
        if key is None:
            continue
        if got.get(key) is None:
            return "FAIL", f"{typ} has no {key}"
        if value is None:
            continue
        if not value_matches(float(got[key]), value):
            return "FAIL", f"{typ} {key}={got[key]}, expected {value}"
    return "PASS", ""


def value_matches(got, value):
    """value: a number, "+" / "-" (the sign only), or ["abs", n] (the magnitude)."""
    if value == "+":
        return got > 0
    if value == "-":
        return got < 0
    if isinstance(value, list):
        return abs(abs(got) - value[1]) <= TOLERANCE
    return abs(got - float(value)) <= TOLERANCE
