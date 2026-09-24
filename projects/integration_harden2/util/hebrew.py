"""Hebrew text helpers shared by several modules (the recognizer, the screen,
log/score.py)."""

HE = "֐-׿"         # the Hebrew Unicode block, for a regex character class


def is_hebrew(c):
    """True for one character in the Hebrew Unicode block."""
    return "֐" <= c <= "׿"


# 2a. Number words -> digits. Digits survived every measured run; number words did not
# (עשרים became "ten"). חצי is deliberately excluded: "חצי סיבוב" must stay words.
NUM_UNITS = {                    # the masculine and feminine forms of each number
    "אחד": 1, "אחת": 1,
    "שניים": 2, "שתיים": 2, "שני": 2, "שתי": 2,
    "שלושה": 3, "שלוש": 3,
    "ארבעה": 4, "ארבע": 4,
    "חמישה": 5, "חמש": 5,
    "שישה": 6, "שש": 6,
    "שבעה": 7, "שבע": 7,
    "שמונה": 8,
    "תשעה": 9, "תשע": 9,
}
NUM_TENS = {
    "עשרים": 20,
    "שלושים": 30,
    "ארבעים": 40,
    "חמישים": 50,
    "שישים": 60,
    "שבעים": 70,
    "שמונים": 80,
    "תשעים": 90,
}
NUM_WORDS = set(NUM_UNITS) | set(NUM_TENS) | {"עשרה", "עשר", "מאה", "מאתיים", "מאות"}


def hebnum_to_digits(s):
    """Compose adjacent Hebrew number words into one value: עשרים וחמישה -> 25,
    מאה עשרים -> 120, חמישה עשר -> 15. A word with the definite article (השני, ordinal
    usage) is never converted."""
    word = ""
    core = ""
    tok = ""
    c = ""
    total = 0
    unit = 0
    j = 0
    consumed = 0
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

        # compose the run of number words that starts here
        total = 0
        unit = 0
        j = i
        consumed = 0
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
