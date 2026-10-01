"""Hebrew text helpers shared by several modules (the recognizer, the screen)."""

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

# The seven front letters (owner Q8, 2026-09-27: "ALL SEVEN! THIS WONT ARISE JUST WITH
# VAV!"). One of them glued to a number word: בחמישה = by five, כעשר = about ten.
FRONT_LETTERS = {
    "ו": "and",
    "ה": "the",
    "ב": "in",
    "ל": "to",
    "מ": "from",
    "כ": "about",
    "ש": "that",
}
# Before one of these, ה + a number is a count (השלושה מטרים = the three metres);
# anywhere else it is an ordinal (הבית השני = the second house) and stays a word.
UNIT_WORDS = {"מטר", "מטרים", "מעלות", "שניות", "שנייה", "דקות", "סיבובים"}

# Fractions (owner C.3: "What about 'ורבע'? What about 'ושמינית'?"). A fraction after a
# number adds to it (שתיים ורבע = 2.25); alone it is its value (רבע מטר = 0.25); of a
# turn it is degrees (רבע סיבוב = 90). The plural forms count: שלושת רבעי = 3/4.
FRACTIONS = {
    "חצי": 0.5,
    "רבע": 0.25,
    "שליש": 1 / 3,
    "שמינית": 0.125,
}
FRACTION_PLURALS = {
    "חצאי": 0.5,
    "רבעי": 0.25,
    "רבעים": 0.25,
    "שלישי": 1 / 3,
    "שלישים": 1 / 3,
    "שמיניות": 0.125,
}


def split_front(word):
    """A number word with one front letter -> (letter, number word). Anything else ->
    ("", word): a word that is a number word by itself keeps its first letter (שמונה,
    שני)."""
    if word in NUM_WORDS:
        return "", word
    if word[:1] in FRONT_LETTERS and word[1:] in NUM_WORDS:
        return word[0], word[1:]
    return "", word


def hebnum_to_digits(s, front_letters=False):
    """Compose adjacent Hebrew number words into one value: עשרים וחמישה -> 25,
    מאה עשרים -> 120, חמישה עשר -> 15. An ordinal (השני) is never converted.
    front_letters=True (the number guard) also converts a number word with a front
    letter, joined by a hyphen as written Hebrew does: בחמישה -> ב-5; with ה only before
    a unit (השלושה מטרים). Stage 2 leaves those words to Gemma: it read all 23 of them
    right (2026-09-28), and the digit form made it fuse two steps into one."""
    word = ""
    front = ""
    first = ""
    after = ""
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
        front = ""
        first = word
        if front_letters:
            front, first = split_front(word)
        after = toks[i + 1] if i + 1 < len(toks) else ""
        if first not in NUM_WORDS or (front == "ה" and after not in UNIT_WORDS):
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
            if not consumed:
                c = first
            if c in NUM_UNITS and unit:
                break                           # אחד וחמישה: two numbers, not one
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
            out.append(front + "-" * bool(front) + str(total))
            i = j
        else:
            out.append(word)
            i += 1
    return " ".join(out)
