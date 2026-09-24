"""Tests for recognizer/: the parser (fast path, bypass, rewrites, numbers, guards) and
the Recognizer's routing. No model server is started: PlannerStub answers the plan."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import recognizer as R
from recognizer import Recognizer, reject_why, recognize_direct
from recognizer.fast_path import critical
from recognizer.guards import negation_only
from recognizer.lexicon import find_nouns, fix_target
from recognizer.rewrites import register_imperative
from control.flight import Control
from dji_app.client import DjiApp
from perception2.vision import TASK_FULL, TASK_OK
from support import PLAN_FAILED, PlannerStub, RecordingPhone, dead_port, no_plan


# ==================== recognizer: the rules and helpers against their evidence =========
# (moved here from recognizer/selftest.py 2026-09-24: test code lives in test files)
from recognizer.bypass import bypass  # noqa: E402
from recognizer.fast_path import emergency  # noqa: E402
from recognizer.numbers import nums_en, nums_he  # noqa: E402
from recognizer.rewrites import (  # noqa: E402
    HE_RULES,
    add_missing_verb,
    explicit_one_meter,
    inline_english,
)
from util.hebrew import hebnum_to_digits  # noqa: E402


def test_every_rule_against_its_own_evidence():
    """Each rewrite rule: every negative untouched, every positive changed."""
    for rule in HE_RULES:
        for n in rule.negatives:
            assert rule.apply(n) == n, f"{rule.name} FALSE-FIRES on {n!r}"
        for p in rule.positives:
            assert rule.apply(p) != p, f"{rule.name} MISSES its positive {p!r}"


def test_hebrew_numbers_become_digits():
    for he, want in (
        ("עלה עשרים מטרים", "עלה 20 מטרים"),
        ("טוס אחורה עשרים וחמישה מטרים", "טוס אחורה 25 מטרים"),
        ("הסתובב מאה עשרים מעלות", "הסתובב 120 מעלות"),
        ("הסתובב מאתיים שבעים מעלות", "הסתובב 270 מעלות"),
        ("עלה חמישה עשר מטרים", "עלה 15 מטרים"),
        ("רד שני מטרים", "רד 2 מטרים"),
        ("החלון השני משמאל", "החלון השני משמאל"),
        ("עשה סיבוב שלם", "עשה סיבוב שלם"),
    ):
        assert hebnum_to_digits(he) == want, he


def test_inline_english_words():
    for s_in, want in (
        ("סמן את הכובע הכתום", "סמן את הכובע ה-orange"),     # he-prefix
        ("עקוב אחרי גדר הבטחון", "עקוב אחרי fence הבטחון"),  # bare
        ("הכתומים רצים לשם", "הכתומים רצים לשם"),            # negative: plural
        ("תתקרב לגדרות", "תתקרב לגדרות"),                    # negative: suffix
    ):
        assert inline_english(s_in) == want, s_in


def test_number_guard_reads_hebrew_numbers():
    # the old summer read this as [1, 3]
    assert nums_he("שלוש מאות מטר קדימה") == [300.0]
    # חצי of a rotation is 180 (the live 0.5-degree bug); חצי of a meter stays 0.5.
    assert nums_he("חצי סיבוב") == [180.0]
    assert nums_he("תעשה חצי סיבוב עם כיוון השעון") == [180.0]
    assert nums_he("תסתובב חצי הקפה") == [180.0]
    assert nums_he("עלה חצי מטר") == [0.5]
    assert nums_he("מטר וחצי למעלה") == [1.5]
    assert nums_he("טוס קדימה חצי") == [0.5]
    assert nums_he("טוס 20 וחצי מעלות") == [20.5]
    # a turn and a half is 540
    # (live 2026-09-08: 180 flew for סיבוב וחצי; both sides read 0.5)
    assert nums_he("עשה סיבוב וחצי עם כיוון השעון") == [540.0]
    # ASR glues punctuation to words; the ש clitic rides on חצי
    # (live 2026-09-08: three false rejects)
    assert nums_he("עלה חמישה... לא, עלה שלושה מטרים.") == [3.0, 5.0]
    assert nums_he("תמתין חמש שניות ואז רד מטר.") == [1.0, 5.0]
    assert nums_he("זה שחצי פתוח") == [0.5]
    assert nums_he("עלה 1.5 מטרים") == [1.5]
    assert nums_he("חמשת המטרים") == [5.0]


def test_number_guard_reads_english_numbers():
    assert nums_en("do a half turn clockwise") == [180.0]
    assert nums_en("make a half-turn") == [180.0]
    assert nums_en("turn right 180 degrees") == [180.0]
    assert nums_en("climb half a meter") == [0.5]
    assert nums_en("go halfway up") == [0.5]
    assert nums_en("do one and a half turns clockwise") == [540.0]
    assert nums_en("a turn and a half") == [540.0]
    assert nums_en("make a half clockwise turn") == [0.5]
    assert nums_en("two and a half meters") == [2.5]
    assert nums_en("turn 20 and a half degrees") == [20.5]


def test_bypass_answers_only_full_matches():
    for he_s, want in (
        ("המראה", [{"type": "takeoff"}]),
        ("בצע המראה עכשיו", [{"type": "takeoff"}]),
        ("נחת", [{"type": "land"}]),
        ("עלה 10 מטרים", [{"type": "fly_by", "dz": 10.0}]),
        ("רד 3 מטרים", [{"type": "fly_by", "dz": -3.0}]),
        ("טוס קדימה 5 מטרים", [{"type": "fly_by", "dx": 5.0}]),
        ("טוס 5 מטרים", None),                          # neutral verb, no direction
        ("עלה קצת", None),                              # no number
        ("מה אתה רואה", None),                          # question
        ("טוס אחורה 2 מטרים ואז שמאלה 3 מטרים", None),  # chains go to the model
    ):
        assert bypass(hebnum_to_digits(he_s)) == want, he_s

    assert bypass("עלה עשרה מטרים") == [{"type": "fly_by", "dz": 10.0}]
    assert bypass("הסתובב תשעים מעלות עם כיוון השעון") == [
        {"type": "spin_by", "degrees": 90.0}
    ]
    assert bypass("פנה שמאלה 30 מעלות") == [{"type": "spin_by", "degrees": -30.0}]
    assert bypass("נחת עכשיו") == [{"type": "land"}]
    assert bypass("טוס 5 מטרים") is None
    assert bypass("תקשיב, עלה 5 מטרים ואז רד") is None


def test_missing_verb_is_added_to_a_bare_direction():
    for s_in, want in (
        ("ואז ימינה 3 מטרים", "ואז זוז ימינה 3 מטרים"),          # a bare direction
        ("ואז פנה ימינה 45 מעלות", "ואז פנה ימינה 45 מעלות"),    # negative: verb present
    ):
        assert add_missing_verb(s_in) == want, s_in

    chained = add_missing_verb(hebnum_to_digits("פנה ימינה ואז ימינה שני מטרים"))
    assert chained == "פנה ימינה ואז זוז ימינה 2 מטרים"
    assert add_missing_verb("ואז פנה ימינה 45 מעלות") == "ואז פנה ימינה 45 מעלות"


def test_a_bare_meter_becomes_one_meter_evidence():
    for s_in, want in (
        # positives
        ("רד מטר", "רד מטר אחד"),
        ("לאט לאט תרד מטר.", "לאט לאט תרד מטר אחד."),
        ("תמתין חמש שניות ואז רד מטר", "תמתין חמש שניות ואז רד מטר אחד"),
        # negatives
        ("תעלה 15 מטר", "תעלה 15 מטר"),
        ("תעלה חמישה עשר מטר", "תעלה חמישה עשר מטר"),
        ("טוס ימינה מטר וחצי", "טוס ימינה מטר וחצי"),
        ("זוז אחורה מטר אחד", "זוז אחורה מטר אחד"),
        ("רד שני מטרים", "רד שני מטרים"),
        ("המטר האחרון", "המטר האחרון"),
    ):
        assert explicit_one_meter(s_in) == want, s_in


def test_a_number_after_meter_that_starts_with_and_is_the_next_item():
    """מטר וחמישה מטר = a meter, and five meters: the first מטר is bare (one meter). A
    ו-number BEFORE מטר is its count; וחצי after it is its half (owner 2026-09-24)."""
    from recognizer.numbers import meter_has_number
    assert explicit_one_meter("עלה מטר וחמישה מטר ימינה") == (
        "עלה מטר אחד וחמישה מטר ימינה"
    )
    assert nums_he("עלה 3 מטר ו5 מטר ימינה") == [3.0, 5.0]
    assert meter_has_number("ו5", "") and meter_has_number("", "וחצי")
    assert not meter_has_number("", "וחמישה")


def test_emergency_word_stops_and_a_command_does_not():
    assert emergency("עצור") and not emergency("עלה עשרה מטרים")


def test_emergency_words_2026_09_08_owner_ruling():
    # הפסק / תפסיק stop the aircraft; די only alone or as the last
    # word; "stop following" is a perception clear
    for s in (
        "תפסיק", "הפסק מיד", "תפסיק עכשיו", "הפסיקו הכל",
        "די", "די די", "די!", "עצור, די",
    ):
        assert R.emergency(s), s
    for s in ("די, מספיק", "מספיק", "זה מספיק"):
        assert R.emergency(s), s
    for s in (
        "טוס די מהר",
        "עלה די גבוה",
        "מספיק גבוה",
        "תפסיק לעקוב אחרי המכונית",
        "הפסק להדגיש את החלון",
        "דיווח מצב",
        "מיידי",
    ):
        assert not R.emergency(s), s


def test_register_rewrites_2026_09_08_owner_ruling():
    f = register_imperative
    assert (
        f("אפשר להמריא") == "תמריא"
        and f("אפשר לנחות") == "תנחת"
        and f("אפשר לעלות חמישה מטרים") == "עלה חמישה מטרים"
    )
    assert f("יש אפשרות לנחות עכשיו") == "תנחת עכשיו"
    assert f("בוא נרד שני מטרים") == "תרד שני מטרים" and f("בוא נמריא") == "תמריא"
    assert (
        f("עלה לגובה עשרה מטרים") == "עלה עשרה מטרים"
        and f("טפס לגובה של עשרים מטרים") == "טפס עשרים מטרים"
    )
    for s in (
        "אתה יכול לנחות?",
        "האם אפשר לנחות",
        "אפשר לנחות?",
        "טפס לגובה ותן לי תמונת מצב",
        "תוכל לזוז ימינה שני מטרים",
    ):
        assert f(s) == s, s


# ---------------- negation guard ----------------
# pure negation, no other order -> negation_only True, recognize_direct -> reject
MUST_REFUSE = [
    "אל תעלה יותר", "אל תזוז", "לא לטוס קדימה", "בלי להסתובב בבקשה", "אל תנחת עדיין",
    "בשום אופן אל תרד עכשיו",
    # double negation (flew two spins live)
    "אל תפנה 90 מעלות שמאלה ואז אל תפנה ימינה",
    # triple negation, no order
    "בשום אופן אל תעלה ואל תרד ואל תסתובב",
    # distractor word, still pure negation
    "בבקשה אל תזוז בכלל",
    # two infinitive negations, no order
    "לא לעלות ולא לרדת",
    # negations across a comma + ואז split
    "אל תעלה, ואז אל תרד",
    # negations across the אבל split
    "אל תסתובב אבל אל תזוז",
    # negations across the אולם split
    "אל תטוס קדימה אולם אל תטוס אחורה",
    # filler words, still pure negation
    "ממש בבקשה אל תמריא עכשיו",
    # "תקשיב" is filler, not a drone order
    "תקשיב טוב, בשום אופן אל תנחת",
    # negated perception verb, no other order
    "אל תסמן את הכיסא",
    # negated verb + number; the number must NOT rescue it
    "אל תעלה חמישה מטרים",
    # two infinitive negations in one clause
    "בלי לרדת ובלי להסתובב",
    # infinitive negation + filler
    "לא לזוז בכלל בבקשה",
    # negated "fly toward", no positive order
    "אל תעוף לכיוון הבניין",
    # negated "approach", not in the verb list but still refused
    "אל תתקרב לעץ",
    # negated "continue" (continue is now a known order)
    "בשום אופן אל תמשיך",
    # negation + filler
    "אל תעלה יותר מדי",
    # infinitive negation + direction
    "לא להסתובב שמאלה",
]
MUST_PASS = [     # a real order is present -> negation_only False -> NOT reject
    # positive imperative BEFORE the negation
    "תטוס קדימה בלי לעצור",
    # negate then order (bench l75_neg_fwd_back3)
    "לא לטוס קדימה, תטוס אחורה שלושה מטרים",
    # v_neg1: climb 5, ignore the negation
    "תקשיב, עלה חמישה מטרים אבל אל תסתובב בינתיים",
    # v_neg2
    "אוקיי טוס קדימה עשרה מטרים, ובבקשה אל תנחת עדיין",
    # perception + negation (the false-fire trap)
    "שים עין על הצומת ואל תרד ממנו",
    # highlight + negation
    "סמן את הכיסא ואל תזוז ממנו",
    # plain command, no negation
    "עלה שני מטרים",
    # plain multi-step
    "תמריא, עלה חמישה מטרים, הסתובב מאה שמונים מעלות",
    # a question (drone state), no negation trigger
    "מה הגובה שלך עכשיו",
    # negation word but not the imperative pattern
    "למה אתה לא עולה",
    # negation then order across a ואז split
    "אל תרד, ואז עלה שלושה מטרים",
    # order then negation
    "עלה שני מטרים ואז אל תזוז",
    # leading manner-negation, real order "continue" follows
    "בלי לעצור תמשיך ישר",
    # negation in clause 1, order "drive slowly" in clause 2
    "אל תאיץ, סע לאט",
    # perception order + negation across אבל
    "תצלם את הרכב אבל אל תתקרב אליו",
    # count order + negation
    "ספור את המכוניות ואל תזוז",
    # order "stop" + negated "continue"
    "עצור, אל תמשיך",
    # order + negation
    "סע קדימה עשרה מטרים ואל תנחת",
    # describe order (question-shaped), no negation
    "תאר מה אתה רואה",
    # negation then "take off" after a ואז split
    "אל תמריא עד שאני אומר, ואז תמריא",
    # order "continue" first, trailing manner-negation
    "המשך ישר בלי לעצור",
    # order "slow down" + negated "stop" across אבל
    "תאט אבל אל תעצור",
    # order "hold altitude" + negation
    "שמור על הגובה, אל תרד",
    # a question, no trigger
    "מה המהירות שלך",
    # order "turn right"; "לא מהר" is not the negation pattern
    "פנה ימינה אבל לא מהר",
]


def test_pure_negations_refuse():
    bad = [s for s in MUST_REFUSE if not negation_only(s)]
    assert not bad, f"guard FAILED to fire on pure negations: {bad}"


def test_real_orders_pass_through_zero_false_fires():
    fired = [s for s in MUST_PASS if negation_only(s)]
    assert not fired, f"FALSE FIRE: guard wrongly rejected a real order: {fired}"


def test_recognize_direct_routes_pure_negation_to_reject():
    assert recognize_direct("בלי להסתובב בבקשה")[0] == "reject"
    assert recognize_direct("אל תעלה חמישה מטרים")[0] == "reject"
    assert recognize_direct("לא לטוס קדימה, תטוס אחורה שלושה מטרים")[0] != "reject"
    assert recognize_direct("בלי לעצור תמשיך ישר")[0] != "reject"


# ==================== fast path (moved from control 2026-09-23) ====================
def test_fast_path_english():
    for w in ("stop", "abort", "freeze", "kill"):
        assert critical(w) == "emergency", w
    assert critical("manual") == "manual"
    assert critical("resume") == "auto"


def test_fast_path_hebrew():
    for w in ("עצור", "עצרי", "עצרו", "תעצור", "סטופ", "חירום", "עצור עכשיו"):
        assert critical(w) == "emergency", w
    for w in ("שליטה ידנית", "ידני", "אני בשליטה"):
        assert critical(w) == "manual", w
    for w in ("המשך", "אוטומטי"):
        assert critical(w) == "auto", w
    # embedded in a longer sentence
    assert critical("רחפן תעצור מיד בבקשה") == "emergency"


def test_everything_else_is_not_critical():
    for t in (
        "what do you see",
        "how many people are in the room",
        # a QUESTION with 'land' is not an emergency
        "is the drone going to land soon",
        "fly forward five meters",
        "look down",
        "scan the area",
        "come home",
        "hello",
        "מה אתה רואה עכשיו",
    ):
        assert critical(t) is None, t
    assert critical("") is None                        # empty -> nothing, never a flight


# ==================== pipeline ====================
class RecordingVision:
    """Stands in for perception2.vision.Vision in the RECOGNIZER's tests: records each
    typed request as its old English form, so a routing test reads plainly."""

    def __init__(self, seen, status=TASK_OK):
        self.seen, self.status = seen, status

    def count(self, target):
        self.seen.append(f"count the {target}")
        return self.status, 1

    def highlight(self, target):
        self.seen.append(f"highlight the {target}")
        return self.status, 1

    def describe(self, text):
        self.seen.append(text)
        return self.status, 1

    def clear(self):
        self.seen.append("clear")


class Said:
    """Runs Recognizer.handle and keeps what the app would SAY. -> the action string, so
    the routing tests read as before. .control and ._fly reach the real Recognizer."""

    def __init__(self, pipeline, said):
        self.pipeline, self.said = pipeline, said
        self.control = pipeline.control

    def handle(self, text):
        routed = self.pipeline.handle(text)
        if routed.say:
            self.said.append(routed.say)
        return routed.action


def make(answers):
    """A Recognizer over the REAL control and phone-app client, against a REAL local HTTP
    server. phone.seen records every request that left the laptop; seen[] every vision
    request; said[] every text the app would speak."""
    phone = RecordingPhone()
    said = []
    seen = []
    # the pipeline hands the model he2 (after the Hebrew rewrites, e.g. number
    # words -> digits), so match on the first word
    planner = PlannerStub(
        lambda he: next(
            (v for k, v in answers.items() if k.split()[0] == he.split()[0]), None
        )
    )
    p = Recognizer(phone.control, RecordingVision(seen), planner)
    return Said(p, said), phone, said, seen


def flown(phone):
    """The /c/fly bodies the phone received."""
    return [body for path, body in phone.seen if path == "/c/fly"]


def test_direct_mission_flies_when_numbers_match():
    p, w, said, seen = make({
        "טוס קדימה שלושה מטרים ואז פנה ימינה תשעים מעלות": {
            "kind": "mission",
            "target_en": "",
            "mission": [{"type": "fly_by", "dx": 3}, {"type": "spin_by", "degrees": 90}],
        }
    })
    a = p.handle("טוס קדימה שלושה מטרים ואז פנה ימינה תשעים מעלות")
    assert a.startswith("mission(2 steps, planned)") and not said
    assert flown(w) == [
        [{"type": "fly_by", "dx": 3}, {"type": "spin_by", "degrees": 90}]
    ]


def test_direct_number_guard_rejects():
    p, w, said, seen = make({
        "טוס קדימה שלושה מטרים ואז פנה ימינה תשעים מעלות": {
            "kind": "mission",
            "target_en": "",
            "mission": [{"type": "fly_by", "dx": 3}, {"type": "spin_by", "degrees": 45}],
        }
    })
    a = p.handle("טוס קדימה שלושה מטרים ואז פנה ימינה תשעים מעלות")
    assert (
        a == "reject-numbers"
        and w.seen == []
        and said
        and said[0].startswith("לא הבנתי")
    )


def test_direct_highlight_count_describe_reject():
    p, w, said, seen = make({
        "סמן את המכונית האדומה": {
            "kind": "highlight", "target_en": "red car", "mission": []
        },
        "כמה אנשים ליד הכניסה": {
            "kind": "count", "target_en": "people near the entrance", "mission": []
        },
        "תאר לי מה יש מימין": {"kind": "describe", "target_en": "", "mission": []},
        "מה הגובה שלך": {"kind": "reject", "target_en": "", "mission": []}})
    assert (
        p.handle("סמן את המכונית האדומה").startswith("perception(highlight")
        and seen[-1] == "highlight the red car"
    )
    assert (
        p.handle("כמה אנשים ליד הכניסה").startswith("perception(count")
        and seen[-1] == "count the people near the entrance"
    )
    assert (
        p.handle("תאר לי מה יש מימין") == "perception(describe)"
        and seen[-1] == "תאר לי מה יש מימין"
    )
    assert (
        p.handle("מה הגובה שלך") == "reject"
        and said[-1] == "לא הבנתי: מה הגובה שלך"
        and w.seen == []
    )


def test_direct_bypass_and_the_fast_path_skip_the_model():
    # the planner answers no plan: a model call would not fly
    p, w, said, seen = make({})
    assert p.handle("עלה עשרה מטרים").startswith("mission(1 steps, bypass)")
    assert flown(w)[-1] == [{"type": "fly_by", "dz": 10.0}]
    assert p.handle("עצור").startswith("emergency:")
    assert w.seen[-1] == ("/c/fly", [{"type": "delay", "seconds": 0.0}]) and said


def test_spoken_manual_and_auto_go_to_control():
    p, w, said, seen = make({})
    assert p.handle("שליטה ידנית").startswith("manual:") and w.paths() == ["/c/stop"]
    assert p.control.manual_on() and "the RC has control" in said[-1]
    assert p.handle("אוטומטי").startswith("auto:") and not p.control.manual_on()


def test_new_action_verbs_pass_through_to_fly():
    # Gemma emits the extra actions in the mission array; _fly
    # sends them to /c/fly unchanged.
    for phrase, mission in [
        ("תסתכל למטה", [{"type": "gimbal_pitch", "angle": -60}]),
        ("חזור הביתה", [{"type": "home"}]),
        ("שלום", [{"type": "wave"}]),
    ]:
        p, w, said, seen = make(
            {phrase: {"kind": "mission", "target_en": "", "mission": mission}}
        )
        a = p.handle(phrase)
        assert a.startswith("mission(1 steps, planned)"), (phrase, a)
        assert flown(w) == [mission], (phrase, w.seen)


def test_manual_mode_refuses_flight_but_perception_answers():
    p, w, said, seen = make({
        "טוס קדימה שני מטרים": {
            "kind": "mission", "target_en": "", "mission": [{"type": "fly_by", "dx": 2}]
        },
        "מה אתה רואה": {"kind": "describe", "target_en": "", "mission": []}})
    # manual mode: transmit off
    p.control.manual()
    a = p.handle("טוס קדימה שני מטרים")
    # mission NOT flown in manual
    assert a.startswith("refused-manual") and flown(w) == []
    assert "manual mode is on" in said[-1]
    b = p.handle("מה אתה רואה")
    # perception still answers
    assert b == "perception(describe)" and seen[-1] == "מה אתה רואה"


def test_failed_gemma_call_is_not_blamed_on_the_user():
    p, w, said, seen = make({})
    p.pipeline.gemma = PlannerStub(lambda he: PLAN_FAILED)
    a = p.handle("סמן את המכונית הלבנה ליד העץ")
    assert a == "gemma-failed" and said == [] and seen == [] and w.seen == []


def test_an_emergency_that_did_not_arrive_says_so():
    """The phone app does not answer: the emergency is reported
    as NOT reaching the aircraft."""
    control = Control(DjiApp("127.0.0.1", dead_port(), timeout=0.5))
    pipeline = Recognizer(control, RecordingVision([]), no_plan())
    routed = pipeline.handle("עצור")
    assert routed.kind == "critical" and "did NOT reach the aircraft" in routed.action
    assert "power button" in routed.say


FLY = [{"type": "fly_by", "dx": 1}]


def test_a_phone_error_status_is_not_reported_as_flown():
    """R13: a 400/500 from the phone is a FAILED mission, not a
    flight. Real phone, real codes."""
    for code, marker in ((400, "FAILED-HTTP-400"), (500, "FAILED-HTTP-500")):
        phone = RecordingPhone(code=code)
        pipeline = Recognizer(phone.control, RecordingVision([]), no_plan())
        routed = pipeline._fly(FLY, "planned")
        assert routed.action.startswith(marker), code
        # the user hears it
        assert routed.say == f"mission FAILED: the phone app answered HTTP {code}."
        phone.close()
    phone = RecordingPhone()
    phone.control.manual()
    pipeline = Recognizer(phone.control, RecordingVision([]), no_plan())
    routed = pipeline._fly(FLY, "planned")
    assert routed.action.startswith("refused-manual") and "manual mode" in routed.say
    phone.close()
    control = Control(DjiApp("127.0.0.1", dead_port(), timeout=0.5))
    routed = Recognizer(control, RecordingVision([]), no_plan())._fly(FLY, "planned")
    assert routed.action.startswith("FAILED-unreachable") and routed.say


# ==================== recognizer helpers (all cases) ====================


def test_apply_he_reports_which_rules_fired():
    from recognizer.rewrites import apply_he
    assert apply_he("טוס עשרים מטר קדימה") == ("טוס 20 מטר קדימה", ["hebnum-digits"])
    assert apply_he("עצור")[1] == []


def test_a_bare_meter_becomes_one_meter():
    from recognizer.rewrites import explicit_one_meter
    assert explicit_one_meter("טוס מטר קדימה") == "טוס מטר אחד קדימה"
    assert explicit_one_meter("טוס 5 מטר קדימה") == "טוס 5 מטר קדימה"


def test_number_guard_lists_every_missing_number():
    assert R.numbers_vs_mission("טוס 5 מטרים", [{"type": "fly_by", "dx": 5}]) == []
    assert R.numbers_vs_mission(
        "טוס 5 מטרים ופנה 90", [{"type": "fly_by", "dx": 5}]
    ) == [90.0]
    assert R.numbers_vs_mission("טוס 5 מטרים", []) == [5.0]


def test_a_copied_few_shot_example_is_an_echo():
    from recognizer.guards import SHOT_MISSIONS, is_shot_echo
    # the example, without its numbers
    assert is_shot_echo("fly", SHOT_MISSIONS[0]) is True
    assert is_shot_echo("fly", [{"type": "delay", "seconds": 0.0}]) is False


def test_a_spoken_clear_clears_without_the_model():
    p, w, said, seen = make({})                  # no plan: no model result
    assert p.handle("תפסיק לעקוב") == "perception(clear)" and seen == ["clear"]
    assert p.handle("never mind") == "perception(clear)"


def test_a_full_vision_service_is_said_not_silent():
    phone = RecordingPhone()
    seen = []
    planner = PlannerStub(
        lambda he: {"kind": "count", "target_en": "people", "mission": []}
    )
    p = Recognizer(phone.control, RecordingVision(seen, status=TASK_FULL), planner)
    routed = p.handle("כמה אנשים יש")
    assert routed.kind == "vision" and routed.vision_status == TASK_FULL
    assert "Too many vision tasks" in routed.say
    phone.close()


# ==================== lexicon.py (moved from perception2) ====================
def test_clear_miss_is_replaced():
    assert fix_target("כמה מגירות אתה רואה בסצנה", "cabin") == (
        "drawer", "lexicon:'cabin'->'drawer'"
    )
    assert fix_target("כמה שידות אתה רואה", "desks")[0] == "dresser"


def test_correct_target_untouched():
    assert fix_target("סמן את המכונית האדומה", "red car") == ("red car", None)
    assert fix_target("סמן את כל המסכים בבקשה", "all screens") == ("all screens", None)
    assert fix_target("ספור את הכיסאות", "chairs") == ("chairs", None)


def test_no_lexicon_noun_untouched():
    assert fix_target("סמן את הדבר הכחול", "blue thing") == ("blue thing", None)


def test_prefixes_and_order():
    assert [en for _, en in find_nouns("סמן את הכיסא שליד החלון")] == ["chair", "window"]
    assert fix_target("סמן את הכיסא שליד החלון", "sofa")[0] == "chair"


def test_reject_why_names_every_reject_reason():
    assert "negation" in reject_why("reject-neg-guard")
    assert "number" in reject_why("reject-numbers[5.0]")
    assert "echoed" in reject_why("reject-planner-echo")
    assert (
        "could not turn" in reject_why("reject")
        and "could not turn" in reject_why(None)
    )


def test_a_reject_tells_the_log_why():
    phone = RecordingPhone()
    notes = {}

    class Log:
        def set(self, **fields):
            notes.update(fields)

    p = Recognizer(phone.control, RecordingVision([]), no_plan(), Log())
    assert p.handle("אל תזוז").kind == "reject"
    assert "negation" in notes["reject_reason"]
    phone.close()
