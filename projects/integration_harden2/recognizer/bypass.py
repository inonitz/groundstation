"""Stage 1 of the recognizer: the bypass. Canonical short commands are answered
deterministically: zero model risk, zero latency. It runs on the digit-normalized
sentence, so the patterns only need to match digits. Measured coverage: 79 of the 189
standard commands.
"""
import re

from util.hebrew import hebnum_to_digits


AXIS_BY_VERB = {
    "עלה": ("z", 1),
    "תעלה": ("z", 1),
    "טפס": ("z", 1),
    "רד": ("z", -1),
    "תרד": ("z", -1),
}
AXIS_BY_DIRECTION = {
    "קדימה": ("x", 1),
    "אחורה": ("x", -1),
    "ימינה": ("y", 1),
    "שמאלה": ("y", -1),
    "למעלה": ("z", 1),
    "למטה": ("z", -1),
}
ACTION_KEY = {"x": "dx", "y": "dy", "z": "dz"}


def _build_takeoff(m):
    return [{"type": "takeoff"}]


def _build_land(m):
    return [{"type": "land"}]


def _build_spin_clock(m):
    """With the clock (עם) is positive, against it (נגד) is negative."""
    sign = 1 if m.group(3) == "עם" else -1
    return [{"type": "spin_by", "degrees": sign * float(m.group(2))}]


def _build_turn(m):
    """Right (ימינה) is positive, left (שמאלה) is negative."""
    sign = 1 if m.group(1) == "ימינה" else -1
    return [{"type": "spin_by", "degrees": sign * float(m.group(2))}]


def _build_move(m):
    # A neutral verb (טוס) with no direction word is ambiguous: the model decides.
    if m.group(2):
        axis = AXIS_BY_DIRECTION.get(m.group(2))
    else:
        axis = AXIS_BY_VERB.get(m.group(1))
    if axis is None:
        return None

    key = ACTION_KEY[axis[0]]
    return [{"type": "fly_by", key: axis[1] * float(m.group(3))}]


def _build_delay(m):
    return [{"type": "delay", "seconds": float(m.group(1))}]


def _build_full_turn(m):
    """A full turn is clockwise unless the speaker says against the clock (נגד)."""
    degrees = -360.0 if m.group(1) == "נגד" else 360.0
    return [{"type": "spin_by", "degrees": degrees}]


BYPASS_PATTERNS = [
    (
        re.compile(r"^(?:בצע\s+)?(?:המראה|תמריא|המרא)(?:\s+עכשיו)?$"),
        _build_takeoff
    ),
    (
        re.compile(r"^(?:בצע\s+)?(?:נחת|תנחת|נחיתה)(?:\s+עכשיו)?$"),
        _build_land
    ),
    (
        re.compile(
            r"^(הסתובב|תסתובב|פנה)\s+(\d+(?:\.\d+)?)\s+מעלות"
            r"\s+(עם|נגד)\s+כיוון\s+השעון$"
        ),
        _build_spin_clock
    ),
    (
        re.compile(r"^(?:פנה|תפנה)\s+(ימינה|שמאלה)\s+(\d+(?:\.\d+)?)\s+מעלות$"),
        _build_turn
    ),
    (
        re.compile(
            r"^(טוס|תטוס|זוז|תזוז|התקדם|תתקדם|סע|עלה|תעלה|רד|תרד|טפס)\s+"
            r"(?:(קדימה|אחורה|ימינה|שמאלה|למעלה|למטה)\s+)?"
            r"(\d+(?:\.\d+)?)\s+(?:מטרים|מטר)$"
        ),
        _build_move
    ),
    (
        re.compile(r"^(?:חכה|תחכה|המתן|תמתין)\s+(\d+(?:\.\d+)?)\s+שניות$"),
        _build_delay
    ),
    (
        re.compile(r"^עשה\s+סיבוב\s+שלם(?:\s+(עם|נגד)\s+כיוון\s+השעון)?$"),
        _build_full_turn
    ),
]


def bypass(s):
    """Mission-schema mission for a full-match sentence, else None."""
    m = None
    mission = None

    s = hebnum_to_digits(s).strip().rstrip(".!")
    for pattern, build in BYPASS_PATTERNS:
        m = pattern.match(s)
        if not m:
            continue

        mission = build(m)
        if mission is not None:
            return mission
    return None
