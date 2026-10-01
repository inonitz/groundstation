"""Tests for labels.py: load, propose, the plan in plain words, save, resume, edit."""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels as L


def _copy(tmp_path):
    """A copy of the real recordings file (the owner may be writing the real one)."""
    out = tmp_path / "recordings.json"
    if os.path.exists(L.OUT):
        shutil.copy(L.OUT, out)
    return str(out)


def test_it_loads_the_139_clips_and_skips_the_live_lists():
    rows = L.load_manifest()
    pool = L.load_cases()
    assert len(rows) == 139
    assert pool and all(isinstance(case, dict) for _, case, _ in pool)
    assert not any(name.startswith("live-test") for name, _, _ in pool)


def test_the_proposal_takes_the_nearest_sentence_only_when_it_is_close():
    rows = [{"clip": "clips/a.wav", "transcript_he": "טוס ימינה מטר אחד",
             "action": "mission"}]
    case = {"name": "g_fwd1", "he": "טוס קדימה מטר אחד", "expect": {"kind": "none"}}
    far = L.propose(rows[0], (0.88, "commands.json", case))
    near = L.propose(rows[0], (0.95, "commands.json", case))
    assert far["he"] == "טוס ימינה מטר אחד"              # whisper's text below 0.9
    assert near["he"] == "טוס קדימה מטר אחד"
    assert far["wav"] == "datasets/asr/clips/a.wav" and far["case"] == "g_fwd1"


def test_the_plan_is_said_in_plain_words():
    expect = {"kind": "mission", "steps": [
        ["fly_by", "dx", -8],
        ["fly_by", "dz", 10.0],
        ["spin_by", "degrees", 90],
        ["spin_by", "degrees", ["abs", 180]],
        ["delay", "seconds", 3],
        ["takeoff", None, None],
    ]}
    assert L.plan_words(expect) == [
        "fly backwards 8 m",
        "fly up 10 m",
        "turn right 90° (clockwise)",
        "turn 180°, either way",
        "wait 3 s",
        "take off",
    ]
    assert L.plan_words({"kind": "emergency"}) == ["Emergency stop"]
    groups = {"kind": "perception", "groups": [["car", "vehicle"], ["red"]]}
    # REWRITTEN (UI1 (4)): the words now name the vision kind ("any kind" here)
    assert L.plan_words(groups) == [
        "A vision request (any kind) that names: car / vehicle; red"
    ]


def test_a_typed_plan_is_read_or_refused():
    assert L.read_expect("dx-8") == (
        {"kind": "mission", "steps": [["fly_by", "dx", -8.0]]}, None
    )
    assert L.read_expect('{"kind": "none"}') == ({"kind": "none"}, None)
    assert L.read_expect("fly somewhere")[0] is None
    assert L.read_expect('{"kind": ')[0] is None
    assert L.read_expect("[1, 2]")[0] is None


def test_save_writes_in_clip_order_and_a_restart_resumes(tmp_path):
    out = str(tmp_path / "recordings.json")
    rec = L.Recordings(out)
    assert rec.first_unsaved() == 0
    rec.save(2, "טוס אחורה 8 מטרים", {"kind": "none"})
    rec.save(0, "עלה", {"kind": "review"})
    rec.save(1, "רד  שני מטרים", {"kind": "open"})
    again = L.Recordings(out)
    cases = json.load(open(out, encoding="utf-8"))["cases"]
    assert [c["wav"] for c in cases] == [L.wav_of(again.rows[i]) for i in (0, 1, 2)]
    assert cases[1]["he"] == "רד  שני מטרים"        # exactly what the box held (UI1 (3))
    assert cases[0]["note"].endswith("the owner: not gradable")
    assert again.saved_count() == 3 and again.first_unsaved() == 3
    assert not os.path.exists(out + ".tmp")


def test_go_to_a_saved_clip_shows_and_edits_what_was_saved(tmp_path):
    out = _copy(tmp_path)
    rec = L.Recordings(out)
    before = rec.saved_count()
    rec.save(12, "טוס אחורה 8 מטרים", rec.clip(12)["case"]["expect"])
    clip = L.Recordings(out).clip(12)
    assert clip["saved"] and clip["case"]["he"] == "טוס אחורה 8 מטרים"
    assert L.Recordings(out).saved_count() in (before, before + 1)
    assert len(clip["options"]) == L.ALTERNATIVES and clip["plan"]


def _case(name):
    with open(os.path.join(L.CASES_DIR, "commands.json"), encoding="utf-8") as src:
        return {c["name"]: c for c in json.load(src)["cases"]}[name]


def test_every_row_action_has_the_benchmarks_step_and_sign():
    """UI1 (3): the editor's rows map to the phone app's steps with the benchmark's
    signs, checked against its own cases (up10, spin90cw, g_right4, g_left1, g_fwd1)."""
    rows = {
        "fly forward": ["fly_by", "dx", 2.0],
        "fly back": ["fly_by", "dx", -2.0],
        "fly right": ["fly_by", "dy", 2.0],
        "fly left": ["fly_by", "dy", -2.0],
        "go up": ["fly_by", "dz", 2.0],
        "go down": ["fly_by", "dz", -2.0],
        "turn right": ["spin_by", "degrees", 2.0],
        "turn left": ["spin_by", "degrees", -2.0],
        "turn either way": ["spin_by", "degrees", ["abs", 2.0]],
        "take off": ["takeoff", None, None],
        "land": ["land", None, None],
        "wait": ["delay", "seconds", 2.0],
    }
    assert set(rows) == set(L.ROW_ACTIONS)
    for action, step in rows.items():
        assert L.row_step({"action": action, "amount": "2"}) == (step, None), action
    for name, action, amount in (
        ("up10", "go up", "10"),
        ("spin90cw", "turn right", "90"),
        ("g_right4", "fly right", "4"),
        ("g_left1", "fly left", "1"),
        ("g_fwd1", "fly forward", "1"),
    ):
        expect, error = L.expect_from_rows([{"action": action, "amount": amount}])
        assert error is None and expect == _case(name)["expect"], name


def test_rows_read_back_every_plan_of_the_cases():
    """rows_of is the reverse of the editor: every mission of commands.json comes back
    the same from its rows."""
    with open(os.path.join(L.CASES_DIR, "commands.json"), encoding="utf-8") as src:
        cases = json.load(src)["cases"]
    missions = [c["expect"] for c in cases if c["expect"]["kind"] == "mission"]
    assert missions
    for expect in missions:
        back, error = L.expect_from_rows(L.rows_of(expect))
        assert error is None and back == expect, expect


def test_an_empty_amount_is_the_sign_only_and_bad_rows_are_refused():
    back = L.row_step({"action": "fly back", "amount": ""})
    assert back == (["fly_by", "dx", "-"], None)
    assert L.row_step({"action": "turn either way", "amount": ""})[0] is None
    assert L.row_step({"action": "fly left", "amount": "-3"})[0] is None
    assert L.row_step({"action": "dance", "amount": "1"})[0] is None
    assert L.expect_from_rows([])[0] is None


def test_the_sentence_starts_as_whispers_exact_text(tmp_path):
    """UI1 (3): an unsaved clip's sentence is transcript_he, character for character,
    even when a nearest case is identical after normalizing."""
    rec = L.Recordings(str(tmp_path / "recordings.json"))
    for index in range(rec.total()):
        clip = rec.clip(index)
        heard = rec.rows[index]["transcript_he"] or ""     # null: whisper wrote nothing
        assert clip["case"]["he"] == heard and clip["heard"] == heard


class _Decision:
    """What route() decided, as the scorer reads it: a kind and a target."""

    def __init__(self, kind, target):
        self.kind = kind
        self.target = target


def test_a_vision_request_is_saved_as_the_scorer_grades_it():
    """REWRITTEN (SC1, 2026-09-30: the kind has its own field, no longer a keyword
    group). The REAL scorer passes the right kind and target, and fails a wrong kind or a
    wrong target."""
    import scorer
    expect, error = L.vision_expect("highlight", "Chair / seat, red")
    assert error is None
    assert expect == {
        "kind": "perception",
        "vision": "highlight",
        "groups": [["chair", "seat"], ["red"]],
    }

    def verdict(kind, target):
        return scorer.score(expect, _Decision(kind, target))[0]

    assert verdict("highlight", "red seat") == "PASS"
    assert verdict("count", "red chair") == "FAIL"       # the wrong kind
    assert verdict("highlight", "table") == "FAIL"       # the wrong target
    any_kind, _ = L.vision_expect("any", "chair")
    assert any_kind == {"kind": "perception", "groups": [["chair"]]}
    assert scorer.score(any_kind, _Decision("count", "chairs"))[0] == "PASS"


def test_the_vision_editor_reads_back_and_refuses_bad_input():
    expect, _ = L.vision_expect("count", "person / people")
    assert L.vision_of(expect) == {"kind": "count", "words": "person / people"}
    assert L.plan_words(expect) == ["A count request that names: person / people"]
    any_kind = {"kind": "perception", "groups": [["box", "crate"], ["roof"]]}
    assert L.vision_of(any_kind) == {"kind": "any", "words": "box / crate, roof"}
    assert L.vision_expect("any", "")[0] is None
    assert L.vision_expect("highlight", "כיסא")[0] is None
    assert L.vision_expect("wave", "chair")[0] is None


def test_a_clip_offers_the_target_of_its_nearest_vision_request(tmp_path):
    rec = L.Recordings(str(tmp_path / "recordings.json"))
    visions = [
        opt["vision"]
        for index in range(rec.total())
        for opt in rec.clip(index)["options"]
        if opt["expect"]["kind"] == "perception"
    ]
    assert visions and all(v["words"] or v["kind"] != "any" for v in visions[:5])
