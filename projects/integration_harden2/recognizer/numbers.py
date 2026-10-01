"""Reading numbers from a sentence: Hebrew and English, digits and number words. Stage 2
(the bare-meter rewrite) and the number guard share it, so both read a number the SAME
way.

The number guard verifies, it does not trust. Hebrew numbers are read by the SAME
composer that stage 2 uses (util.hebrew.hebnum_to_digits; the old ad-hoc summer could not
compose hundreds: שלוש מאות read as 3). This file only pre-normalizes the vocabulary the
digitizer deliberately leaves alone: construct-state numerals, the fractions (util.hebrew
FRACTIONS: חצי, רבע, שליש, שמינית), and the bare-מטר rule. A number may carry any of
the seven front letters (util.hebrew FRONT_LETTERS).
"""
import re

from util.hebrew import (
    FRACTION_PLURALS,
    FRACTIONS,
    FRONT_LETTERS,
    NUM_WORDS,
    hebnum_to_digits,
)

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


def is_number_word(word):
    """Digits, a number word, a construct numeral, or a fraction."""
    return (
        bool(re.fullmatch(r"\d+(?:\.\d+)?", word))
        or word in NUM_WORDS
        or word in CONSTRUCT_NUM
        or word in FRACTIONS
        or word in FRACTION_PLURALS
    )


def is_number_token(token):
    """A number token, with or without one front letter (ב-5, ו5, בחמישה, ורבע).
    Trailing punctuation is ignored."""
    word = token.rstrip(_PUNCT)
    rest = ""
    if is_number_word(word):
        return True
    if word[:1] in FRONT_LETTERS:
        rest = word[1:].lstrip("-")
    return is_number_word(rest)


def meter_has_number(before, after):
    """Does a מטר between the words `before` and `after` carry its own number?
    Hebrew puts the number on either side (חמישה מטר / מטר אחד). A number AFTER it
    that starts with ו ("and") begins the NEXT item (מטר וחמישה מטר), except a
    fraction (מטר וחצי = 1.5 m, מטר ורבע = 1.25 m)."""
    if is_number_token(before):
        return True
    if after.startswith("ו"):
        return after.rstrip(_PUNCT)[1:] in FRACTIONS
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


# A fraction of a ROTATION is degrees, not the number: "חצי סיבוב" read as 0.5 made the
# guard overwrite DictaLM's correct "Turn right 180 degrees" with "0.5 degrees" (live
# 2026-09-06, traces/session-20260906-231146.jsonl utterance 30). So חצי סיבוב = 180,
# רבע סיבוב = 90, שלושת רבעי סיבוב = 270, סיבוב וחצי = 540. A front letter can ride on a
# fraction (שחצי פתוח = that is half open): live 2026-09-08 rejected that sentence three
# times because the bare pattern missed it.
_FRONT = "".join(FRONT_LETTERS)
_FRACTION = "|".join(FRACTIONS)
_PLURAL = "|".join(FRACTION_PLURALS)
_TURN = "(?:סיבוב|הקפה)"
HE_COUNTED_TURN_RE = re.compile(rf"(?<!\S)(\d+)\s+({_PLURAL})\s+{_TURN}(?!\S)")
HE_FRACTION_TURN_RE = re.compile(rf"(?<![^\s{_FRONT}])({_FRACTION})\s+{_TURN}(?!\S)")
HE_TURN_AND_FRACTION_RE = re.compile(rf"(?<!\S){_TURN}\s+ו({_FRACTION})(?!\S)")
HE_COUNTED_RE = re.compile(rf"(?<!\S)(\d+)\s+({_PLURAL})(?!\S)")
HE_AND_FRACTION_RE = re.compile(rf"(\d+(?:\.\d+)?)\s+ו({_FRACTION})(?!\S)")
HE_METER_AND_FRACTION_RE = re.compile(rf"(?<!\S)מטר\s+ו({_FRACTION})(?!\S)")
HE_FRACTION_RE = re.compile(rf"(?<!\S)[{_FRONT}]?({_FRACTION})(?!\S)")
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
    """'N and a half' -> N + 0.5, as text."""
    return str(float(m.group(1)) + 0.5)


def _number(value):
    """A value as text, 3 decimals at most (a third)."""
    return str(round(value, 3))


def _meter_and_fraction(m):
    """מטר ורבע -> '1.25 מטר'."""
    return _number(1 + FRACTIONS[m.group(1)]) + " מטר"


def read_fractions(s):
    """Every Hebrew fraction in s -> digits (after hebnum_to_digits, so a count before a
    fraction is already digits: 3 רבעי סיבוב)."""
    def counted_turn(m):
        return _number(int(m.group(1)) * FRACTION_PLURALS[m.group(2)] * 360)

    def fraction_turn(m):
        return _number(FRACTIONS[m.group(1)] * 360)

    def turn_and_fraction(m):
        return _number((1 + FRACTIONS[m.group(1)]) * 360)

    def counted(m):
        return _number(int(m.group(1)) * FRACTION_PLURALS[m.group(2)])

    def and_fraction(m):
        return _number(float(m.group(1)) + FRACTIONS[m.group(2)])

    def fraction(m):
        return _number(FRACTIONS[m.group(1)])

    s = HE_COUNTED_TURN_RE.sub(counted_turn, s)
    s = HE_FRACTION_TURN_RE.sub(fraction_turn, s)
    s = HE_TURN_AND_FRACTION_RE.sub(turn_and_fraction, s)
    s = HE_COUNTED_RE.sub(counted, s)
    s = HE_AND_FRACTION_RE.sub(and_fraction, s)
    s = HE_FRACTION_RE.sub(fraction, s)
    return s


def nums_he(s):
    """Every number in a Hebrew sentence, digits and composed number words, sorted.
    A bare singular unit counts as one (מטר = 1, מטר וחצי = 1.5) -- both were measured
    causes of false rejections. Composition is delegated to hebnum_to_digits, so hundreds
    (שלוש מאות = 300) and the article exclusion behave exactly as in stage 2. Unlike
    stage 2, it also reads a number word with a front letter (בחמישה = 5)."""
    core = ""
    prefix = ""
    bare_meters = 0
    norm = []

    # "חמישה..." -> "חמישה", "מטר." -> "מטר"
    s = GLUED_PUNCT_RE.sub("", s)
    s = HE_METER_AND_FRACTION_RE.sub(_meter_and_fraction, s)     # מטר ורבע = 1.25
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

    s = hebnum_to_digits(" ".join(norm), front_letters=True)
    s = read_fractions(s)
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
