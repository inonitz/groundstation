"""Text parsing for the vision commands: what to highlight, what to count, and ASCII-safe text.

Pure string work, no models. The dispatch uses parse_count and parse_highlight to pick the task type;
the overlay uses ascii_only because cv2.putText draws ASCII only. Moved here from perception/engine.py
on 2026-09-22 (owner ruling: one utility module inside perception2).
"""
import re

# Verbs that open a highlight request. follow / focus on / emphasize were added 2026-09-08: both
# translators render עקוב, התמקד and הדגש with them, and every such request had been falling
# through to a plain VLM question in two live runs (sessions 2026-09-08 REPORT.md).
CLEAR_RE = re.compile(r"\b(?:stop (?:highlight\w*|track\w*|follow\w*)|clear|reset|deselect|never ?mind)\b", re.I)
_HL_VERBS = r"highlight|locate|track|follow|mark|find|show me|point (?:at|to)|focus on|emphasi[sz]e"
LEAD_VERB_RE = re.compile(rf"^(?:{_HL_VERBS})\s+(?:the |a |an |that |my )?", re.I)
FIND_RE = re.compile(rf"\b(?:{_HL_VERBS}|where(?:'s| is| are))\s+(?:the |a |an |that |my )?(.+)", re.I)
FILLER_RE = re.compile(r"\b(?:please|for me|in the (?:frame|image|scene|room|camera)|right now|thank you|thanks)\b.*$", re.I)
COUNT_RE = re.compile(r"^\s*count (?:the |all (?:the )?)?(.+?)[.!?]*\s*$", re.I)


def parse_count(text):
    """'count the red cars' -> 'red cars'; anything else -> None. harden2 (owner ruling 2026-09-08):
    counting is SAM3's job, not the VLM's (Gemma counted 2/26 on the bench)."""
    m = COUNT_RE.match(text or "")
    if not m:
        return None
    return m.group(1).strip()


def parse_highlight(text):
    """'highlight the red backpack' -> 'red backpack'; 'clear' -> ''; anything else -> None."""
    if CLEAR_RE.search(text):
        return ""
    m = FIND_RE.search(text)
    if not m:
        return None
    phrase = FILLER_RE.sub("", m.group(1)).strip().strip(".?! ,")
    if phrase:
        phrase = LEAD_VERB_RE.sub("", phrase).strip()
    return phrase or None


def ascii_only(s):
    """Drop non-ASCII characters; cv2.putText cannot draw them."""
    return (s or "").encode("ascii", "ignore").decode("ascii")


def selftest():
    """Parser cases, moved from the engine self-test on 2026-09-22."""
    bad = []
    for text, want in (("Follow the white car", "white car"),
                       ("Focus on the middle windows of the rightmost building.", "middle windows of the rightmost building"),
                       ("Emphasize all vehicles", "all vehicles"),
                       ("Emphasise the chimney of the lowest house", "chimney of the lowest house"),
                       ("stop following", ""),
                       ("what do you see now", None),
                       ("Do not follow-up on that", None)):
        if parse_highlight(text) != want:
            bad.append(f"parse_highlight({text!r}) -> {parse_highlight(text)!r}, want {want!r}")
    if parse_highlight("highlight the red backpack please") != "red backpack":
        bad.append("parse: basic")
    if parse_highlight("clear") != "":
        bad.append("parse: clear")
    if parse_highlight("how many people do you see") is not None:
        bad.append("parse: question must not become a target")
    return bad
