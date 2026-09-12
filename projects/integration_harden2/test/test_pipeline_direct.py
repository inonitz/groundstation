import os, sys
os.environ["MVD_TRANSLATOR"] = "none"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "recognizer"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline import Pipeline


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
