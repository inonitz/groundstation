"""Recognizer unit tests: the component self-test plus the emergency and register-rewrite rulings.
The Pipeline direct path (mission / number guard / highlight / count / describe / reject / bypass /
emergency) is covered by test_pipeline_direct.py."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "recognizer"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import recognizer as R


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
