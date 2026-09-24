"""Reading numbers from a sentence: Hebrew and English, digits and number words. Stage 2
(the bare-meter rewrite) and the number guard share it, so both read a number the SAME
way.

The number guard verifies, it does not trust. Hebrew numbers are read by the SAME
composer that stage 2 uses (util.hebrew.hebnum_to_digits; the old ad-hoc summer could not
compose hundreds: שלוש מאות read as 3). This file only pre-normalizes the vocabulary the
digitizer deliberately leaves alone: construct-state numerals, חצי, and the bare-מטר
rule.
"""
import re

from util.hebrew import NUM_WORDS, hebnum_to_digits

# Construct-state numerals (שלושת האנשים = the three people) -> plain composer forms.
CONSTRUCT_NUM = {
    "שלושת": "שלושה",
    "ארבעת": "ארבעה",
    "חמשת": "חמישה",
    "ששת": "שישה",
    "שבעת": "שבעה",
    "שמונת": "שמונה",
    "תשעת": "תשעה",
    "עשרת": "עשרה",
}

_PUNCT = ".,!?;:"


def is_number_token(token):
    """A number token: digits, a number word, a construct numeral, or חצי with a clitic
    prefix. A leading ו ("and") and trailing punctuation are ignored."""
    core = token.rstrip(_PUNCT).lstrip("ו")
    return (
        bool(re.fullmatch(r"\d+(?:\.\d+)?", core))
        or core in NUM_WORDS
        or core in CONSTRUCT_NUM
        or core.lstrip("שבלמכה") == "חצי"
    )


def meter_has_number(before, after):
    """Does a מטר between the words `before` and `after` carry its own number?
    Hebrew puts the number on either side (חמישה מטר / מטר אחד). A number AFTER it
    that starts with ו ("and") begins the NEXT item (מטר וחמישה מטר), except וחצי
    (מטר וחצי = 1.5 m)."""
    if is_number_token(before):
        return True
    if after.startswith("ו"):
        return after.rstrip(_PUNCT) == "וחצי"
    return is_number_token(after)


def is_bare_meter(toks, i):
    """toks[i] is מטר with no number of its own: it means ONE meter. Only מטר: the other
    unit words are homographs (שנייה = a moment, מעלה = upward)."""
    before = toks[i - 1] if i else ""
    after = toks[i + 1] if i + 1 < len(toks) else ""
    if toks[i].rstrip(_PUNCT) != "מטר":
        return False
    return not meter_has_number(before, after)

# The guards verify, they do not trust. Hebrew numbers are read by the SAME composer that
# stage 2 uses (the old ad-hoc summer could not compose hundreds: שלוש מאות read as 3).
# The guard only pre-normalizes vocabulary the digitizer deliberately leaves alone:
# construct-state numerals (CONSTRUCT_NUM, stage 2), חצי, and the bare-מטר rule.


EN_NUM = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
    "half": 0.5,
    "halfway": 0.5,
}


# חצי of a ROTATION is 180 degrees, not the number 0.5: "חצי סיבוב" read as 0.5 made the
# guard overwrite DictaLM's correct "Turn right 180 degrees" with "0.5 degrees" (live
# 2026-09-06, traces/session-20260906-231146.jsonl utterance 30). Both extractors compose
# the idiom to 180, so a correct "180 degrees" AND a correct "half a turn" both pass the
# check unpatched. Clitic prefixes ride on חצי too (שחצי פתוח = that is half open): live
# 2026-09-08 rejected that sentence three times because the bare pattern missed it.
# סיבוב וחצי (a turn and a half) is 540.
HE_HALF_TURN_RE = re.compile(r"(?<!\S)(?:[שבלמכה]|ו)?חצי\s+(?:סיבוב|הקפה)(?!\S)")
HE_TURN_HALF_RE = re.compile(r"(?<!\S)סיבוב\s+וחצי(?!\S)")
EN_HALF_TURN_RE = re.compile(
    r"\b(?:a\s+)?half(?:\s+a|\s+an|-)?\s*(?:turn|rotation|revolution|circle|spin)s?\b",
    re.I
)
EN_TURN_HALF_RE = re.compile(
    r"\b(?:(?:one|a|1)\s+and\s+a\s+half\s+(?:turn|rotation|revolution|circle)s?"
    r"|(?:a\s+)?(?:turn|rotation|revolution|circle)\s+and\s+a\s+half"
    r"|1\.5\s+(?:turn|rotation|revolution|circle)s?)\b",
    re.I
)
# Punctuation glued to a word by the ASR ("חמישה...", "מטר.") hid number words and the
# bare-metre rule (live 2026-09-08: three false rejects). Strip trailing punctuation
# clusters; decimals survive.
GLUED_PUNCT_RE = re.compile(r"(?<=\S)[.,!?;:\u2026\"'()]+(?=\s|$)")


def _add_half(m):
    """'N and a half' / 'N וחצי' -> N + 0.5, as text."""
    return str(float(m.group(1)) + 0.5)


def nums_he(s):
    """Every number in a Hebrew sentence, digits and composed number words, sorted.
    A bare singular unit counts as one (מטר = 1, מטר וחצי = 1.5) -- both were measured
    causes of false rejections. Composition is delegated to hebnum_to_digits, so hundreds
    (שלוש מאות = 300) and the article exclusion behave exactly as in stage 2."""
    core = ""
    prefix = ""
    bare_meters = 0
    norm = []

    # "חמישה..." -> "חמישה", "מטר." -> "מטר"
    s = GLUED_PUNCT_RE.sub("", s)
    s = HE_HALF_TURN_RE.sub("180", s)                # חצי סיבוב = 180 degrees, not 0.5
    s = HE_TURN_HALF_RE.sub("540", s)                # סיבוב וחצי = 540 degrees
    s = s.replace("מטר וחצי", "1.5 מטר")
    toks = s.split()

    # a bare מטר counts as one meter (the shared rule: is_bare_meter)
    for i in range(len(toks)):
        if is_bare_meter(toks, i):
            bare_meters += 1

    # Construct numerals -> composer forms; a leading ו stays in front.
    for t in toks:
        core = t.lstrip("ו")
        if core not in CONSTRUCT_NUM:
            norm.append(t)
            continue

        prefix = "ו" if t != core else ""
        norm.append(prefix + CONSTRUCT_NUM[core])

    s = hebnum_to_digits(" ".join(norm))
    s = re.sub(r"(\d+(?:\.\d+)?)\s+וחצי(?!\S)", _add_half, s)
    s = re.sub(r"(?<!\S)(?:[שבלמכה]|ו)?חצי(?!\S)", "0.5", s)
    vals = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    return sorted(vals + [1.0] * bare_meters)


def nums_en(s):
    """Every number in an English sentence; adjacent number words compose (twenty five,
    one hundred twenty, two and a half -- mirroring the Hebrew composer's וחצי)."""
    total = 0
    i = 0

    s = re.sub(r"(\d+(?:\.\d+)?)\s+and\s+a\s+half\b", _add_half, s)
    s = EN_TURN_HALF_RE.sub("540", s)                # one and a half turns = 540 degrees
    s = EN_HALF_TURN_RE.sub("180", s)                # half a turn = 180 degrees, not 0.5
    vals = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    toks = re.findall(r"[a-zA-Z]+", s.lower())

    while i < len(toks):
        if toks[i] not in EN_NUM:
            i += 1
            continue
        # "the one" is an idiom (the one with the open door), not a count.
        if toks[i] == "one" and i and toks[i - 1] == "the":
            i += 1
            continue

        # Compose the run of number words: "hundred" multiplies, the rest add.
        total = EN_NUM[toks[i]]
        i += 1
        while i < len(toks) and (toks[i] in EN_NUM or toks[i] in ("and", "a")):
            if toks[i] not in EN_NUM:
                i += 1
                continue
            if EN_NUM[toks[i]] == 100:
                total = total * 100
            else:
                total = total + EN_NUM[toks[i]]
            i += 1
        vals.append(float(total))
    return sorted(vals)
