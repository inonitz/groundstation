"""The recognizer's guards: they refuse what must not fly, before or after the Gemma
call.

  negation_only       a PURE action-negation ("do not move") is refused before the model
  numbers_vs_mission  every number spoken must appear in the planned mission
  is_shot_echo        a plan that copies one of the planner's own examples is refused
"""
import json
import re

from .numbers import nums_en, nums_he
from .prompts import PLANNER_SHOTS_D


def mission_numbers(mission):
    """Every number in a mission's steps, as a magnitude."""
    nums = set()
    for step in mission:
        for k, v in step.items():
            if k != "type" and isinstance(v, (int, float)):
                nums.add(abs(float(v)))
    return nums


# ================================ the number guard ================================
def numbers_vs_mission(he2, mission):
    """The number guard for the direct path: every number spoken in the Hebrew must
    appear in the mission (magnitude). Returns the list of missing numbers ([] = ok)."""
    said = {abs(float(x)) for x in nums_he(he2)}
    got = mission_numbers(mission or [])
    return sorted(x for x in said if x not in got)


# ============================ the planner-echo guard =============================
def _shot_missions():
    """The planner's own few-shot missions (the non-empty ones). They are our own
    constants: json.loads cannot fail on them unless the constants are broken, and a
    broken constant is a bug for the crash hook."""
    out = []
    for _, answer in PLANNER_SHOTS_D:
        mission = json.loads(answer)
        if mission:
            out.append(mission)
    return out


# A planned mission identical to one of these, from an input that carries none of that
# example's numbers, is a COPY of the example, not a plan (live 2026-09-08 u74).
SHOT_MISSIONS = _shot_missions()


def is_shot_echo(english, mission):
    nums = set()
    for shot in SHOT_MISSIONS:
        if mission != shot:
            continue

        nums = mission_numbers(shot)
        if not nums or not (set(nums_en(english)) & nums):
            return True
    return False


# ============================== the negation guard ===============================
# Negation guard (2026-09-10): refuse a PURE action-negation with NO positive order,
# deterministically, BEFORE the Gemma call. Defense-in-depth for the safety-critical
# negation class. Clause-based; errs toward NOT rejecting (zero false fires). Design +
# evidence: docs/active/2026-09-10-guard-and-config-workplan.md A2.
_NEG_TRIG = re.compile(r"(?:בשום אופן\s+)?(?:אל\s+ת\S+|בלי\s+ל\S+|לא\s+ל\S+)")
_POS_IMP = re.compile(
    r"(?<![א-ת])ו?(?:תטוס|טוס|תעלה|עלה|תרד|רד|תסתובב|הסתובב|תפנה|פנה|תסע|סע|תזוז|זוז"
    r"|תמריא|המריא|תנחת|נחת|תעוף|עוף|תחזור|חזור|בוא|תמשיך|המשך|תאט|האט|תאיץ|האץ"
    r"|תעצור|עצור|שים|סמן|תסמן|עקוב|תעקוב|ספור|תספור|תאר|תתאר|צלם|תצלם|חפש|תחפש"
    r"|הראה|תראה|מצא|תמצא|שמור|תשמור|זהה|תזהה)(?![א-ת])"
)
_NUM_UNIT = re.compile(r"(?<![א-ת])(?:מטר|מטרים|מעלות|שניות)(?![א-ת])")
_CLAUSE_SPLIT = re.compile(r"[,.;]|\bואז\b|\bאבל\b|\bורק\b|\bאולם\b")


def negation_only(he):
    """True iff the utterance is a PURE action-negation: at least one negated action
    clause and NO clause carrying a positive order. The negation trigger consumes its own
    verb, so a positive imperative that survives the removal is a separate, real order. A
    bare number+unit counts as an order only when the clause has no negation. Errs toward
    NOT rejecting (zero false fires)."""
    rest = ""
    has_neg = False
    neg_found = False
    pos_found = False

    for cl in _CLAUSE_SPLIT.split(he or ""):
        cl = cl.strip()
        if not cl:
            continue

        # drop the negated verbs; an order verb left behind is genuine
        rest = _NEG_TRIG.sub(" ", cl)
        has_neg = rest != cl
        if _POS_IMP.search(rest):
            pos_found = True
        elif has_neg:
            neg_found = True
        elif _NUM_UNIT.search(rest):
            pos_found = True
    return neg_found and not pos_found
