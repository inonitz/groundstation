"""Stage 2 of the recognizer: the Hebrew rewrites that make a sentence survivable before
the Gemma call. Everything here exists because a measured failure demanded it. Every
rule carries positives (must fire) and negatives (must not fire); test/test_recognizer.py
checks both. Ship criterion (owner 2026-09-02): zero false fires, measured accuracy lift.
"""
import re

from util.hebrew import HE, hebnum_to_digits
from .numbers import is_bare_meter


class Rule:
    """One rewrite: a pattern, its replacement, and the evidence it is safe."""

    def __init__(self, name, pattern, repl, negatives=(), positives=()):
        self.name = name
        self.re = re.compile(pattern)
        self.repl = repl
        self.negatives = negatives      # strings the rule must leave untouched
        self.positives = positives      # strings the rule must change

    def apply(self, s):
        return self.re.sub(self.repl, s)


# Everything here exists because a measured failure demanded it. Order matters:
# digits first (the other rules then only handle digits), inline words, verb insertion,
# then the glossary rules.

def he_word(core, prefixes=""):
    """Canonical Hebrew word boundary: clitic prefixes break \\b, so the boundary is a
    non-Hebrew lookaround on both sides. Hand-rolled (?<![HE])...(?![HE]) patterns in the
    rule tables must stay in sync with this shape."""
    return rf"(?<![{HE}]){prefixes}{core}(?![{HE}])"


# 2a. Number words -> digits: util/hebrew.py (hebnum_to_digits), shared with log/.


# 2b. Measured trouble words are written as English inline: DictaLM copies Latin tokens
# through verbatim (probed 2026-09-02), so no reverse mapping is needed. An entry
# requires at least two measured mistranslations.
INLINE_WORDS = [
    ("כתומה", "orange"),
    ("כתום", "orange"),
    ("גדר", "fence"),
    ("אפוד", "vest"),
]


def inline_english(s):
    for he, en in INLINE_WORDS:
        s = re.sub(he_word(f"ה{he}"), f"ה-{en}", s)
        s = re.sub(he_word(f"{he}", "(ב|ל|מ)?"), lambda m: (m.group(1) or "") + en, s)
    return s


# 2c. A direction with no verb after a connective merges into the previous rotation when
# translated ("then right two meters" -> "turn right two meters"). Inserting זוז at the
# source prevents the merge.
BARE_DIRECTION_RE = re.compile(
    r"(ואז|ואחר כך|אחרי זה|לאחר מכן|,)\s+(ימינה|שמאלה|קדימה|אחורה|למעלה|למטה)\s+(?=\d)"
)


def add_missing_verb(s):
    return BARE_DIRECTION_RE.sub(lambda m: f"{m.group(1)} זוז {m.group(2)} ", s)


# 2c'. A bare מטר (no number on either side) is written out as מטר אחד before
# translation: Hy-MT2 rendered "רד מטר" as "six meters" twice (live 2026-09-08, lines 11
# and 61; the guard caught both). The neighbour test is the guard's own bare-unit rule.
# Runs AFTER hebnum-digits, so "חמישה עשר מטר" is already "15 מטר" and untouched;
# "מטר וחצי" and "מטר אחד" are untouched.

def explicit_one_meter(s):
    toks = s.split()
    out = []

    for i, tok in enumerate(toks):
        if is_bare_meter(toks, i):
            tok = tok.replace("מטר", "מטר אחד", 1)
        out.append(tok)
    return " ".join(out)


# 2d. Glossary rules: acronym expansion, radio-procedure words, homographs, slang.
# owner ruling 2026-09-08 ("hardwire them"): possibility / let's / absolute-altitude
# register -> imperative BEFORE the translator, so Hy-MT2's "It is possible to take off"
# never reaches the planner. Questions (? / האם) are left alone.
_INF2IMP = {
    "להמריא": "תמריא",
    "לנחות": "תנחת",
    "לטוס": "טוס",
    "לעלות": "עלה",
    "לרדת": "רד",
    "להסתובב": "הסתובב",
    "לזוז": "זוז",
    "לפנות": "פנה",
    "להתקדם": "התקדם",
    "לחזור": "חזור",
    "להתרומם": "התרומם",
    "לטפס": "טפס",
}
HE_POSSIBLE_RE = re.compile(r"(?<!\S)(?:אפשר|יש אפשרות)\s+(ל\S+)")
HE_LETS_RE = re.compile(r"(?<!\S)בוא(?:י|ו)?\s+נ(\S+)")
HE_TO_ALT_RE = re.compile(
    r"(?<!\S)(עלה|תעלה|טפס|תטפס|התרומם|תתרומם|רד|תרד)\s+לגובה\s+(?:של\s+)?"
    r"(?=(?:\S+\s+){1,4}מטר)"
)


def register_imperative(s):
    if s.rstrip().endswith("?") or s.lstrip().startswith("האם"):
        return s

    # אפשר להמריא -> תמריא (unknown verb: untouched)
    s = HE_POSSIBLE_RE.sub(lambda m: _INF2IMP.get(m.group(1), m.group(0)), s)
    # בוא נרד -> תרד ; בוא נמריא -> תמריא
    s = HE_LETS_RE.sub(lambda m: "ת" + m.group(1), s)
    # עלה לגובה עשרה מטרים -> עלה עשרה מטרים (dataset: relative)
    s = HE_TO_ALT_RE.sub(lambda m: m.group(1) + " ", s)
    return s


HE_RULES = [
    Rule("acronym-grid", r"נ\.צ\.|\bנ\.?צ\b", "נקודת הציון",
         negatives=["נץ עף מעל השדה"], positives=["עבור לנ.צ. שנתתי לך"]),
    Rule("acronym-cp", r'(?<![֐-׿])[ובלשכמ]?ה?חפ"ק(?![֐-׿])', "עמדת הפיקוד",
         negatives=[], positives=['יש קשר עין עם החפ"ק', 'מהחפ"ק נמסר']),
    Rule("acronym-uav", r'(?<![֐-׿])[ובלשכמ]?ה?כטב"ם(?![֐-׿])', "כלי הטיס הבלתי מאויש",
         negatives=[], positives=['אבד קשר עם הכטב"ם']),
    Rule("abbrev-point", r"(?<![֐-׿])([ובלשכמה]{0,2})נק'\s+", r"\1נקודת ",
         negatives=["חוזר לנקודה"], positives=["חוזר לנק' האיסוף", "נק' המפגש"]),
    Rule("proc-roger", r"^רות,\s*", "קיבלתי, ",
         negatives=["רותם ממשיכה בסריקה", "רות ואני נפגשים"],
         positives=["רות, ממשיך בסריקה"]),
    Rule("proc-over-final", r",\s*עבור\s*$", "",
         negatives=["תעבור לעמדה הבאה", "זה עבורך", "עצור לפני שתמשיך, עבורי זה חשוב"],
         positives=["ממשיך בסריקה, עבור"]),
    Rule("proc-out-final", r",\s*סוף\s*$", "",
         negatives=["חוזר לנקודת האיסוף", "טוס עד סוף הרחוב"],
         positives=["שנתתי לך, סוף"]),
    Rule("takeoff-homograph", r"^המראה(?=$|,|!|\s+(?:מיידית|עכשיו|מהירה|דחופה)\b)",
         "בצע המראה",
         negatives=["המראה שבורה בחדר", "תבדוק את המראה של הרחפן",
                    "המראה של הרחפן מלוכלכת"],
         positives=["המראה מיידית", "המראה", "המראה, יש הקפצה"]),
    Rule("feet-unit", r"(\bמאות?|עשרות|אלף|\d+)\s+רגל\b", r"\1 פיט",
         negatives=["הכלב הרים רגל", "רגל של השולחן שבורה"],
         positives=["שמונה מאות רגל"]),
    Rule("slang-sector", r"(?<![֐-׿])([וש]?(?:ב|ל|מה|ה))גזרה(?![֐-׿])", r"\1אזור",
         negatives=["גזר במרק", "הגוזרת גזרה", "גזרה עליו הגורל"],
         positives=["סריקה בגזרה הצפונית", "הגזרה שלך", "נכנס לגזרה שלך"]),
    Rule("slang-scramble", r"\bיש הקפצה\b", "יש משימת חירום",
         negatives=[], positives=["המראה מיידית, יש הקפצה"]),
    # Rotation sense as inline English: Hy-MT2 (the deployed translator, ruling
    # 2026-09-07) renders "עם כיוון השעון" as "counter-clockwise" -- a sign FLIP the
    # guards cannot see. Measured on the 2026-09-07 hymt2 run: combo3, combo5,
    # v_finish3_g3 (wrong-degrees -90 vs 90). The inline mechanism carries the fix; a
    # leading ו (ועם / ונגד) is kept in front of the Latin token.
    Rule("clockwise-inline", r"(?<![֐-׿])(ו?)עם כיוון השעון(?![֐-׿])", r"\1clockwise",
         negatives=["טוס עם הרוח", "עם כיוון הרוח", "סמן את השעון על הקיר",
                    "כיוון השעון שגוי"],
         positives=["הסתובב 90 מעלות עם כיוון השעון", "ועם כיוון השעון",
                    "תעשה חצי סיבוב עם כיוון השעון"]),
    Rule("counterclockwise-inline", r"(?<![֐-׿])(ו?)נגד כיוון השעון(?![֐-׿])",
         r"\1counterclockwise",
         negatives=["טוס נגד הרוח", "נגד כיוון הרוח", "הוא נגד השעון החדש"],
         positives=["הסתובב 45 מעלות נגד כיוון השעון", "ונגד כיוון השעון"]),
    # Chain-initial takeoff: DictaLM mistranslates the takeoff verb that OPENS a chain
    # ("המראה," became "Perform a landing"; verbose chains became "Fly forward").
    # Measured: combo5, r_mis2-class, v_listen3/v_okso4/v_seq5, live combo_tl
    # 2026-09-02. The inline-English mechanism carries the fix: DictaLM copies Latin
    # tokens through verbatim.
    Rule("takeoff-verb-inline", r"\b(?:תמריא|המרא)\b", "take off",
         negatives=["ההמראה הייתה חלקה", "המראה, עלה 2 מטרים"],
         positives=["תמריא, עלה 3 מטרים ותישאר שם", "המרא ואז טוס קדימה"]),
    # המראה is a homograph (takeoff / the-mirror): fire only as a chain opener (followed
    # by a comma or ואז) and never after על/אל/את (looking AT the mirror).
    Rule("takeoff-noun-inline", r"(?<!על )(?<!אל )(?<!את )\bהמראה(?=\s*,|\s+ואז\b)",
         "take off",
         negatives=["תסתכל על המראה, ואז זוז ימינה", "המראה נמצאת שם",
                    "המראה של הבניין יפה"],
         positives=["המראה, עלה 2 מטרים ונחת", "קודם כל המראה, אחרי זה עלה 5 מטרים",
                    "בצע המראה ואז טוס קדימה"]),
]

# Stage 2 in order: digits first, so every later step only handles digits.
HE_STEPS = (
    ("hebnum-digits", hebnum_to_digits),
    ("inline-english", inline_english),
    ("missing-verb", add_missing_verb),
    ("one-meter", explicit_one_meter),
    ("register", register_imperative),
)


def apply_he(s):
    """All of stage 2, in order.
    Returns the rewritten Hebrew and the names of fired rules."""
    t = ""
    fired = []

    for name, fn in HE_STEPS:
        t = fn(s)
        if t != s:
            fired.append(name)
            s = t

    for rule in HE_RULES:
        t = rule.apply(s)
        if t != s:
            fired.append(rule.name)
            s = t
    return s.strip(), fired
