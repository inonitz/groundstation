"""Tests for recognizer/: the Hebrew recognizer (emergency, register rewrites, negation guard), the
Pipeline direct path. No model server is started."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import recognizer as R
from recognizer.pipeline import Pipeline
from recognizer.recognizer import negation_only, recognize_direct


# ==================== recognizer ====================
def test_component_selftest_clean():
    assert R.selftest() == []


def test_emergency_words_2026_09_08_owner_ruling():
    # הפסק / תפסיק stop the aircraft; די only alone or as the last word; "stop following" is a perception clear
    for s in ("תפסיק", "הפסק מיד", "תפסיק עכשיו", "הפסיקו הכל", "די", "די די", "די!", "עצור, די"):
        assert R.emergency(s), s
    for s in ("די, מספיק", "מספיק", "זה מספיק"):
        assert R.emergency(s), s
    for s in ("טוס די מהר", "עלה די גבוה", "מספיק גבוה", "תפסיק לעקוב אחרי המכונית", "הפסק להדגיש את החלון", "דיווח מצב", "מיידי"):
        assert not R.emergency(s), s


def test_register_rewrites_2026_09_08_owner_ruling():
    f = R.register_imperative
    assert f("אפשר להמריא") == "תמריא" and f("אפשר לנחות") == "תנחת" and f("אפשר לעלות חמישה מטרים") == "עלה חמישה מטרים"
    assert f("יש אפשרות לנחות עכשיו") == "תנחת עכשיו"
    assert f("בוא נרד שני מטרים") == "תרד שני מטרים" and f("בוא נמריא") == "תמריא"
    assert f("עלה לגובה עשרה מטרים") == "עלה עשרה מטרים" and f("טפס לגובה של עשרים מטרים") == "טפס עשרים מטרים"
    for s in ("אתה יכול לנחות?", "האם אפשר לנחות", "אפשר לנחות?", "טפס לגובה ותן לי תמונת מצב", "תוכל לזוז ימינה שני מטרים"):
        assert f(s) == s, s


# ---------------- negation guard ----------------
MUST_REFUSE = [   # pure negation, no other order -> negation_only True, recognize_direct -> reject
    "אל תעלה יותר", "אל תזוז", "לא לטוס קדימה", "בלי להסתובב בבקשה", "אל תנחת עדיין",
    "בשום אופן אל תרד עכשיו",
    "אל תפנה 90 מעלות שמאלה ואז אל תפנה ימינה",        # double negation (flew two spins live)
    "בשום אופן אל תעלה ואל תרד ואל תסתובב",             # triple negation, no order
    "בבקשה אל תזוז בכלל",                               # distractor word, still pure negation
    "לא לעלות ולא לרדת",                                 # two infinitive negations, no order
    "אל תעלה, ואז אל תרד",                               # negations across a comma + ואז split
    "אל תסתובב אבל אל תזוז",                             # negations across the אבל split
    "אל תטוס קדימה אולם אל תטוס אחורה",                  # negations across the אולם split
    "ממש בבקשה אל תמריא עכשיו",                          # filler words, still pure negation
    "תקשיב טוב, בשום אופן אל תנחת",                      # "תקשיב" is filler, not a drone order
    "אל תסמן את הכיסא",                                  # negated perception verb, no other order
    "אל תעלה חמישה מטרים",                               # negated verb + number; the number must NOT rescue it
    "בלי לרדת ובלי להסתובב",                             # two infinitive negations in one clause
    "לא לזוז בכלל בבקשה",                                # infinitive negation + filler
    "אל תעוף לכיוון הבניין",                             # negated "fly toward", no positive order
    "אל תתקרב לעץ",                                      # negated "approach", not in the verb list but still refused
    "בשום אופן אל תמשיך",                                # negated "continue" (continue is now a known order)
    "אל תעלה יותר מדי",                                  # negation + filler
    "לא להסתובב שמאלה",                                  # infinitive negation + direction
]
MUST_PASS = [     # a real order is present -> negation_only False -> NOT reject
    "תטוס קדימה בלי לעצור",                              # positive imperative BEFORE the negation
    "לא לטוס קדימה, תטוס אחורה שלושה מטרים",             # negate then order (bench l75_neg_fwd_back3)
    "תקשיב, עלה חמישה מטרים אבל אל תסתובב בינתיים",      # v_neg1: climb 5, ignore the negation
    "אוקיי טוס קדימה עשרה מטרים, ובבקשה אל תנחת עדיין",  # v_neg2
    "שים עין על הצומת ואל תרד ממנו",                     # perception + negation (the false-fire trap)
    "סמן את הכיסא ואל תזוז ממנו",                        # highlight + negation
    "עלה שני מטרים",                                     # plain command, no negation
    "תמריא, עלה חמישה מטרים, הסתובב מאה שמונים מעלות",   # plain multi-step
    "מה הגובה שלך עכשיו",                                # a question (drone state), no negation trigger
    "למה אתה לא עולה",                                   # negation word but not the imperative pattern
    "אל תרד, ואז עלה שלושה מטרים",                       # negation then order across a ואז split
    "עלה שני מטרים ואז אל תזוז",                          # order then negation
    "בלי לעצור תמשיך ישר",                               # leading manner-negation, real order "continue" follows
    "אל תאיץ, סע לאט",                                   # negation in clause 1, order "drive slowly" in clause 2
    "תצלם את הרכב אבל אל תתקרב אליו",                    # perception order + negation across אבל
    "ספור את המכוניות ואל תזוז",                         # count order + negation
    "עצור, אל תמשיך",                                    # order "stop" + negated "continue"
    "סע קדימה עשרה מטרים ואל תנחת",                      # order + negation
    "תאר מה אתה רואה",                                   # describe order (question-shaped), no negation
    "אל תמריא עד שאני אומר, ואז תמריא",                  # negation then "take off" after a ואז split
    "המשך ישר בלי לעצור",                                # order "continue" first, trailing manner-negation
    "תאט אבל אל תעצור",                                  # order "slow down" + negated "stop" across אבל
    "שמור על הגובה, אל תרד",                             # order "hold altitude" + negation
    "מה המהירות שלך",                                    # a question, no trigger
    "פנה ימינה אבל לא מהר",                              # order "turn right"; "לא מהר" is not the negation pattern
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


# ==================== pipeline ====================
class FakeWire:
    def __init__(self): self.calls = []
    def halt(self): self.calls.append("halt"); return 200
    def fly_mission(self, m): self.calls.append(("fly", m)); return 200


def make(answers):
    w = FakeWire(); said = []; seen = []
    # the pipeline hands the model he2 (after the Hebrew rewrites, e.g. number words -> digits), so match on the first word
    p = Pipeline(w, vlm_query=seen.append, say=said.append,
                 plan2_fn=lambda he: next((v for k, v in answers.items() if k.split()[0] == he.split()[0]), None))
    return p, w, said, seen


def test_direct_mission_flies_when_numbers_match():
    p, w, said, seen = make({"טוס קדימה שלושה מטרים ואז פנה ימינה תשעים מעלות":
                             {"kind": "mission", "target_en": "", "mission": [{"type": "fly_by", "dx": 3}, {"type": "spin_by", "degrees": 90}]}})
    a = p.handle("טוס קדימה שלושה מטרים ואז פנה ימינה תשעים מעלות")
    assert a.startswith("mission(2 steps, planned)") and w.calls == [("fly", [{"type": "fly_by", "dx": 3}, {"type": "spin_by", "degrees": 90}])] and not said


def test_direct_number_guard_rejects():
    p, w, said, seen = make({"טוס קדימה שלושה מטרים ואז פנה ימינה תשעים מעלות":
                             {"kind": "mission", "target_en": "", "mission": [{"type": "fly_by", "dx": 3}, {"type": "spin_by", "degrees": 45}]}})
    a = p.handle("טוס קדימה שלושה מטרים ואז פנה ימינה תשעים מעלות")
    assert a == "reject-numbers" and w.calls == [] and said and said[0].startswith("לא הבנתי")


def test_direct_highlight_count_describe_reject():
    p, w, said, seen = make({
        "סמן את המכונית האדומה": {"kind": "highlight", "target_en": "red car", "mission": []},
        "כמה אנשים ליד הכניסה": {"kind": "count", "target_en": "people near the entrance", "mission": []},
        "תאר לי מה יש מימין": {"kind": "describe", "target_en": "", "mission": []},
        "מה הגובה שלך": {"kind": "reject", "target_en": "", "mission": []}})
    assert p.handle("סמן את המכונית האדומה").startswith("perception(highlight") and seen[-1] == "highlight the red car"
    assert p.handle("כמה אנשים ליד הכניסה").startswith("perception(count") and seen[-1] == "count the people near the entrance"
    assert p.handle("תאר לי מה יש מימין") == "perception(describe)" and seen[-1] == "תאר לי מה יש מימין"
    assert p.handle("מה הגובה שלך") == "reject" and said[-1] == "לא הבנתי: מה הגובה שלך" and w.calls == []


def test_direct_bypass_and_emergency_skip_the_model():
    p, w, said, seen = make({})
    assert p.handle("עלה עשרה מטרים").startswith("mission(1 steps, bypass)") and w.calls[-1][0] == "fly"
    assert p.handle("עצור") == "emergency-halt(backup)" and w.calls[-1] == "halt"


def test_new_action_verbs_pass_through_to_fly():
    # Gemma emits the extra actions in the mission array; _fly sends them to /c/fly unchanged.
    for phrase, mission in [
        ("תסתכל למטה", [{"type": "gimbal_pitch", "angle": -60}]),
        ("חזור הביתה", [{"type": "home"}]),
        ("שלום", [{"type": "wave"}]),
    ]:
        p, w, said, seen = make({phrase: {"kind": "mission", "target_en": "", "mission": mission}})
        a = p.handle(phrase)
        assert a.startswith("mission(1 steps, planned)"), (phrase, a)
        assert w.calls == [("fly", mission)], (phrase, w.calls)


def test_manual_mode_refuses_flight_but_perception_answers():
    p, w, said, seen = make({
        "טוס קדימה שני מטרים": {"kind": "mission", "target_en": "", "mission": [{"type": "fly_by", "dx": 2}]},
        "מה אתה רואה": {"kind": "describe", "target_en": "", "mission": []}})
    p.flight_allowed = lambda: False                            # manual override active
    a = p.handle("טוס קדימה שני מטרים")
    assert a.startswith("refused-manual") and w.calls == []      # mission NOT flown in manual
    b = p.handle("מה אתה רואה")
    assert b == "perception(describe)" and seen[-1] == "מה אתה רואה"   # perception still answers


def test_failed_gemma_call_is_not_blamed_on_the_user():
    p, w, said, seen = make({})
    p.plan2_fn = lambda he: {"kind": "failed"}
    a = p.handle("סמן את המכונית הלבנה ליד העץ")
    assert a == "gemma-failed" and said == [] and seen == [] and w.calls == []


def test_backup_halt_that_did_not_arrive_says_so():
    p, w, said, seen = make({})
    w.halt = lambda: 0
    assert "FAILED (HTTP 0)" in p.handle("עצור")


def test_a_phone_error_status_is_not_reported_as_flown():
    """R13: a 400/500 from the phone is a FAILED mission, not a flight."""
    p, w, said, seen = make({})
    for code, marker in ((400, "FAILED-HTTP-400"), (500, "FAILED-HTTP-500"), (409, "REFUSED-kill-latch"), (0, "FAILED-unreachable")):
        w.fly_mission = lambda m, c=code: c
        assert p._fly([{"type": "fly_by", "dx": 1}], "planned").startswith(marker), code


# ==================== recognizer helpers (all cases) ====================
def test_hebrew_number_words_become_digits():
    from recognizer.recognizer import hebnum_to_digits
    assert hebnum_to_digits("טוס עשרים וחמישה מטרים") == "טוס 25 מטרים"
    assert hebnum_to_digits("עלה מאה עשרים מטר") == "עלה 120 מטר"
    assert hebnum_to_digits("פנה חמישה עשר מעלות") == "פנה 15 מעלות"
    assert hebnum_to_digits("השני מימין") == "השני מימין"          # an ordinal with the article is kept


def test_apply_he_reports_which_rules_fired():
    from recognizer.recognizer import apply_he
    assert apply_he("טוס עשרים מטר קדימה") == ("טוס 20 מטר קדימה", ["hebnum-digits"])
    assert apply_he("עצור")[1] == []


def test_a_bare_meter_becomes_one_meter():
    from recognizer.recognizer import explicit_one_meter
    assert explicit_one_meter("טוס מטר קדימה") == "טוס מטר אחד קדימה"
    assert explicit_one_meter("טוס 5 מטר קדימה") == "טוס 5 מטר קדימה"


def test_number_guard_lists_every_missing_number():
    assert R.numbers_vs_mission("טוס 5 מטרים", [{"type": "fly_by", "dx": 5}]) == []
    assert R.numbers_vs_mission("טוס 5 מטרים ופנה 90", [{"type": "fly_by", "dx": 5}]) == [90.0]
    assert R.numbers_vs_mission("טוס 5 מטרים", []) == [5.0]


def test_a_copied_few_shot_example_is_an_echo():
    from recognizer.pipeline import SHOT_MISSIONS, is_shot_echo
    assert is_shot_echo("fly", SHOT_MISSIONS[0]) is True               # the example, without its numbers
    assert is_shot_echo("fly", [{"type": "delay", "seconds": 0.0}]) is False


def test_trace_appends_one_numbered_json_line_per_utterance(tmp_path):
    import json
    from recognizer.trace import Trace
    t = Trace(str(tmp_path))
    t.record(text="a", kind="k", flags=[], action="x", payload={}, ms=1)
    t.record(text="b", kind="k", flags=[], action="y", payload={}, ms=2)
    lines = [json.loads(line) for line in open(t.path, encoding="utf-8")]
    assert [row["utterance"] for row in lines] == [1, 2] and lines[1]["text"] == "b"



def test_trace_reports_a_failed_write(tmp_path):
    from recognizer.trace import Trace
    t = Trace(str(tmp_path))
    t.path = str(tmp_path)                               # a directory: the append must fail
    assert t.record(text="x") is False
