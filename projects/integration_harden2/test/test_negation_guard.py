"""Negation guard: PURE action-negations refuse; anything with a real order passes through.
Zero false fires is the ship gate. Adversarial by design, per owner (stress the unlikely, not just realistic).
Dataset grown 2026-09-11 (A7): clause-spanning connectors, leading manner-negations, perception+negation,
negated number+unit, and the continue/slow/speed verbs added to the positive-imperative list."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from recognizer.recognizer import negation_only, recognize_direct

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
