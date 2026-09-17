"""The Recognizer: Hebrew utterance in -> {emergency | mission | routed English | rejection}.

This file is the component. It is pure text processing: it owns no model and starts no server.
The live entry is recognize_direct() (direct Hebrew, no translator); stages 0-2 + guards run before the Gemma call.
integration unchanged. bench.py owns the models and the measurements.

File layout follows execution order:
    stage 0  emergency filter     stop words act immediately, before anything else
    stage 1  bypass               full-match sentences become missions with no model call
    stage 2  Hebrew rewrites      make the Hebrew survivable before translation
    stage 3  (external)           the injected translate() callable
    stage 4  output guards        verify the translation against the source
    stage 5  English rewrites     fix known translation defects
    stage 6  routing              command path or perception path
    recognize_direct()            runs the live direct-Hebrew chain
    selftest() + main             `python3 recognizer.py` must print CLEAN before any change ships

Every rewrite rule carries positives (must fire) and negatives (must not fire). The selftest
enforces both. Ship criterion (owner 2026-09-02): zero false fires, measured accuracy lift.
"""
import re


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


# ============================= stage 0: emergency filter =============================
# Copied verbatim from the production router (projects/integration_harden/commands.py,
# _EMERGENCY_RE) -- THIS regex is now the source of truth; control/commands.py imports it (flipped by ruling 2026-09-02). Greedy by ruling: עצור always stops,
# even mid-sentence; the same intent stays expressible through חכה/המתן.

EMERGENCY_RE = re.compile(
    r"(\b(?:stop|emergency|abort|halt|freeze|mayday|kill|cut"
    r"|עצור|עצרי|עצרו|תעצור|תעצרי|תעצרו"
    r"|סטופ|חירום)\b"
    # owner ruling 2026-09-08: הפסק / תפסיק stop too -- unless they stop a PERCEPTION job ("תפסיק לעקוב" = clear the
    # highlight, not the aircraft); די only as the whole utterance or its last word ("טוס די מהר" is an adverb).
    r"|\b(?:הפסק|הפסיקי|הפסיקו|תפסיק|תפסיקי|תפסיקו)\b(?!\s+ל(?:עקוב|הדגיש|סמן|הראות|צלם|ספור))"
    r"|(?<!\S)(?:די|מספיק)(?:[,!.]?\s+(?:די|מספיק))*(?=\s*[!.?]*\s*$))", re.I)


def emergency(s):
    return bool(EMERGENCY_RE.search(s))


# ================================ stage 1: bypass ================================
# Canonical short commands are answered deterministically: zero model risk, zero latency.
# Runs on the digit-normalized sentence, so the patterns only need to match digits.
# Measured coverage: 79 of the 189 standard commands.

AXIS_BY_VERB = {"עלה": ("z", 1), "תעלה": ("z", 1), "טפס": ("z", 1),
                "רד": ("z", -1), "תרד": ("z", -1)}
AXIS_BY_DIRECTION = {"קדימה": ("x", 1), "אחורה": ("x", -1), "ימינה": ("y", 1),
                     "שמאלה": ("y", -1), "למעלה": ("z", 1), "למטה": ("z", -1)}
WIRE_KEY = {"x": "dx", "y": "dy", "z": "dz"}


def _build_move(m):
    # A neutral verb (טוס) with no direction word is ambiguous: fall through to the model.
    axis = AXIS_BY_VERB.get(m.group(1)) if not m.group(2) else AXIS_BY_DIRECTION.get(m.group(2))
    if axis is None:
        return None
    return [{"type": "fly_by", WIRE_KEY[axis[0]]: axis[1] * float(m.group(3))}]


BYPASS_PATTERNS = [
    (re.compile(r"^(?:בצע\s+)?(?:המראה|תמריא|המרא)(?:\s+עכשיו)?$"),
     lambda m: [{"type": "takeoff"}]),
    (re.compile(r"^(?:בצע\s+)?(?:נחת|תנחת|נחיתה)(?:\s+עכשיו)?$"),
     lambda m: [{"type": "land"}]),
    (re.compile(r"^(הסתובב|תסתובב|פנה)\s+(\d+(?:\.\d+)?)\s+מעלות\s+(עם|נגד)\s+כיוון\s+השעון$"),
     lambda m: [{"type": "spin_by", "degrees": (1 if m.group(3) == "עם" else -1) * float(m.group(2))}]),
    (re.compile(r"^(?:פנה|תפנה)\s+(ימינה|שמאלה)\s+(\d+(?:\.\d+)?)\s+מעלות$"),
     lambda m: [{"type": "spin_by", "degrees": (1 if m.group(1) == "ימינה" else -1) * float(m.group(2))}]),
    (re.compile(r"^(טוס|תטוס|זוז|תזוז|התקדם|תתקדם|סע|עלה|תעלה|רד|תרד|טפס)\s+"
                r"(?:(קדימה|אחורה|ימינה|שמאלה|למעלה|למטה)\s+)?(\d+(?:\.\d+)?)\s+(?:מטרים|מטר)$"),
     _build_move),
    (re.compile(r"^(?:חכה|תחכה|המתן|תמתין)\s+(\d+(?:\.\d+)?)\s+שניות$"),
     lambda m: [{"type": "delay", "seconds": float(m.group(1))}]),
    (re.compile(r"^עשה\s+סיבוב\s+שלם(?:\s+(עם|נגד)\s+כיוון\s+השעון)?$"),
     lambda m: [{"type": "spin_by", "degrees": (-360.0 if m.group(1) == "נגד" else 360.0)}]),
]


def bypass(s):
    """Wire-schema mission for a full-match sentence, else None."""
    s = hebnum_to_digits(s).strip().rstrip(".!")
    for pattern, build in BYPASS_PATTERNS:
        m = pattern.match(s)
        if m:
            mission = build(m)
            if mission is not None:
                return mission
    return None


HE = "֐-׿"                       # the Hebrew Unicode block: ONE home for the range


def he_word(core, prefixes=""):
    """Canonical Hebrew word boundary: clitic prefixes break \\b, so the boundary is a
    non-Hebrew lookaround on both sides. Hand-rolled (?<![HE])...(?![HE]) patterns in the
    rule tables must stay in sync with this shape."""
    return rf"(?<![{HE}]){prefixes}{core}(?![{HE}])"


# ============================ stage 2: Hebrew rewrites ============================
# Everything here exists because a measured failure demanded it. Order matters:
# digits first (the other rules then only handle digits), inline words, verb insertion,
# then the glossary rules.

# 2a. Number words -> digits. Digits survived every measured run; number words did not
# (עשרים became "ten"). חצי is deliberately excluded: "חצי סיבוב" must stay words.
NUM_UNITS = {"אחד": 1, "אחת": 1, "שניים": 2, "שתיים": 2, "שני": 2, "שתי": 2,
             "שלושה": 3, "שלוש": 3, "ארבעה": 4, "ארבע": 4, "חמישה": 5, "חמש": 5,
             "שישה": 6, "שש": 6, "שבעה": 7, "שבע": 7, "שמונה": 8, "תשעה": 9, "תשע": 9}
NUM_TENS = {"עשרים": 20, "שלושים": 30, "ארבעים": 40, "חמישים": 50,
            "שישים": 60, "שבעים": 70, "שמונים": 80, "תשעים": 90}
NUM_WORDS = set(NUM_UNITS) | set(NUM_TENS) | {"עשרה", "עשר", "מאה", "מאתיים", "מאות"}


def hebnum_to_digits(s):
    """Compose adjacent Hebrew number words into one value: עשרים וחמישה -> 25,
    מאה עשרים -> 120, חמישה עשר -> 15. A word with the definite article (השני, ordinal
    usage) is never converted."""
    toks = s.split(" ")
    out = []
    i = 0
    while i < len(toks):
        word = toks[i]
        core = word[1:] if word.startswith("ו") else word
        if core not in NUM_WORDS or word.startswith("ה"):
            out.append(word)
            i += 1
            continue
        total, unit, j, consumed = 0, 0, i, 0
        while j < len(toks):
            tok = toks[j]
            c = tok[1:] if tok.startswith("ו") and consumed else tok
            if c in NUM_UNITS:
                unit = NUM_UNITS[c]
            elif c in ("עשרה", "עשר") and unit:
                unit += 10                      # teens: חמישה עשר = 15
            elif c in ("עשרה", "עשר"):
                unit = 10
            elif c in NUM_TENS:
                total += NUM_TENS[c] + unit
                unit = 0
            elif c == "מאה":
                total += 100
            elif c == "מאתיים":
                total += 200
            elif c == "מאות" and unit:
                total += unit * 100             # שלוש מאות = 300
                unit = 0
            else:
                break
            consumed += 1
            j += 1
        total += unit
        if consumed and total > 0:
            out.append(str(total))
            i = j
        else:
            out.append(word)
            i += 1
    return " ".join(out)


# 2b. Measured trouble words are written as English inline: DictaLM copies Latin tokens
# through verbatim (probed 2026-09-02), so no reverse mapping is needed. An entry requires
# at least two measured mistranslations.
INLINE_WORDS = [("כתומה", "orange"), ("כתום", "orange"), ("גדר", "fence"), ("אפוד", "vest")]


def inline_english(s):
    for he, en in INLINE_WORDS:
        s = re.sub(he_word(f"ה{he}"), f"ה-{en}", s)
        s = re.sub(he_word(f"{he}", "(ב|ל|מ)?"), lambda m: (m.group(1) or "") + en, s)
    return s


# 2c. A direction with no verb after a connective merges into the previous rotation when
# translated ("then right two meters" -> "turn right two meters"). Inserting זוז at the
# source prevents the merge.
BARE_DIRECTION_RE = re.compile(
    r"(ואז|ואחר כך|אחרי זה|לאחר מכן|,)\s+(ימינה|שמאלה|קדימה|אחורה|למעלה|למטה)\s+(?=\d)")


def add_missing_verb(s):
    return BARE_DIRECTION_RE.sub(lambda m: f"{m.group(1)} זוז {m.group(2)} ", s)


# 2c'. A bare מטר (no number on either side) is written out as מטר אחד before translation:
# Hy-MT2 rendered "רד מטר" as "six meters" twice (live 2026-09-08, lines 11 and 61; the guard
# caught both). The neighbour test is the guard's own bare-unit rule. Runs AFTER hebnum-digits,
# so "חמישה עשר מטר" is already "15 מטר" and untouched; "מטר וחצי" and "מטר אחד" are untouched.
def _number_token(t):
    core = t.rstrip(".,!?;:").lstrip("ו")
    return (bool(re.fullmatch(r"\d+(?:\.\d+)?", core)) or core in NUM_WORDS
            or core in CONSTRUCT_NUM or core.lstrip("שבלמכה") == "חצי")


def explicit_one_meter(s):
    toks = s.split()
    out = []
    for i, tok in enumerate(toks):
        if tok.rstrip(".,!?;:") == "מטר":
            prev = toks[i - 1] if i else ""
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            if not _number_token(prev) and not _number_token(nxt) and nxt.rstrip(".,!?") != "וחצי":
                out.append(tok.replace("מטר", "מטר אחד", 1))
                continue
        out.append(tok)
    return " ".join(out)


# 2d. Glossary rules: acronym expansion, radio-procedure words, homographs, slang.
# owner ruling 2026-09-08 ("hardwire them"): possibility / let's / absolute-altitude register -> imperative BEFORE the
# translator, so Hy-MT2's "It is possible to take off" never reaches the planner. Questions (? / האם) are left alone.
_INF2IMP = {"להמריא": "תמריא", "לנחות": "תנחת", "לטוס": "טוס", "לעלות": "עלה", "לרדת": "רד", "להסתובב": "הסתובב",
            "לזוז": "זוז", "לפנות": "פנה", "להתקדם": "התקדם", "לחזור": "חזור", "להתרומם": "התרומם", "לטפס": "טפס"}
HE_POSSIBLE_RE = re.compile(r"(?<!\S)(?:אפשר|יש אפשרות)\s+(ל\S+)")
HE_LETS_RE = re.compile(r"(?<!\S)בוא(?:י|ו)?\s+נ(\S+)")
HE_TO_ALT_RE = re.compile(r"(?<!\S)(עלה|תעלה|טפס|תטפס|התרומם|תתרומם|רד|תרד)\s+לגובה\s+(?:של\s+)?(?=(?:\S+\s+){1,4}מטר)")


def register_imperative(s):
    if s.rstrip().endswith("?") or s.lstrip().startswith("האם"):
        return s
    s = HE_POSSIBLE_RE.sub(lambda m: _INF2IMP.get(m.group(1), m.group(0)), s)   # אפשר להמריא -> תמריא (unknown verb: untouched)
    s = HE_LETS_RE.sub(lambda m: "ת" + m.group(1), s)                           # בוא נרד -> תרד ; בוא נמריא -> תמריא
    s = HE_TO_ALT_RE.sub(lambda m: m.group(1) + " ", s)                          # עלה לגובה עשרה מטרים -> עלה עשרה מטרים (dataset: relative)
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
         negatives=["רותם ממשיכה בסריקה", "רות ואני נפגשים"], positives=["רות, ממשיך בסריקה"]),
    Rule("proc-over-final", r",\s*עבור\s*$", "",
         negatives=["תעבור לעמדה הבאה", "זה עבורך", "עצור לפני שתמשיך, עבורי זה חשוב"],
         positives=["ממשיך בסריקה, עבור"]),
    Rule("proc-out-final", r",\s*סוף\s*$", "",
         negatives=["חוזר לנקודת האיסוף", "טוס עד סוף הרחוב"], positives=["שנתתי לך, סוף"]),
    Rule("takeoff-homograph", r"^המראה(?=$|,|!|\s+(?:מיידית|עכשיו|מהירה|דחופה)\b)", "בצע המראה",
         negatives=["המראה שבורה בחדר", "תבדוק את המראה של הרחפן", "המראה של הרחפן מלוכלכת"],
         positives=["המראה מיידית", "המראה", "המראה, יש הקפצה"]),
    Rule("feet-unit", r"(\bמאות?|עשרות|אלף|\d+)\s+רגל\b", r"\1 פיט",
         negatives=["הכלב הרים רגל", "רגל של השולחן שבורה"], positives=["שמונה מאות רגל"]),
    Rule("slang-sector", r"(?<![֐-׿])([וש]?(?:ב|ל|מה|ה))גזרה(?![֐-׿])", r"\1אזור",
         negatives=["גזר במרק", "הגוזרת גזרה", "גזרה עליו הגורל"],
         positives=["סריקה בגזרה הצפונית", "הגזרה שלך", "נכנס לגזרה שלך"]),
    Rule("slang-scramble", r"\bיש הקפצה\b", "יש משימת חירום",
         negatives=[], positives=["המראה מיידית, יש הקפצה"]),
# Rotation sense as inline English: Hy-MT2 (the deployed translator, ruling 2026-09-07) renders
# "עם כיוון השעון" as "counter-clockwise" -- a sign FLIP the guards cannot see. Measured on the
# 2026-09-07 hymt2 run: combo3, combo5, v_finish3_g3 (wrong-degrees -90 vs 90). The inline
# mechanism carries the fix; a leading ו (ועם / ונגד) is kept in front of the Latin token.
    Rule("clockwise-inline", r"(?<![֐-׿])(ו?)עם כיוון השעון(?![֐-׿])", r"\1clockwise",
         negatives=["טוס עם הרוח", "עם כיוון הרוח", "סמן את השעון על הקיר", "כיוון השעון שגוי"],
         positives=["הסתובב 90 מעלות עם כיוון השעון", "ועם כיוון השעון", "תעשה חצי סיבוב עם כיוון השעון"]),
    Rule("counterclockwise-inline", r"(?<![֐-׿])(ו?)נגד כיוון השעון(?![֐-׿])", r"\1counterclockwise",
         negatives=["טוס נגד הרוח", "נגד כיוון הרוח", "הוא נגד השעון החדש"],
         positives=["הסתובב 45 מעלות נגד כיוון השעון", "ונגד כיוון השעון"]),
# Chain-initial takeoff: DictaLM mistranslates the takeoff verb that OPENS a chain
# ("המראה," became "Perform a landing"; verbose chains became "Fly forward"). Measured:
# combo5, r_mis2-class, v_listen3/v_okso4/v_seq5, live combo_tl 2026-09-02. The inline-English
# mechanism carries the fix: DictaLM copies Latin tokens through verbatim.
    Rule("takeoff-verb-inline", r"\b(?:תמריא|המרא)\b", "take off",
         negatives=["ההמראה הייתה חלקה", "המראה, עלה 2 מטרים"],
         positives=["תמריא, עלה 3 מטרים ותישאר שם", "המרא ואז טוס קדימה"]),
# המראה is a homograph (takeoff / the-mirror): fire only as a chain opener (followed by
# a comma or ואז) and never after על/אל/את (looking AT the mirror).
    Rule("takeoff-noun-inline", r"(?<!על )(?<!אל )(?<!את )\bהמראה(?=\s*,|\s+ואז\b)",
         "take off",
         negatives=["תסתכל על המראה, ואז זוז ימינה", "המראה נמצאת שם", "המראה של הבניין יפה"],
         positives=["המראה, עלה 2 מטרים ונחת", "קודם כל המראה, אחרי זה עלה 5 מטרים",
                    "בצע המראה ואז טוס קדימה"]),
]


def apply_he(s):
    """All of stage 2, in order. Returns the rewritten Hebrew and the names of fired rules."""
    fired = []
    for name, fn in (("hebnum-digits", hebnum_to_digits),
                     ("inline-english", inline_english),
                     ("missing-verb", add_missing_verb),
                     ("one-meter", explicit_one_meter), ("register", register_imperative)):
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


# ============================= stage 4: output guards =============================
# The guards verify, they do not trust. Hebrew numbers are read by the SAME composer that
# stage 2 uses (the old ad-hoc summer could not compose hundreds: שלוש מאות read as 3).
# The guard only pre-normalizes vocabulary the digitizer deliberately leaves alone:
# construct-state numerals, חצי, and the bare-מטר rule.

# Construct-state numerals (שלושת האנשים = the three people) -> plain forms for the composer.
CONSTRUCT_NUM = {"שלושת": "שלושה", "ארבעת": "ארבעה", "חמשת": "חמישה", "ששת": "שישה",
                 "שבעת": "שבעה", "שמונת": "שמונה", "תשעת": "תשעה", "עשרת": "עשרה"}
EN_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
          "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
          "hundred": 100, "half": 0.5, "halfway": 0.5}
EN_NUM_REV = {v: k for k, v in EN_NUM.items()}


# חצי of a ROTATION is 180 degrees, not the number 0.5: "חצי סיבוב" read as 0.5 made the guard
# overwrite DictaLM's correct "Turn right 180 degrees" with "0.5 degrees" (live 2026-09-06,
# traces/session-20260906-231146.jsonl utterance 30). Both extractors compose the idiom to 180,
# so a correct "180 degrees" AND a correct "half a turn" both pass the check unpatched.
# Clitic prefixes ride on חצי too (שחצי פתוח = that is half open): live 2026-09-08 rejected that
# sentence three times because the bare pattern missed it. סיבוב וחצי (a turn and a half) is 540.
HE_HALF_TURN_RE = re.compile(r"(?<!\S)(?:[שבלמכה]|ו)?חצי\s+(?:סיבוב|הקפה)(?!\S)")
HE_TURN_HALF_RE = re.compile(r"(?<!\S)סיבוב\s+וחצי(?!\S)")
EN_HALF_TURN_RE = re.compile(r"\b(?:a\s+)?half(?:\s+a|\s+an|-)?\s*(?:turn|rotation|revolution|circle|spin)s?\b", re.I)
EN_TURN_HALF_RE = re.compile(r"\b(?:(?:one|a|1)\s+and\s+a\s+half\s+(?:turn|rotation|revolution|circle)s?"
                             r"|(?:a\s+)?(?:turn|rotation|revolution|circle)\s+and\s+a\s+half"
                             r"|1\.5\s+(?:turn|rotation|revolution|circle)s?)\b", re.I)
# Punctuation glued to a word by the ASR ("חמישה...", "מטר.") hid number words and the bare-metre
# rule (live 2026-09-08: three false rejects). Strip trailing punctuation clusters; decimals survive.
GLUED_PUNCT_RE = re.compile(r"(?<=\S)[.,!?;:\u2026\"'()]+(?=\s|$)")


def _nums_he(s):
    """Every number in a Hebrew sentence, digits and composed number words, sorted.
    A bare singular unit counts as one (מטר = 1, מטר וחצי = 1.5) -- both were measured
    causes of false rejections. Composition is delegated to hebnum_to_digits, so hundreds
    (שלוש מאות = 300) and the article exclusion behave exactly as in stage 2."""
    s = GLUED_PUNCT_RE.sub("", s)                    # "חמישה..." -> "חמישה", "מטר." -> "מטר"
    s = HE_HALF_TURN_RE.sub("180", s)                # חצי סיבוב = 180 degrees, not 0.5
    s = HE_TURN_HALF_RE.sub("540", s)                # סיבוב וחצי = 540 degrees
    s = s.replace("מטר וחצי", "1.5 מטר")
    toks = s.split()

    def is_number(t):
        core = t.lstrip("ו")
        return (bool(re.fullmatch(r"\d+(?:\.\d+)?", t)) or core in NUM_WORDS
                or core in CONSTRUCT_NUM or core.lstrip("שבלמכה") == "חצי")

    bare_meters = 0
    for i, tok in enumerate(toks):
        # Only מטר: the other unit words are homographs (שנייה = a moment, מעלה = upward).
        # Hebrew allows the number on either side (שני מטרים / מטר אחד), so both neighbors
        # must be number-free before מטר counts as a bare one.
        if tok == "מטר":
            prev = toks[i - 1] if i else ""
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            if not is_number(prev) and not is_number(nxt):
                bare_meters += 1

    norm = []
    for t in toks:
        core = t.lstrip("ו")
        if core in CONSTRUCT_NUM:
            norm.append(("ו" if t != core else "") + CONSTRUCT_NUM[core])
        else:
            norm.append(t)
    s = hebnum_to_digits(" ".join(norm))
    s = re.sub(r"(\d+(?:\.\d+)?)\s+וחצי(?!\S)", lambda m: str(float(m.group(1)) + 0.5), s)
    s = re.sub(r"(?<!\S)(?:[שבלמכה]|ו)?חצי(?!\S)", "0.5", s)
    vals = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    return sorted(vals + [1.0] * bare_meters)


def _nums_en(s):
    """Every number in an English sentence; adjacent number words compose (twenty five,
    one hundred twenty, two and a half -- mirroring the Hebrew composer's וחצי)."""
    s = re.sub(r"(\d+(?:\.\d+)?)\s+and\s+a\s+half\b",
               lambda m: str(float(m.group(1)) + 0.5), s)
    s = EN_TURN_HALF_RE.sub("540", s)                # one and a half turns = 540 degrees
    s = EN_HALF_TURN_RE.sub("180", s)                # half a turn = 180 degrees, not 0.5
    vals = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    toks = re.findall(r"[a-zA-Z]+", s.lower())
    i = 0
    while i < len(toks):
        if toks[i] not in EN_NUM:
            i += 1
            continue
        # "the one" is an idiom (the one with the open door), not a count.
        if toks[i] == "one" and i and toks[i - 1] == "the":
            i += 1
            continue
        total = EN_NUM[toks[i]]
        i += 1
        while i < len(toks) and (toks[i] in EN_NUM or toks[i] in ("and", "a")):
            if toks[i] in EN_NUM:
                total = total * 100 if EN_NUM[toks[i]] == 100 else total + EN_NUM[toks[i]]
            i += 1
        vals.append(float(total))
    return sorted(vals)


# ================================ the entry point ================================


# Negation guard (2026-09-10): refuse a PURE action-negation with NO positive order, deterministically,
# BEFORE the Gemma call. Defense-in-depth for the safety-critical negation class. Clause-based; errs toward
# NOT rejecting (zero false fires). Design + evidence: docs/active/2026-09-10-guard-and-config-workplan.md A2.
_NEG_TRIG = re.compile(r"(?:בשום אופן\s+)?(?:אל\s+ת\S+|בלי\s+ל\S+|לא\s+ל\S+)")
_POS_IMP = re.compile(r"(?<![א-ת])ו?(?:תטוס|טוס|תעלה|עלה|תרד|רד|תסתובב|הסתובב|תפנה|פנה|תסע|סע|תזוז|זוז|תמריא|המריא|תנחת|נחת|תעוף|עוף|תחזור|חזור|בוא|תמשיך|המשך|תאט|האט|תאיץ|האץ|תעצור|עצור|שים|סמן|תסמן|עקוב|תעקוב|ספור|תספור|תאר|תתאר|צלם|תצלם|חפש|תחפש|הראה|תראה|מצא|תמצא|שמור|תשמור|זהה|תזהה)(?![א-ת])")
_NUM_UNIT = re.compile(r"(?<![א-ת])(?:מטר|מטרים|מעלות|שניות)(?![א-ת])")
_CLAUSE_SPLIT = re.compile(r"[,.;]|\bואז\b|\bאבל\b|\bורק\b|\bאולם\b")

def negation_only(he):
    """True iff the utterance is a PURE action-negation: at least one negated action clause and NO clause
    carrying a positive order. The negation trigger consumes its own verb, so a positive imperative that
    survives the removal is a separate, real order. A bare number+unit counts as an order only when the
    clause has no negation. Errs toward NOT rejecting (zero false fires)."""
    neg_found = pos_found = False
    for cl in _CLAUSE_SPLIT.split(he or ""):
        cl = cl.strip()
        if not cl:
            continue
        rest = _NEG_TRIG.sub(" ", cl)      # drop the negated verbs; an order verb left behind is genuine
        has_neg = rest != cl
        if _POS_IMP.search(rest):
            pos_found = True
        elif has_neg:
            neg_found = True
        elif _NUM_UNIT.search(rest):
            pos_found = True
    return neg_found and not pos_found

def recognize_direct(he):
    """harden2 (2026-09-08): the Hebrew-only front half. Stage 0 emergency, stage 1 bypass (deterministic
    missions, no model), stage 2 Hebrew rewrites; then ("direct", he2, flags) for the pipeline's single Gemma call.
    The English stages (translation, answer-mode, English rewrites, English routing) do not run."""
    he = he or ""                 # defensive: never crash the stage-0 regex on a None transcript
    if emergency(he):
        return ("emergency", None, [])
    mission = bypass(he)
    if mission is not None:
        return ("mission", mission, [])
    if negation_only(he):
        return ("reject", he, ["neg-guard"])
    he2, flags = apply_he(he)
    return ("direct", he2, flags)


def numbers_vs_mission(he2, mission):
    """The number guard for the direct path: every number spoken in the Hebrew must appear in the mission
    (magnitude). Returns the list of missing numbers ([] = ok)."""
    said = {abs(float(x)) for x in _nums_he(he2)}
    got = set()
    for step in mission or []:
        for k, v in step.items():
            if k != "type" and isinstance(v, (int, float)):
                got.add(abs(float(v)))
    return sorted(x for x in said if x not in got)
