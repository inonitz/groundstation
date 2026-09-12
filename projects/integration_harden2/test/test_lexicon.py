"""HE->EN target lexicon (block B 2026-09-09: Gemma wrote 'cabin' for מגירות and 'desks' for שידות)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from perception2.lexicon import fix_target, find_nouns
from perception2.concept import phrase_concepts


def test_clear_miss_is_replaced():
    assert fix_target("כמה מגירות אתה רואה בסצנה", "cabin") == ("drawer", "lexicon:'cabin'->'drawer'")
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


def test_concepts_positional_and_synonyms():
    assert phrase_concepts("top left window") == "window"
    assert phrase_concepts("window panes") == "window"
    assert phrase_concepts("all screens") == "monitor, television, screen"
    assert phrase_concepts("the cabinets") == "cabinet, cupboard, wardrobe"
