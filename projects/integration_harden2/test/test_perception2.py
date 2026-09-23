"""Tests for perception2/: the SAM3 backend contract, engine, one-consumer task queue, text parsing,
concepts, counting, lexicon, verify, and the Gemma vision client. No models, no GPU."""
import os
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from perception2 import concept, vlm_client
from perception2.backend import DETECT_NOT_READY, DETECT_OK
from perception2.concept import phrase_concepts
from perception2.counting import count_instances, median_count
from perception2.engine import PerceptionEngine, scale_vlm_box
from perception2.engine import selftest as engine_selftest
from perception2.lexicon import find_nouns, fix_target
from perception2.task_queue import (PRIORITY_COMMAND, PRIORITY_REFRESH, SUBMIT_FULL, SUBMIT_OK,
                                    TaskQueue)
from perception2.text_parse import parse_count, parse_highlight
from perception2.text_parse import selftest as text_parse_selftest
from perception2.verify import region_is_color, rel_holds, split_target, verify_highlight


# ==================== text_parse ====================
def test_text_parse_selftest_clean():
    assert text_parse_selftest() == []


def test_parse_highlight_forms():
    assert parse_highlight("highlight the red backpack please") == "red backpack"
    assert parse_highlight("where is my guitar case") == "guitar case"
    assert parse_highlight("track that person in the black hat") == "person in the black hat"
    assert parse_highlight("never mind") == ""
    assert parse_highlight("what do you see right now") is None


def test_parse_count_routes_counting_to_sam3():
    assert parse_count("count the red cars") == "red cars" and parse_count("count all the people near the entrance.") == "people near the entrance"
    assert parse_count("highlight the red car") is None and parse_highlight("count the red cars") is None


# ==================== concept ====================
def test_concept_selftest_clean():
    assert concept.selftest() == []


def test_phrase_concepts_drops_relational_clauses_for_sam3():
    assert phrase_concepts("the man with glasses talking to the woman in the yellow shirt").startswith("man with glasses")
    assert phrase_concepts("the box next to the man standing on the roof").startswith("box")
    assert phrase_concepts("the red backpack") == phrase_concepts("red backpack")



def test_concepts_positional_and_synonyms():
    assert phrase_concepts("top left window") == "window"
    assert phrase_concepts("window panes") == "window"
    assert phrase_concepts("all screens") == "monitor, television, screen"
    assert phrase_concepts("the cabinets") == "cabinet, cupboard, wardrobe"


# ==================== lexicon ====================
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


# ==================== counting ====================
def _d(conf, box): return {"conf": conf, "box": box}


def test_threshold_drops_low_conf():
    assert len(count_instances([_d(0.9, (0, 0, 100, 100)), _d(0.3, (200, 200, 300, 300))])) == 1


def test_part_inside_whole_is_one_instance():
    whole = _d(0.93, (100, 100, 400, 500)); back = _d(0.62, (120, 110, 380, 300)); other = _d(0.7, (600, 100, 900, 500))
    kept = count_instances([back, whole, other])
    assert [k["box"] for k in kept] == [whole["box"], other["box"]]


def test_side_by_side_chairs_both_count():
    a = _d(0.9, (0, 0, 100, 100)); b = _d(0.8, (90, 0, 190, 100))   # 10 % overlap
    assert len(count_instances([a, b])) == 2


def test_zero_area_box_ignored():
    assert count_instances([_d(0.9, (5, 5, 5, 50))]) == []


def test_median_count():
    assert median_count([2, 5, 4]) == 4 and median_count([6, 1]) == 1 and median_count([]) == 0 and median_count([3]) == 3


def test_speck_boxes_dropped_with_frame_area():
    speck = _d(0.86, (10, 10, 20, 20)); real = _d(0.7, (100, 100, 400, 400))     # 100 px2 vs 90000 px2
    kept = count_instances([speck, real], 0.5, frame_area=1280 * 720, min_frac=0.001)
    assert [k["box"] for k in kept] == [real["box"]]
    assert len(count_instances([speck, real], 0.5)) == 2                            # no floor when frame_area is absent


# ==================== engine ====================
def test_engine_selftest_clean():
    assert engine_selftest() == []


def test_relative_gate_keeps_near_peers():
    frame = np.zeros((100, 100, 3), np.uint8)
    two_windows = [{"label": "window", "conf": 0.88, "box": (10, 10, 30, 30)},
                   {"label": "window", "conf": 0.85, "box": (50, 50, 70, 70)}]
    eng = PerceptionEngine(detect=lambda f, p, c: (DETECT_OK, two_windows),
                           mask_for_box=lambda f, b: None, vlm_ask=None)
    dets, masks, dbg = eng.highlight_step(frame, "window", use_sam=False)
    assert len(dets) == 2                       # peers within 65% of the top both survive


def test_full_frame_box_without_mask_is_dropped():
    frame = np.zeros((100, 100, 3), np.uint8)
    eng = PerceptionEngine(detect=lambda f, p, c: (DETECT_OK, [{"label": "x", "conf": 0.9, "box": (0, 0, 99, 99)}]),
                           mask_for_box=lambda f, b: None, vlm_ask=None)
    dets, masks, _ = eng.highlight_step(frame, "x")
    assert dets == [] and masks == []


def test_box_scaling_both_conventions():
    shape = (100, 200, 3)
    assert scale_vlm_box((0.5, 0.5, 1.0, 1.0), shape) == (100, 50, 200, 100)
    assert scale_vlm_box((500, 500, 1000, 1000), shape) == (100, 50, 200, 100)


def test_failed_detect_draws_nothing_and_reports_it():
    frame = np.zeros((100, 100, 3), np.uint8)
    eng = PerceptionEngine(detect=lambda f, p, c: (DETECT_NOT_READY, []), mask_for_box=lambda f, b: None, vlm_ask=None)
    dets, masks, dbg = eng.highlight_step(frame, "window")
    assert dets == [] and masks == [] and dbg["status"] == DETECT_NOT_READY


# ==================== verify ====================
def test_split_target_keeps_the_related_clause():
    t = split_target("man with glasses talking to woman in yellow shirt")
    assert t.head == "man with glasses" and t.relation == "near"
    assert t.related[0].noun == "woman in yellow shirt" and t.related[0].color == "yellow"
    t = split_target("backpack held by child with green shirt")
    assert t.head == "backpack" and t.relation == "touch" and t.related[0].noun == "child with green shirt" and t.related[0].color == "green"
    t = split_target("person standing on the roof of the white building")
    assert t.head == "person" and t.relation == "on" and t.related[0].noun.startswith("roof")
    assert t.related[0].color == ""                     # 'white' belongs to the building, not the roof
    assert split_target("the chair").related == [] and split_target("the chair").relation == "none"

def test_rel_holds_geometry():
    roof = (100, 100, 500, 200); person_on = (250, 20, 300, 110); person_far = (250, 400, 300, 500)
    assert rel_holds("on", person_on, roof) and not rel_holds("on", person_far, roof)
    chair = (100, 230, 900, 720); sitter = (100, 0, 900, 720)                       # sitting on = overlap, not bottom-on-top
    assert rel_holds("on", sitter, chair)
    a = (0, 0, 100, 100); near = (110, 0, 200, 100); far = (900, 0, 1000, 100)
    assert rel_holds("near", a, near) and not rel_holds("near", a, far)
    assert rel_holds("touch", a, (90, 0, 150, 100)) and not rel_holds("touch", a, (140, 0, 240, 100))   # gap 40 > 25
    assert rel_holds("in", (10, 10, 50, 50), a) and not rel_holds("in", (60, 60, 200, 200), a)

def test_region_is_color():
    fr = np.zeros((100, 100, 3), np.uint8); fr[:, :] = (0, 200, 0)       # BGR green
    assert region_is_color(fr, (0, 0, 100, 100), "green") and not region_is_color(fr, (0, 0, 100, 100), "red")

def _fake(dets_by_phrase):
    return lambda frame, phrase, floor: (DETECT_OK, list(dets_by_phrase.get(phrase, [])))

def test_verify_absent_related_noun_refuses():
    fr = np.zeros((720, 1280, 3), np.uint8)
    t = split_target("backpack held by child with green shirt")
    det = _fake({"backpack": [{"label": "backpack", "conf": 0.9, "box": (100, 100, 300, 400)}]})   # no child anywhere
    v = verify_highlight(det, fr, t)
    assert v.verdict == "absent" and "child" in v.reason

def test_verify_draws_when_relation_holds_and_flags_misplaced():
    fr = np.zeros((720, 1280, 3), np.uint8); fr[:, :] = (0, 200, 0)      # everything green, so the color check passes
    t = split_target("backpack held by child with green shirt")
    bp = {"label": "backpack", "conf": 0.9, "box": (100, 100, 300, 400)}
    child_near = {"label": "child", "conf": 0.8, "box": (280, 100, 500, 600)}
    child_far = {"label": "child", "conf": 0.8, "box": (900, 100, 1100, 600)}
    assert verify_highlight(_fake({"backpack": [bp], "child with green shirt": [child_near]}), fr, t).verdict == "draw"
    assert verify_highlight(_fake({"backpack": [bp], "child with green shirt": [child_far]}), fr, t).verdict == "misplaced"

def test_verify_simple_query_is_untouched():
    fr = np.zeros((720, 1280, 3), np.uint8)
    v = verify_highlight(_fake({"chair": [{"label": "chair", "conf": 0.9, "box": (100, 100, 300, 400)}]}), fr, split_target("the chair"))
    assert v.verdict == "draw" and v.reason == "simple"


def test_failed_sam3_call_is_a_failed_verdict_not_absent():
    fr = np.zeros((480, 640, 3), np.uint8)
    failing = lambda frame, phrase, floor: (DETECT_NOT_READY, [])
    v = verify_highlight(failing, fr, split_target("the backpack held by the child"))
    assert v.verdict == "failed"               # mvd fails open on this; "absent" would veto the highlight


# ==================== task_queue ====================
def _wait_for(pred, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_every_task_runs_on_one_consumer_thread():
    q = TaskQueue(max_active=8)
    threads = []
    for _ in range(5):
        q.submit(lambda: threads.append(threading.get_ident()))
    assert _wait_for(lambda: len(threads) == 5)
    assert len(set(threads)) == 1 and threads[0] != threading.get_ident()
    q.shutdown()


def test_fresh_command_preempts_a_due_refresh():
    q = TaskQueue(max_active=8)
    gate = threading.Event()
    order = []
    q.submit(gate.wait)                                   # hold the consumer busy
    q.submit(lambda: order.append("refresh"), priority=PRIORITY_REFRESH)
    q.submit(lambda: order.append("command"), priority=PRIORITY_COMMAND)
    gate.set()
    assert _wait_for(lambda: len(order) == 2)
    assert order == ["command", "refresh"]
    q.shutdown()


def test_delayed_task_waits_until_due():
    q = TaskQueue(max_active=8)
    ran = []
    t0 = time.monotonic()
    q.submit(lambda: ran.append(time.monotonic() - t0), delay=0.3)
    assert _wait_for(lambda: ran)
    assert ran[0] >= 0.29
    q.shutdown()


def test_cap_refuses_past_max_active():
    q = TaskQueue(max_active=2)
    gate = threading.Event()
    q.submit(gate.wait)                                   # running, no longer pending
    assert _wait_for(lambda: q.pending() == 0)
    assert q.submit(lambda: None, delay=5) == SUBMIT_OK
    assert q.submit(lambda: None, delay=5) == SUBMIT_OK
    assert q.submit(lambda: None, delay=5) == SUBMIT_FULL
    gate.set()
    q.shutdown()


def test_cancel_drops_tagged_tasks_only():
    q = TaskQueue(max_active=8)
    ran = []
    q.submit(lambda: ran.append("a"), delay=0.2, tag="hl-1")
    q.submit(lambda: ran.append("b"), delay=0.2, tag="hl-2")
    assert q.cancel("hl-1") == 1
    assert _wait_for(lambda: ran == ["b"])
    time.sleep(0.3)
    assert ran == ["b"]
    q.shutdown()


def test_shutdown_stops_an_idle_consumer():
    q = TaskQueue(max_active=8)
    q.shutdown()
    assert not q._thread.is_alive()


# ==================== vlm_client ====================
def test_vlm_reply_parsing():
    long_, tgt, box, short = vlm_client.parse_reply(
        "LONG RESPONSE: Two people near a car.\nSHORT RESPONSE: Two people.\n"
        "HIGHLIGHT: the red car\nVLM_BOX: 0.1,0.2,0.5,0.6")
    assert tgt == "the red car" and box == (0.1, 0.2, 0.5, 0.6)
    assert long_ == "Two people near a car." and short == "Two people."
    _, tgt2, box2, _ = vlm_client.parse_reply(
        "LONG RESPONSE: No dog visible.\nSHORT RESPONSE: No dog.\nHIGHLIGHT: none")
    assert tgt2 is None and box2 is None


def test_ask_returns_false_and_no_reply_when_gemma_fails(monkeypatch):
    monkeypatch.setattr(vlm_client, "request", lambda *a, **k: (False, ""))
    assert vlm_client.ask(np.zeros((16, 16, 3), np.uint8), "what do you see", []) == (False, None)


def test_ask_parses_a_successful_reply(monkeypatch):
    reply = "LONG RESPONSE: A red car.\nSHORT RESPONSE: A car.\nHIGHLIGHT: red car\nVLM_BOX: 0.1,0.1,0.5,0.5"
    monkeypatch.setattr(vlm_client, "request", lambda *a, **k: (True, reply))
    ok, (long_, tgt, box, short) = vlm_client.ask(np.zeros((16, 16, 3), np.uint8), "highlight the red car", [])
    assert ok and tgt == "red car" and short == "A car." and box == (0.1, 0.1, 0.5, 0.5)


def test_presence_gate_fails_open_when_gemma_fails():
    eng = PerceptionEngine(detect=None, mask_for_box=None, vlm_ask=lambda f, q, d: (False, None))
    assert eng.presence_gate(np.zeros((100, 100, 3), np.uint8), "cat") == (True, None)


# ==================== direct cases for the helpers ====================
def test_ascii_only_drops_non_ascii():
    from perception2.text_parse import ascii_only
    assert ascii_only("chair כיסא") == "chair " and ascii_only(None) == ""


def test_apply_masks_tightens_to_the_mask_and_drops_garbage():
    frame = np.zeros((100, 100, 3), np.uint8)
    good = np.zeros((100, 100), bool)
    good[40:60, 40:60] = True
    garbage = np.ones((100, 100), bool)
    det = {"label": "x", "conf": 0.9, "box": (10, 10, 90, 90)}
    eng = PerceptionEngine(detect=None, mask_for_box=lambda f, b: good, vlm_ask=None)
    kept, masks = eng.apply_masks(frame, [det])
    assert kept[0]["box"] == (40, 40, 59, 59) and len(masks) == 1
    eng2 = PerceptionEngine(detect=None, mask_for_box=lambda f, b: garbage, vlm_ask=None)
    kept2, masks2 = eng2.apply_masks(frame, [det])
    assert masks2 == [] and kept2 == [det]                           # the box stays, the garbage mask goes
    kept3, _ = eng2.apply_masks(frame, [{"label": "x", "conf": 0.9, "box": (0, 0, 99, 99)}])
    assert kept3 == []                                               # a full-frame box with no clean mask



def test_a_refresh_is_never_refused_by_the_cap():
    """R25: a highlight's next refresh continues an accepted task, so the cap does not refuse it."""
    q = TaskQueue(max_active=1)
    q.submit(lambda: None, delay=5)
    assert q.submit(lambda: None, delay=5) == SUBMIT_FULL
    assert q.submit(lambda: None, priority=PRIORITY_REFRESH, delay=5) == SUBMIT_OK
    q.shutdown()
