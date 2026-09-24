"""The recognizer's front half: Hebrew utterance in ->
{emergency | manual | auto | clear | mission | reject | direct}. Pure text processing: it
owns no model and starts no server. The recognizer (recognizer.py) calls
recognize_direct() and routes the result; "direct" goes to its one Gemma call.

Execution order, one file per step:
    fast_path.py   critical words and "clear" act before anything else
    bypass.py      full-match sentences become missions with no model call
    guards.py      the negation guard refuses a pure "do not ..." before the model
    rewrites.py    Hebrew rewrites that make the sentence survivable for the model
"""
from .bypass import bypass
from .fast_path import critical, is_clear
from .guards import negation_only
from .rewrites import apply_he


def recognize_direct(he):
    """harden2: the Hebrew front half. Stage 0 the fast path (emergency /
    manual / auto -> that kind), stage 1 bypass (deterministic missions,
    no model), the negation guard, stage 2 Hebrew rewrites; then
    ("direct", he2, flags) for the pipeline's single Gemma call."""
    he = he or ""                 # never crash the stage-0 regex on a None transcript

    kind = critical(he)
    if kind is not None:
        return (kind, None, [])
    if is_clear(he):
        return ("clear", None, [])

    mission = bypass(he)
    if mission is not None:
        return ("mission", mission, [])

    if negation_only(he):
        return ("reject", he, ["neg-guard"])

    he2, flags = apply_he(he)
    return ("direct", he2, flags)
