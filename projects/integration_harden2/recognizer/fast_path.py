"""The fast path: the critical words, matched first, with no model
call. A stop shout must never wait on Gemma, and a false hover is
safer than a missed stop (owner ruling 2026-09-23: the recognizer
parses every command; a critical one goes straight to control).

  emergency -- stop / halt (EN + HE), greedy, works in manual mode too
  manual    -- hand control to the RC
  auto      -- take control back

Priority: emergency > manual > auto. The Hebrew alternates match directly: Python's \\b
treats Hebrew letters as word characters, so the boundaries hold.

A stop word halts in every mode, unless the sentence gives a duration: "stop for 10
seconds" is a wait, which the bypass plans (owner STOP1 (3), 2026-10-02). Auto is a
trigger word: it acts only as the whole sentence, so "continue forward 5 m" is a
command, not a mode switch (owner AUTO1, 2026-10-02)."""
import re

from util.hebrew import hebnum_to_digits

# Greedy by ruling: עצור always stops, even mid-sentence; the same intent stays
# expressible through חכה/המתן.
EMERGENCY_RE = re.compile(
    # "stop tracking" clears a perception job, as the Hebrew below (owner 2026-09-08)
    r"(\b(?:stop(?!\s+(?:highlight|track|follow|mark|count)\w*)"
    r"|emergency|abort|halt|freeze|mayday|kill|cut"
    r"|עצור|עצרי|עצרו|תעצור|תעצרי|תעצרו"
    r"|סטופ|חירום)\b"
    # owner ruling 2026-09-08: הפסק / תפסיק stop too -- unless they stop a PERCEPTION
    # job ("תפסיק לעקוב" = clear the highlight, not the aircraft); די only as the whole
    # utterance or its last word ("טוס די מהר" is an adverb).
    r"|\b(?:הפסק|הפסיקי|הפסיקו|תפסיק|תפסיקי|תפסיקו)\b"
    r"(?!\s+ל(?:עקוב|הדגיש|סמן|הראות|צלם|ספור))"
    r"|(?<!\S)(?:די|מספיק)(?:[,!.]?\s+(?:די|מספיק))*(?=\s*[!.?]*\s*$))",
    re.I
)
MANUAL_RE = re.compile(
    r"\b(manual|override|take over|i have control|my control|disengage"
    r"|ידני|ידנית"                      # manual
    r"|אני בשליטה)\b",                   # I am in control
    re.I
)
AUTO_RE = re.compile(
    r"(?:resume|auto|autonomous|you have control|take control"
    r"|אוטומטי|אוטונומי"                # automatic, autonomous
    r"|המשך)",                          # continue
    re.I
)
# Words a trigger may carry and stay a trigger: "המשך בבקשה" is still the auto word.
FILLER_RE = re.compile(r"\b(?:please|now|drone|the|בבקשה|עכשיו|רחפן|הרחפן)\b", re.I)
# A number with a time unit, after number words become digits ("לעשר שניות" -> 10).
DURATION_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:שניות|שנייה|שניה|דקות|דקה|seconds?|secs?|minutes?)\b",
    re.I
)


# Stop a PERCEPTION job ("clear the highlight"), not the aircraft. English from the old
# text parser; Hebrew = the phrases the emergency regex already leaves to perception
# (owner ruling 2026-09-08: "תפסיק לעקוב" = clear the highlight).
CLEAR_RE = re.compile(
    r"\b(?:stop (?:highlight\w*|track\w*|follow\w*)|clear|reset|deselect|never ?mind)\b"
    r"|\b(?:הפסק|הפסיקי|הפסיקו|תפסיק|תפסיקי|תפסיקו)"
    r"\s+ל(?:עקוב|הדגיש|סמן|הראות|צלם|ספור)",
    re.I
)


def has_duration(text):
    """True when the sentence gives a time span ("for 10 seconds")."""
    return bool(DURATION_RE.search(hebnum_to_digits(text or "", front_letters=True)))


def emergency(text):
    """True when the sentence holds a stop word and no duration."""
    t = text or ""
    return bool(EMERGENCY_RE.search(t)) and not has_duration(t)


def bare(text):
    """The sentence without punctuation and fillers, single-spaced."""
    t = re.sub(r"[^\w\s]", " ", text or "")
    t = FILLER_RE.sub(" ", t)
    return " ".join(t.split())


def is_clear(text):
    """True when the sentence asks to clear the highlight (checked after critical())."""
    return bool(CLEAR_RE.search(text or ""))


def critical(text):
    """-> "emergency", "manual", "auto", or None when the sentence is not a critical
    command."""
    t = (text or "").strip()
    if not t:
        return None

    if emergency(t):
        return "emergency"
    if MANUAL_RE.search(t):
        return "manual"
    if AUTO_RE.fullmatch(bare(t)):
        return "auto"
    return None
