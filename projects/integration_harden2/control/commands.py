"""Deterministic safety-tier classifier for the router.

harden2 (2026-09-19): the English BASIC verb regex was RETIRED. Command typing and mission
planning now run through the ONE Gemma call (recognizer.pipeline) -- in Hebrew, directly. This
module keeps ONLY the deterministic tiers that must never depend on a model:

    EMERGENCY  -- stop / halt (EN + HE), checked first, length-independent.
    OVERRIDE   -- hand control to the RC (manual).
    RESUME     -- take control back (auto).

Everything else is COMPLEX and goes to Gemma. These vocabularies stay deterministic on purpose:
a stop shout must never wait on a model, and a false hover is safer than a missed stop. The
Hebrew alternates match DIRECTLY, before any translation hop -- Python's \\b treats Hebrew letters
as word chars, so the boundaries hold.
"""
import re
from dataclasses import dataclass
from enum import Enum


class Tier(Enum):
    EMERGENCY = "emergency"   # highest priority; checked first, works even in manual mode
    OVERRIDE = "override"     # hand authority back to the RC (manual control)
    RESUME = "resume"         # take authority back from manual
    COMPLEX = "complex"       # everything else -> the Gemma recognizer (routes + plans)


@dataclass(frozen=True)
class Command:
    tier: Tier
    name: str            # "stop"/"override"/"resume" for the safety tiers; "" for complex
    text: str = ""       # the original transcript, for the complex handler


# The Recognizer's stage 0 OWNS the emergency vocabulary (EN + HE, greedy); ruled 2026-09-02.
from recognizer.recognizer import EMERGENCY_RE as _EMERGENCY_RE  # noqa: E402
# HE override: "manual"/"manually", "I am in control".
_OVERRIDE_RE = re.compile(
    r"\b(manual|override|take over|i have control|my control|disengage"
    r"|ידני|ידנית"                                 # ידני ידנית
    r"|אני בשליטה)\b", re.I)                      # אני בשליטה
# HE resume: "automatic"/"autonomous", "continue".
_RESUME_RE = re.compile(
    r"\b(resume|auto|autonomous|you have control|take control"
    r"|אוטומטי|אוטונומי"   # אוטומטי אוטונומי
    r"|המשך)\b", re.I)                                                          # המשך


def classify(text: str) -> Command:
    """Map a transcript to a safety tier, else COMPLEX (the Gemma recognizer).
    Priority: emergency > override > resume > complex."""
    t = (text or "").strip()
    if not t:
        return Command(Tier.COMPLEX, "", text=t)
    if _EMERGENCY_RE.search(t):
        return Command(Tier.EMERGENCY, "stop", text=t)
    if _OVERRIDE_RE.search(t):
        return Command(Tier.OVERRIDE, "override", text=t)
    if _RESUME_RE.search(t):
        return Command(Tier.RESUME, "resume", text=t)
    return Command(Tier.COMPLEX, "", text=t)
