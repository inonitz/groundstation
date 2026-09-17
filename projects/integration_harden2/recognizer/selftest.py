"""Recognizer component self-test -- moved out of recognizer.py 2026-09-17 (test code, not production).
Runs every rewrite rule + helper against its own evidence; returns the list of problems ([] = clean).
Run via pytest (test_recognizer) or `python3 -m recognizer.selftest`."""
from .recognizer import (HE_RULES, emergency, bypass, hebnum_to_digits, inline_english,
                         add_missing_verb, explicit_one_meter, _nums_he, _nums_en)


def selftest():
    """Every rule against its own evidence, plus the helpers. Returns a list of problems."""
    bad = []
    for rule in HE_RULES:
        for n in rule.negatives:
            if rule.apply(n) != n:
                bad.append(f"{rule.name} FALSE-FIRES on {n!r} -> {rule.apply(n)!r}")
        for p in rule.positives:
            if rule.apply(p) == p:
                bad.append(f"{rule.name} MISSES its positive {p!r}")


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

    for s_in, want in (("סמן את הכובע הכתום", "סמן את הכובע ה-orange"),      # he-prefix
                       ("עקוב אחרי גדר הבטחון", "עקוב אחרי fence הבטחון"),     # bare
                       ("הכתומים רצים לשם", "הכתומים רצים לשם"),               # negative: plural
                       ("תתקרב לגדרות", "תתקרב לגדרות")):                      # negative: suffix
        if inline_english(s_in) != want:
            bad.append(f"inline_english: {s_in!r} -> {inline_english(s_in)!r}, want {want!r}")


    assert _nums_he("שלוש מאות מטר קדימה") == [300.0]      # the old summer read this as [1, 3]
    # חצי of a rotation is 180 (the live 0.5-degree bug); חצי of a meter stays 0.5.
    assert _nums_he("חצי סיבוב") == [180.0]
    assert _nums_he("תעשה חצי סיבוב עם כיוון השעון") == [180.0]
    assert _nums_he("תסתובב חצי הקפה") == [180.0]
    assert _nums_he("עלה חצי מטר") == [0.5]
    assert _nums_he("מטר וחצי למעלה") == [1.5]
    assert _nums_he("טוס קדימה חצי") == [0.5]
    assert _nums_en("do a half turn clockwise") == [180.0]
    assert _nums_en("make a half-turn") == [180.0]
    assert _nums_en("turn right 180 degrees") == [180.0]
    assert _nums_en("climb half a meter") == [0.5]
    assert _nums_en("go halfway up") == [0.5]
    assert _nums_he("טוס 20 וחצי מעלות") == [20.5]
    # a turn and a half is 540 (live 2026-09-08: 180 flew for סיבוב וחצי; both sides read 0.5)
    assert _nums_he("עשה סיבוב וחצי עם כיוון השעון") == [540.0]
    assert _nums_en("do one and a half turns clockwise") == [540.0]
    assert _nums_en("a turn and a half") == [540.0]
    assert _nums_en("make a half clockwise turn") == [0.5]
    # ASR glues punctuation to words; the ש clitic rides on חצי (live 2026-09-08: three false rejects)
    assert _nums_he("עלה חמישה... לא, עלה שלושה מטרים.") == [3.0, 5.0]
    assert _nums_he("תמתין חמש שניות ואז רד מטר.") == [1.0, 5.0]
    assert _nums_he("זה שחצי פתוח") == [0.5]
    assert _nums_he("עלה 1.5 מטרים") == [1.5]
    assert _nums_he("חמשת המטרים") == [5.0]
    assert _nums_en("two and a half meters") == [2.5]
    assert _nums_en("turn 20 and a half degrees") == [20.5]

    for he_s, want in (("המראה", [{"type": "takeoff"}]),                     # bypass positives
                       ("בצע המראה עכשיו", [{"type": "takeoff"}]),
                       ("נחת", [{"type": "land"}]),
                       ("עלה 10 מטרים", [{"type": "fly_by", "dz": 10.0}]),
                       ("רד 3 מטרים", [{"type": "fly_by", "dz": -3.0}]),
                       ("טוס קדימה 5 מטרים", [{"type": "fly_by", "dx": 5.0}]),
                       ("טוס 5 מטרים", None),                               # neutral verb, no direction
                       ("עלה קצת", None),                                   # no number
                       ("מה אתה רואה", None),                               # question
                       ("טוס אחורה 2 מטרים ואז שמאלה 3 מטרים", None)):      # chains go to the model
        got = bypass(hebnum_to_digits(he_s))
        if got != want:
            bad.append(f"bypass: {he_s!r} -> {got!r}, want {want!r}")

    for s_in, want in (("ואז ימינה 3 מטרים", "ואז זוז ימינה 3 מטרים"),      # bare direction gets a verb
                       ("ואז פנה ימינה 45 מעלות", "ואז פנה ימינה 45 מעלות")):  # negative: verb present
        if add_missing_verb(s_in) != want:
            bad.append(f"add_missing_verb: {s_in!r} -> {add_missing_verb(s_in)!r}, want {want!r}")
    if add_missing_verb(hebnum_to_digits("פנה ימינה ואז ימינה שני מטרים")) != \
            "פנה ימינה ואז זוז ימינה 2 מטרים":
        bad.append("missing-verb")
    if add_missing_verb("ואז פנה ימינה 45 מעלות") != "ואז פנה ימינה 45 מעלות":
        bad.append("missing-verb false-fire")
    for s_in, want in (("רד מטר", "רד מטר אחד"),                                   # positives
                       ("לאט לאט תרד מטר.", "לאט לאט תרד מטר אחד."),
                       ("תמתין חמש שניות ואז רד מטר", "תמתין חמש שניות ואז רד מטר אחד"),
                       ("תעלה 15 מטר", "תעלה 15 מטר"),                              # negatives
                       ("תעלה חמישה עשר מטר", "תעלה חמישה עשר מטר"),
                       ("טוס ימינה מטר וחצי", "טוס ימינה מטר וחצי"),
                       ("זוז אחורה מטר אחד", "זוז אחורה מטר אחד"),
                       ("רד שני מטרים", "רד שני מטרים"),
                       ("המטר האחרון", "המטר האחרון")):
        if explicit_one_meter(s_in) != want:
            bad.append(f"one-meter: {s_in!r} -> {explicit_one_meter(s_in)!r}, want {want!r}")

    assert bypass("עלה עשרה מטרים") == [{"type": "fly_by", "dz": 10.0}]
    assert bypass("הסתובב תשעים מעלות עם כיוון השעון") == [{"type": "spin_by", "degrees": 90.0}]
    assert bypass("פנה שמאלה 30 מעלות") == [{"type": "spin_by", "degrees": -30.0}]
    assert bypass("נחת עכשיו") == [{"type": "land"}]
    assert bypass("טוס 5 מטרים") is None
    assert bypass("תקשיב, עלה 5 מטרים ואז רד") is None


    assert emergency("עצור") and not emergency("עלה עשרה מטרים")
    return bad


def main():
    problems = selftest()
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print(f"recognizer self-test CLEAN: {len(HE_RULES)} Hebrew rules, bypass, and guards verified")


if __name__ == "__main__":
    main()
