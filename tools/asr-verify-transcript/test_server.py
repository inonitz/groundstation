"""Tests for server.py over a REAL local HTTP server (127.0.0.1), on a copy."""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels as L
import server


def _start(tmp_path):
    rec = L.Recordings(str(tmp_path / "recordings.json"))
    srv = server.serve(rec, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _get(url):
    with urllib.request.urlopen(url) as res:
        return res.status, res.read()


def _post(url, value):
    body = json.dumps(value, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode("utf-8"))


def test_the_page_the_audio_and_the_state_are_served(tmp_path):
    srv, base = _start(tmp_path)
    status, page = _get(base + "/")
    assert status == 200 and b'dir="rtl"' in page
    status, wav = _get(base + "/audio/0")
    assert status == 200 and wav[:4] == b"RIFF"
    state = json.loads(_get(base + "/api/state")[1])
    assert state == {"total": 139, "saved": 0, "first_unsaved": 0,
                     "out": str(tmp_path / "recordings.json")}
    srv.shutdown()


def test_hebrew_goes_through_the_api_and_back_unchanged(tmp_path):
    srv, base = _start(tmp_path)
    sentence = "טוס אחורה 8 מטרים"
    plan = _post(base + "/api/parse", {"text": "dx-8"})
    assert plan["ok"] and plan["plan"] == ["fly backwards 8 m"]
    saved = _post(base + "/api/save", {"index": 12, "he": sentence,
                                       "expect": plan["expect"], "option": 1})
    assert saved["ok"] and saved["saved"] == 1 and saved["first_unsaved"] == 0
    clip = json.loads(_get(base + "/api/clip/12")[1].decode("utf-8"))
    assert clip["saved"] and clip["case"]["he"] == sentence
    on_disk = json.load(open(tmp_path / "recordings.json", encoding="utf-8"))
    assert on_disk["cases"][0]["he"] == sentence
    srv.shutdown()


def test_a_bad_plan_a_bad_clip_and_a_save_with_no_sentence_field_are_refused(tmp_path):
    srv, base = _start(tmp_path)
    assert _post(base + "/api/parse", {"text": "fly somewhere"})["ok"] is False
    for path in ("/api/clip/139", "/api/clip/x", "/audio/../../etc/passwd"):
        with pytest.raises(urllib.error.HTTPError) as err:
            _get(base + path)
        assert err.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as err:
        _post(base + "/api/save", {"index": 0, "expect": {"kind": "none"}})
    assert err.value.code == 400
    assert not os.path.exists(tmp_path / "recordings.json")
    srv.shutdown()


def test_the_rows_become_a_plan_over_the_api(tmp_path):
    srv, base = _start(tmp_path)
    rows = [
        {"action": "fly back", "amount": "8"},
        {"action": "turn left", "amount": "45"},
    ]
    res = _post(base + "/api/rows", {"rows": rows})
    assert res["ok"] and res["expect"] == {"kind": "mission", "steps": [
        ["fly_by", "dx", -8.0], ["spin_by", "degrees", -45.0]]}
    assert res["plan"] == ["fly backwards 8 m", "turn left 45° (counter-clockwise)"]
    assert _post(base + "/api/rows", {"rows": []})["ok"] is False
    srv.shutdown()


def test_nothing_was_said_saves_an_empty_sentence_and_nothing_flies(tmp_path):
    """Owner B4 (7), clip 63: "Nothing was said ... it NEEDS to be empty." What the
    "Nothing was said" button sends."""
    srv, base = _start(tmp_path)
    silent = {"index": 62, "he": "", "expect": {"kind": "none"}}
    saved = _post(base + "/api/save", silent)
    assert saved["ok"] and saved["saved"] == 1
    clip = json.loads(_get(base + "/api/clip/62")[1].decode("utf-8"))
    assert clip["saved"] and clip["case"]["he"] == "" and clip["plan"] == [
        "Nothing flies (a reject, an empty plan, a vision request or a halt)"
    ]
    on_disk = json.load(open(tmp_path / "recordings.json", encoding="utf-8"))["cases"]
    assert on_disk[0]["he"] == "" and on_disk[0]["expect"] == {"kind": "none"}
    status, page = _get(base + "/")
    assert b'id="silent"' in page and b"Nothing was said" in page
    srv.shutdown()


def test_a_vision_request_goes_through_the_api(tmp_path):
    srv, base = _start(tmp_path)
    res = _post(base + "/api/vision", {"kind": "highlight", "words": "chair / seat"})
    # REWRITTEN (SC1): the kind is its own field, so the target is the first group
    assert res["ok"] and res["expect"]["vision"] == "highlight"
    assert res["expect"]["groups"] == [["chair", "seat"]]
    assert res["plan"] == ["A highlight request that names: chair / seat"]
    assert _post(base + "/api/vision", {"kind": "any", "words": ""})["ok"] is False
    saved = _post(base + "/api/save", {"index": 64, "he": "תסמן את הכיסא",
                                       "expect": res["expect"]})
    assert saved["ok"]
    clip = json.loads(_get(base + "/api/clip/64")[1].decode("utf-8"))
    assert clip["vision"] == {"kind": "highlight", "words": "chair / seat"}
    srv.shutdown()


def test_a_removed_clip_keeps_its_reason_and_is_never_graded(tmp_path):
    """Owner B4 (8): "Remove from the set" with a reason; path B skips it."""
    srv, base = _start(tmp_path)
    why = "SAM3/Gemma don't know the context regarding the system internals"
    saved = _post(base + "/api/save", {"index": 82, "he": "", "option": 0,
                                       "expect": {"kind": "none"}, "removed": why})
    assert saved["ok"]
    case = json.load(open(tmp_path / "recordings.json", encoding="utf-8"))["cases"][0]
    assert case["removed"] is True and case["removed_reason"] == why
    assert case["expect"] == {"kind": "review"}
    with pytest.raises(urllib.error.HTTPError) as err:
        _post(base + "/api/save", {"index": 83, "he": "", "removed": " ",
                                   "expect": {"kind": "none"}})
    assert err.value.code == 400
    srv.shutdown()


def test_the_nearest_cases_follow_the_typed_sentence(tmp_path):
    srv, base = _start(tmp_path)
    found = _post(base + "/api/nearest", {"index": 69, "text": "עלה עשרה מטרים"})
    assert found["options"][0]["he"] == "עלה עשרה מטרים"
    assert found["options"][0]["similarity"] == 1.0
    saved = _post(base + "/api/save", {"index": 69, "he": "עלה עשרה מטרים", "option": 0,
                                       "expect": found["options"][0]["expect"]})
    assert saved["ok"]
    case = json.load(open(tmp_path / "recordings.json", encoding="utf-8"))["cases"][0]
    assert case["case"] == found["options"][0]["name"]      # the note names that case
    srv.shutdown()
