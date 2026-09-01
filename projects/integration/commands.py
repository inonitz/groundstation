"""Deterministic voice->verb grammar for the Tier-1 fast path.

The command regexes here are ported VERBATIM from the recon-swarm Android app
(`res/values/strings.xml`, the `command_*` entries) that `voice/SpeechResolving.kt`
uses as a *canonicalisation* stage before its on-phone LLM. We reuse the SAME patterns,
but as a TERMINAL classifier: a match dispatches a bounded deterministic verb straight
to the DJI wire, with NO LLM in the loop (per the "LLM out of the control loop" rule).

WHY faithful-but-reordered: the dev's patterns were written to feed an LLM that
disambiguates afterwards, so they overlap on purpose -- e.g. `command_land` swallows
"down", "off", "plan", which also collide with `go_down`. As a terminal flight
classifier those overlaps misfire (say "go down" and you'd LAND). So the PATTERNS are
unchanged, but the PRIORITY ORDER is ours: directional verbs are matched before `land`.
`test_router.py` exercises the ambiguous phrases so the behaviour is visible. Tighten a
pattern only with the human's sign-off -- do not silently diverge from the dev's app.
"""
import os
import re
from dataclasses import dataclass
from enum import Enum


class Tier(Enum):
    EMERGENCY = "emergency"   # highest priority; checked first, works even in manual mode
    OVERRIDE = "override"     # hand authority back to the RC (manual control)
    RESUME = "resume"         # take authority back from manual
    BASIC = "basic"           # deterministic verb -> wire
    COMPLEX = "complex"       # everything else -> perception engine


@dataclass(frozen=True)
class Command:
    tier: Tier
    name: str            # canonical verb, e.g. "takeoff", "go_down"; "" for non-basic tiers
    param: str = ""      # captured group(1) if the pattern extracts one (e.g. scan target)
    text: str = ""       # the original transcript, for the complex handler


# A flight verb only fires as a TERMINAL command on a SHORT imperative. Longer utterances
# are treated as questions for perception -- otherwise "is the drone going to land" would LAND
# the aircraft mid-question. Emergency/override stay length-independent (a false hover is safer
# than a missed stop). Tune with MVD_MAX_CMD_WORDS.
MAX_BASIC_WORDS = int(os.environ.get("MVD_MAX_CMD_WORDS", "4"))


# --- Tier 4 / Tier 3 vocab -------------------------------------------------------------
# Emergency is deliberately broad and word-bounded. "stop" is the dev's own WS kill word
# (ApiServer.kt: Regex("bye|x|stop")). These take priority over every other tier.
_EMERGENCY_RE = re.compile(r"\b(stop|emergency|abort|halt|freeze|mayday|kill|cut)\b", re.I)
_OVERRIDE_RE = re.compile(r"\b(manual|override|take over|i have control|my control|disengage)\b", re.I)
_RESUME_RE = re.compile(r"\b(resume|auto|autonomous|you have control|take control)\b", re.I)
# A movement intent ("go/move/head ...") that matches NO direction -> a no-op with feedback,
# so "go dance"/a mis-heard word never falls through to the perception engine (scene-describe).
_MOVE_INTENT_RE = re.compile(r"^\s*(go|move|head)\b", re.I)


# --- Tier 1: the 9 safe deterministic verbs --------------------------------------------
# Ordered on purpose (see module docstring): directional verbs BEFORE `land`.
# Patterns are copied verbatim from strings.xml.
# ORDER MATTERS: explicit directionals (forward/backward/right/left) come BEFORE the short
# up/down, else "back up" matches the 'up' in go_up and the drone climbs. Verified by test_router.
_BASIC_PATTERNS = [
    ("come_home",      r"come (back|home)|go home|return home"),
    # gimbal BEFORE directionals: "look up/down" must not hit go_up/go_down.
    ("gimbal_forward", r"(look|camera|face) (forward|ahead|straight)"),
    ("gimbal_down",    r"(look|camera|gimbal) down"),
    ("gimbal_up",      r"(look|camera|gimbal) up"),
    ("go_forward",     r"(go )?forwards?"),
    ("go_backward",    r"(go )?(back(ward)?s?( up)?)"),
    ("go_right",       r"(go )?right(ward(s)?)?"),
    ("go_left",        r"(go )?left(ward(s)?)?"),
    ("go_up",          r"(go )?(up|rise|high)"),
    ("go_down",        r"(go )?(down|under|low)"),
    ("track",          r"looking at you|(look|watch|track)( at)? (me|us)"),
    ("follow",         r"follow me|follow him|follow"),
    ("scan",           r"scan(?:\s+(.+))?"),
    ("search",         r"search|recon(naissance)?"),
    ("wave",           r"hello|hey|heya|hiya|\bhi\b|wave|how are you|how'?s it going"),
    ("spin",           r"spin|((spin|look) around)"),
    ("takeoff",        r"takeoff|take off|fly|sky|liftoff|wakeup|sunshine|morning"),
    ("land",           r"land|landing|ground|down|fall|perch|floor|shutdown|shut down|night|off|turn off|sleep|sunset|plan|planned"),
]
_BASIC = [(name, re.compile(rf"\b(?:{pat})\b", re.I)) for name, pat in _BASIC_PATTERNS]


def classify(text: str) -> Command:
    """Map a transcript to exactly one Command, honouring tier priority:
    emergency > override/resume > basic verb > complex (fallthrough to perception)."""
    t = (text or "").strip()
    if not t:
        return Command(Tier.COMPLEX, "", text=t)

    if _EMERGENCY_RE.search(t):
        return Command(Tier.EMERGENCY, "stop", text=t)
    if _OVERRIDE_RE.search(t):
        return Command(Tier.OVERRIDE, "override", text=t)
    if _RESUME_RE.search(t):
        return Command(Tier.RESUME, "resume", text=t)

    # Length guard: skip terminal flight verbs on long (question-like) utterances.
    if len(t.split()) <= MAX_BASIC_WORDS:
        for name, rx in _BASIC:
            if rx.search(t):
                return Command(Tier.BASIC, name, text=t)
        if _MOVE_INTENT_RE.search(t):                 # movement intent, unrecognized direction
            return Command(Tier.BASIC, "unknown_move", text=t)

    return Command(Tier.COMPLEX, "", text=t)
