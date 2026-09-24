"""The fast path: the critical words, matched first, with no model
call. A stop shout must never wait on Gemma, and a false hover is
safer than a missed stop (owner ruling 2026-09-23: the recognizer
parses every command; a critical one goes straight to control).

  emergency -- stop / halt (EN + HE), greedy, works in manual mode too
  manual    -- hand control to the RC
  auto      -- take control back

Priority: emergency > manual > auto. The Hebrew alternates match directly: Python's \\b
treats Hebrew letters as word characters, so the boundaries hold."""
import re

# Greedy by ruling: עצור always stops, even mid-sentence; the same intent stays
# expressible through חכה/המתן.
EMERGENCY_RE = re.compile(
    r"(\b(?:stop|emergency|abort|halt|freeze|mayday|kill|cut"
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
    r"\b(resume|auto|autonomous|you have control|take control"
    r"|אוטומטי|אוטונומי"                # automatic, autonomous
    r"|המשך)\b",                        # continue
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


def emergency(text):
    """True when the sentence contains an emergency word."""
    return bool(EMERGENCY_RE.search(text or ""))


def is_clear(text):
    """True when the sentence asks to clear the highlight (checked after critical())."""
    return bool(CLEAR_RE.search(text or ""))


def critical(text):
    """-> "emergency", "manual", "auto", or None when the sentence is not a critical
    command."""
    t = (text or "").strip()
    if not t:
        return None

    if EMERGENCY_RE.search(t):
        return "emergency"
    if MANUAL_RE.search(t):
        return "manual"
    if AUTO_RE.search(t):
        return "auto"
    return None
