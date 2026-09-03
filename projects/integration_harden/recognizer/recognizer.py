"""The Recognizer: Hebrew utterance in -> {emergency | mission | routed English | rejection}.

This file is the component. It is pure text processing: it owns no model and starts no server.
The translator (stage 3) is injected into recognize() as a callable, so the file moves into
integration unchanged. bench.py owns the models and the measurements.

File layout follows execution order:
    stage 0  emergency filter     stop words act immediately, before anything else
    stage 1  bypass               full-match sentences become missions with no model call
    stage 2  Hebrew rewrites      make the Hebrew survivable before translation
    stage 3  (external)           the injected translate() callable
    stage 4  output guards        verify the translation against the source
    stage 5  English rewrites     fix known translation defects
    stage 6  routing              command path or perception path
    recognize()                   runs all of it
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
    r"\b(stop|emergency|abort|halt|freeze|mayday|kill|cut"
    r"|עצור|עצרי|עצרו|תעצור|תעצרי|תעצרו"
    r"|סטופ|חירום)\b", re.I)


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
        s = re.sub(rf"(?<![֐-׿])ה{he}(?![֐-׿])", f"ה-{en}", s)
        s = re.sub(rf"(?<![֐-׿])(ב|ל|מ)?{he}(?![֐-׿])", lambda m: (m.group(1) or "") + en, s)
    return s


# 2c. A direction with no verb after a connective merges into the previous rotation when
# translated ("then right two meters" -> "turn right two meters"). Inserting זוז at the
# source prevents the merge.
BARE_DIRECTION_RE = re.compile(
    r"(ואז|ואחר כך|אחרי זה|לאחר מכן|,)\s+(ימינה|שמאלה|קדימה|אחורה|למעלה|למטה)\s+(?=\d)")


def add_missing_verb(s):
    return BARE_DIRECTION_RE.sub(lambda m: f"{m.group(1)} זוז {m.group(2)} ", s)


# 2d. Glossary rules: acronym expansion, radio-procedure words, homographs, slang.
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
                     ("missing-verb", add_missing_verb)):
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
# The guards verify, they do not trust. Number reading uses two tables: the Hebrew one also
# accepts standalone עשר/מאה/חצי that the stage-2 digitizer deliberately leaves alone.

# Construct-state numerals (שלושת האנשים = the three people) join the plain forms.
HEB_NUM = dict(NUM_UNITS, **NUM_TENS,
               **{"עשרה": 10, "עשר": 10, "מאה": 100, "מאתיים": 200, "חצי": 0.5,
                  "שלושת": 3, "ארבעת": 4, "חמשת": 5, "ששת": 6, "שבעת": 7,
                  "שמונת": 8, "תשעת": 9, "עשרת": 10})
EN_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
          "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
          "hundred": 100, "half": 0.5, "halfway": 0.5}
EN_NUM_REV = {v: k for k, v in EN_NUM.items()}


def _nums_he(s):
    """Every number in a Hebrew sentence, digits and composed number words, sorted.
    A bare singular unit counts as one (מטר = 1, מטר וחצי = 1.5) -- both were measured
    causes of false rejections."""
    s = s.replace("מטר וחצי", "1.5 מטר")
    vals = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    toks = s.split()
    for i, tok in enumerate(toks):
        # Only מטר: the other unit words are homographs (שנייה = a moment, מעלה = upward).
        # Hebrew allows the number on either side (שני מטרים / מטר אחד), so both neighbors
        # must be number-free before מטר counts as a bare one.
        if tok == "מטר":
            def is_number(t):
                return bool(re.fullmatch(r"\d+(?:\.\d+)?", t)) or t.lstrip("ו") in HEB_NUM
            prev = toks[i - 1] if i else ""
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            if not is_number(prev) and not is_number(nxt):
                vals.append(1.0)
    heb_toks = re.findall(r"[֐-׿]+", s)
    i = 0
    while i < len(heb_toks):
        if heb_toks[i].lstrip("ו") in HEB_NUM:
            total = 0
            while i < len(heb_toks) and heb_toks[i].lstrip("ו") in HEB_NUM:
                total += HEB_NUM[heb_toks[i].lstrip("ו")]
                i += 1
            vals.append(float(total))
        else:
            i += 1
    return sorted(vals)


def _nums_en(s):
    """Every number in an English sentence; adjacent number words compose (twenty five,
    one hundred twenty)."""
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
        while i < len(toks) and (toks[i] in EN_NUM or toks[i] == "and"):
            if toks[i] in EN_NUM:
                total = total * 100 if EN_NUM[toks[i]] == 100 else total + EN_NUM[toks[i]]
            i += 1
        vals.append(float(total))
    return sorted(vals)


def check_numbers(he, en):
    """True when the translation carries exactly the source's numbers, order ignored."""
    return _nums_he(he) == _nums_en(en)


def patch_number(en, wrong, right):
    """Deterministic last resort: replace the one English number token whose value is wrong.
    Returns the patched sentence, or None when the token cannot be found."""
    digits = str(int(right)) if right == int(right) else str(right)
    if wrong == int(wrong) and re.search(rf"\b{int(wrong)}\b", en):
        return re.sub(rf"\b{int(wrong)}\b", digits, en, count=1)
    word = EN_NUM_REV.get(wrong)
    if word and re.search(rf"\b{word}\b", en, re.I):
        return re.sub(rf"\b{word}\b", digits, en, count=1, flags=re.I)
    return None


COLORS = {"אדום": "red", "אדומה": "red", "כחול": "blue", "כחולה": "blue",
          "לבן": "white", "לבנה": "white", "שחור": "black", "שחורה": "black",
          "צהוב": "yellow", "צהובה": "yellow", "ירוק": "green", "ירוקה": "green",
          "כתום": "orange", "כתומה": "orange", "אפור": "gray", "אפורה": "gray",
          "חום": "brown", "חומה": "brown", "כסוף": "silver", "כסופה": "silver",
          "ורוד": "pink", "ורודה": "pink"}


def check_colors(he, en):
    """Colors named in the Hebrew but absent from the translation (the כתום->red class)."""
    en_l = en.lower()
    missing = []
    for h, e in COLORS.items():
        present = re.search(rf"(?<![֐-׿])[ובלשכמה]{{0,2}}{h}(?![֐-׿])", he)
        if present and e not in en_l and (e != "gray" or "grey" not in en_l):
            missing.append((h, e))
    return missing


# ============================ stage 5: English rewrites ============================

EN_RULES = [
    Rule("turn-meters",
         r"(?i)\bturn(?:ed|ing)?\s+(left|right)\s+((?:\d+(?:\.\d+)?|one|two|three|four|five"
         r"|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty)\s+meters?)\b",
         r"move \1 \2",
         negatives=["turn right 45 degrees", "turn left at the corner", "turn right and fly 3 meters"],
         positives=["then turn left three meters", "turn right 2 meters", "Turn right nine meters"]),
# The planner turns a duration-less closing "stay there / remain stationary" into a
# {"delay": 1} step (measured: r_mis2; live E2E 2026-09-02 planner shots). Hovering is the
# drone's default; strip the clause. A duration ("stay there for 5 seconds") never matches:
# the pattern is end-anchored right after the verb phrase.
    Rule("stay-there-strip",
         r"(?i)(?:,|;)?\s*\b(?:and|then)\s+(?:remain|stay|stop)\s+(?:stationary|still|there|put|in\s+place)\s*\.?\s*$",
         "",
         negatives=["go up 3 meters and stay there for 5 seconds",
                    "climb 2 meters and wait 3 seconds", "stay there"],
         positives=["Take off, go up 3 meters and stay there",
                    "climb 2 meters, then remain stationary.",
                    "fly forward and stop in place"]),
]


def apply_en(s):
    fired = []
    for rule in EN_RULES:
        t = rule.apply(s)
        if t != s:
            fired.append(rule.name)
            s = t
    return s, fired


# ================================ stage 6: routing ================================
# The Recognizer decides where its output goes (ruling 2026-09-02). Deterministic, on the
# Hebrew. A movement verb wins over a perception clause: dual-intent sentences execute the
# motion; multi-intent handling is a future item. Measured offline: 100/100 perception,
# 240/243 commands (the 3 are see-questions, correctly sent to the VLM).

PERCEPTION_RE = re.compile(
    r"(?<![֐-׿])(סמן|תסמן|הדגש|תדגיש|עקוב|תעקוב|ספור|תספור|התמקד|תתמקד|תאר|הסתכל|תסתכל"
    r"|צלם|תצלם|זהה|תזהה|חפש|תחפש)(?![֐-׿])"
    r"|מה (אתה רואה|נמצא|יש)|כמה [֐-׿]+ (יש|אתה רואה|מחכים|עומדים)|האם יש"
    r"|(?<![֐-׿])(מצא|תמצא)(?![֐-׿])|זום|התקרב ל")
MOVEMENT_RE = re.compile(
    r"(?<![֐-׿])(טוס|תטוס|עלה|תעלה|רד|תרד|פנה|תפנה|הסתובב|תסתובב|זוז|תזוז|התקדם|תתקדם"
    r"|סע|טפס|תמריא|המרא|נחת|תנחת|חכה|תחכה|המתן|תמתין|עצור)(?![֐-׿])")


def route(he):
    """'command' or 'perception'."""
    if MOVEMENT_RE.search(he):
        return "command"
    return "perception" if PERCEPTION_RE.search(he) else "command"


# ================================ the entry point ================================

def recognize(he, translate):
    """Run the full Recognizer on one Hebrew utterance.

    translate(text, required_numbers=None) -> English string; one model call, injected by
    the caller. On the number-guard retry the required numbers are passed in, so the caller
    can name them to the model.

    Returns (kind, payload, flags):
        ("emergency", None,  [])      stage 0 fired; act immediately
        ("mission",   steps, [])      bypass answered; no model ran
        ("english",   text,  flags)   translated; flags carry route:command / route:perception
        ("reject",    text,  flags)   numbers unrecoverable; read the text back to the user
    """
    if emergency(he):
        return ("emergency", None, [])

    mission = bypass(he)
    if mission is not None:
        return ("mission", mission, [])

    he2, flags = apply_he(he)
    flags.append(f"route:{route(he)}")

    text = translate(he2, required_numbers=None)
    if not check_numbers(he2, text):
        flags.append("number-flag")
        retry = translate(he2, required_numbers=_nums_he(he2))
        if check_numbers(he2, retry):
            text = retry
        else:
            he_nums, en_nums = _nums_he(he2), _nums_en(text)
            extra = [x for x in en_nums if x not in he_nums]
            missing = [x for x in he_nums if x not in en_nums]
            patched = (patch_number(text, extra[0], missing[0])
                       if len(extra) == 1 and len(missing) == 1 else None)
            if patched and check_numbers(he2, patched):
                text = patched
                flags.append("number-patched")
            else:
                return ("reject", text, flags + ["REJECT-number"])

    text, en_fired = apply_en(text)
    return ("english", text.strip(), flags + en_fired)


# ==================================== selftest ====================================

def selftest():
    """Every rule against its own evidence, plus the helpers. Returns a list of problems."""
    bad = []
    for rule in HE_RULES + EN_RULES:
        for n in rule.negatives:
            if rule.apply(n) != n:
                bad.append(f"{rule.name} FALSE-FIRES on {n!r} -> {rule.apply(n)!r}")
        for p in rule.positives:
            if rule.apply(p) == p:
                bad.append(f"{rule.name} MISSES its positive {p!r}")

    assert check_numbers("עלה עשרים מטרים", "Climb twenty meters")
    assert not check_numbers("עלה עשרים מטרים", "Climb ten meters")
    assert check_numbers("עלה 12 מטרים ואז רד שניים", "Climb 12 meters then descend two meters")
    assert not check_numbers("טוס אחורה עשרים מטרים", "Fly back 60 meters")
    assert check_colors("עקוב אחרי הכובע הכתום", "Follow the red hat") == [("כתום", "orange")]
    assert check_colors("המכונית הלבנה", "the white car") == []
    assert patch_number("Climb ten meters, then turn 45 degrees", 10, 20) == \
        "Climb 20 meters, then turn 45 degrees"
    assert patch_number("Fly back 60 meters", 60, 20) == "Fly back 20 meters"

    for he, want in (("עלה עשרים מטרים", "עלה 20 מטרים"),
                     ("טוס אחורה עשרים וחמישה מטרים", "טוס אחורה 25 מטרים"),
                     ("הסתובב מאה עשרים מעלות", "הסתובב 120 מעלות"),
                     ("הסתובב מאתיים שבעים מעלות", "הסתובב 270 מעלות"),
                     ("עלה חמישה עשר מטרים", "עלה 15 מטרים"),
                     ("רד שני מטרים", "רד 2 מטרים"),
                     ("החלון השני משמאל", "החלון השני משמאל"),
                     ("עשה סיבוב שלם", "עשה סיבוב שלם")):
        got = hebnum_to_digits(he)
        if got != want:
            bad.append(f"hebnum: {he!r} -> {got!r}, want {want!r}")

    if inline_english("סמן את הכובע הכתום") != "סמן את הכובע ה-orange":
        bad.append("inline he-prefix")
    if inline_english("עקוב אחרי גדר הבטחון") != "עקוב אחרי fence הבטחון":
        bad.append("inline bare")
    if add_missing_verb(hebnum_to_digits("פנה ימינה ואז ימינה שני מטרים")) != \
            "פנה ימינה ואז זוז ימינה 2 מטרים":
        bad.append("missing-verb")
    if add_missing_verb("ואז פנה ימינה 45 מעלות") != "ואז פנה ימינה 45 מעלות":
        bad.append("missing-verb false-fire")

    assert bypass("עלה עשרה מטרים") == [{"type": "fly_by", "dz": 10.0}]
    assert bypass("הסתובב תשעים מעלות עם כיוון השעון") == [{"type": "spin_by", "degrees": 90.0}]
    assert bypass("פנה שמאלה 30 מעלות") == [{"type": "spin_by", "degrees": -30.0}]
    assert bypass("נחת עכשיו") == [{"type": "land"}]
    assert bypass("טוס 5 מטרים") is None
    assert bypass("תקשיב, עלה 5 מטרים ואז רד") is None

    assert emergency("עצור") and not emergency("עלה עשרה מטרים")
    assert route("עלה עשרה מטרים בבקשה") == "command"
    assert route("סמן את המכונית הלבנה") == "perception"
    assert route("טוס ימינה ותגיד לי מה אתה רואה") == "command"    # movement wins
    return bad


def main():
    problems = selftest()
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print(f"recognizer self-test CLEAN: {len(HE_RULES)} Hebrew rules, {len(EN_RULES)} English "
          f"rule, bypass, guards, and routing all verified")


if __name__ == "__main__":
    main()
