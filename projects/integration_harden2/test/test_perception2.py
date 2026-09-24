"""Tests for perception2/: the backend contract and loader, the engine, the SAM3 priority
lock, the dispatcher, the vision service (count / highlight / clear / describe),
concepts, counting, verify, and the Gemma vision client. No GPU: the
vision-service tests run the REAL service, dispatcher and lock on a stand-in backend
(SAM3 itself is GPU-only)."""
import os
import sys
import threading
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from perception2 import vlm_client
from perception2.backend import DETECT_NOT_READY, DETECT_OK
from perception2.boxes import area, inside, intersection, iou
from perception2.concept import phrase_concepts
from perception2.counting import count_instances, median_count
from perception2.engine import PerceptionEngine, scale_vlm_box
from perception2.dispatcher import SUBMIT_FULL, SUBMIT_OK, Dispatcher
from perception2.sam3_lock import PRIORITY_COMMAND, PRIORITY_REFRESH, PriorityLock
from perception2 import vision as V
from support import CAR, GemmaStub, StandInBackend, state_of, wait_for
from perception2.verify import region_is_color, rel_holds, split_target, verify_highlight


# ==================== concept ====================
def test_phrase_concepts_live_path():
    """Attributes kept, article stripped, category expanded, empty guarded; relational
    and positional clauses SAM3 cannot use are dropped to the bare noun. (Moved here
    from concept.selftest 2026-09-24.)"""
    for phrase, want in (
        ("the red backpack", "red backpack"),
        ("all the vehicles", "car, van, truck, bus, motorcycle, scooter, bicycle"),
        ("person in the black hat", "person in the black hat"),
        ("people", "person"),
        ("", ""),
    ):
        assert phrase_concepts(phrase) == want, phrase

    assert phrase_concepts(
        "the man with glasses talking to the woman in the yellow shirt"
    ).startswith("man with glasses")
    assert phrase_concepts("window on the left") == "window"
    assert phrase_concepts("top left window") == "window"


def test_phrase_concepts_drops_relational_clauses_for_sam3():
    assert phrase_concepts(
        "the man with glasses talking to the woman in the yellow shirt"
    ).startswith("man with glasses")
    assert phrase_concepts(
        "the box next to the man standing on the roof"
    ).startswith("box")
    assert phrase_concepts("the red backpack") == phrase_concepts("red backpack")


def test_concepts_positional_and_synonyms():
    assert phrase_concepts("top left window") == "window"
    assert phrase_concepts("window panes") == "window"
    assert phrase_concepts("all screens") == "monitor, television, screen"
    assert phrase_concepts("the cabinets") == "cabinet, cupboard, wardrobe"


# ==================== counting ====================
def _d(conf, box):
    return {"conf": conf, "box": box}


def test_threshold_drops_low_conf():
    assert len(count_instances([
        _d(0.9, (0, 0, 100, 100)), _d(0.3, (200, 200, 300, 300))
    ])) == 1


def test_part_inside_whole_is_one_instance():
    whole = _d(0.93, (100, 100, 400, 500))
    back = _d(0.62, (120, 110, 380, 300))
    other = _d(0.7, (600, 100, 900, 500))
    kept = count_instances([back, whole, other])
    assert [k["box"] for k in kept] == [whole["box"], other["box"]]


def test_side_by_side_chairs_both_count():
    # 10 % overlap
    a = _d(0.9, (0, 0, 100, 100))
    b = _d(0.8, (90, 0, 190, 100))
    assert len(count_instances([a, b])) == 2


def test_zero_area_box_ignored():
    assert count_instances([_d(0.9, (5, 5, 5, 50))]) == []


def test_median_count():
    assert (
        median_count([2, 5, 4]) == 4
        and median_count([6, 1]) == 1
        and median_count([]) == 0
        and median_count([3]) == 3
    )


def test_speck_boxes_dropped_with_frame_area():
    # 100 px2 vs 90000 px2
    speck = _d(0.86, (10, 10, 20, 20))
    real = _d(0.7, (100, 100, 400, 400))
    kept = count_instances([speck, real], 0.5, frame_area=1280 * 720, min_frac=0.001)
    assert [k["box"] for k in kept] == [real["box"]]
    # no floor when frame_area is absent
    assert len(count_instances([speck, real], 0.5)) == 2


# ==================== engine ====================
# (moved here from engine.selftest 2026-09-24)
_FRAME = np.zeros((100, 100, 3), dtype=np.uint8)
_GOOD_MASK = np.zeros((100, 100), dtype=bool)
_GOOD_MASK[40:60, 40:60] = True
_GARBAGE_MASK = np.ones((100, 100), dtype=bool)


def _two_windows(frame, phrase, conf):
    return DETECT_OK, [
        {"label": phrase, "conf": 0.90, "box": (10, 10, 30, 30)},
        {"label": phrase, "conf": 0.48, "box": (50, 50, 70, 70)},
    ]


def _one_thing(frame, phrase, conf):
    return DETECT_OK, [{"label": phrase, "conf": 0.9, "box": (10, 10, 30, 30)}]


def _nothing(frame, phrase, conf):
    return DETECT_OK, []


def test_relative_gate_and_mask_hygiene():
    """0.48 dies next to 0.90; the kept box is tightened to its mask."""
    eng = PerceptionEngine(_two_windows, lambda f, b: _GOOD_MASK, None)
    dets, _masks, dbg = eng.highlight_step(_FRAME, "window")
    assert len(dets) == 1 and dbg["threshold"] >= 0.5
    assert dets[0]["box"] == (40, 40, 59, 59)


def test_a_garbage_mask_is_dropped_and_the_box_stays():
    eng = PerceptionEngine(_one_thing, lambda f, b: _GARBAGE_MASK, None)
    dets, masks, _ = eng.highlight_step(_FRAME, "thing")
    assert not masks and len(dets) == 1


def test_a_detector_whiff_falls_back_to_the_vlm_box():
    eng = PerceptionEngine(_nothing, lambda f, b: _GOOD_MASK, None)
    dets, masks, _ = eng.highlight_step(_FRAME, "cat", vlm_box_px=(35, 35, 65, 65))
    assert len(dets) == 1 and "(vlm)" in dets[0]["label"] and len(masks) == 1


def test_presence_gate_absent_and_box_scaling():
    """Absent -> (False, None); present with a 0-1000 box -> pixel coords."""
    no_reply = ("no", None, None, "no")
    absent = PerceptionEngine(None, None, lambda f, q, d: (True, no_reply))
    assert absent.presence_gate(_FRAME, "unicorn")[0] is False

    reply = ("yes", "cat", (500, 500, 1000, 1000), "yes")
    present = PerceptionEngine(None, None, lambda f, q, d: (True, reply))
    assert present.presence_gate(_FRAME, "cat") == (True, (50, 50, 100, 100))


def test_relative_gate_keeps_near_peers():
    frame = np.zeros((100, 100, 3), np.uint8)
    two_windows = [{"label": "window", "conf": 0.88, "box": (10, 10, 30, 30)},
                   {"label": "window", "conf": 0.85, "box": (50, 50, 70, 70)}]
    eng = PerceptionEngine(detect=lambda f, p, c: (DETECT_OK, two_windows),
                           mask_for_box=lambda f, b: None, vlm_ask=None)
    dets, masks, dbg = eng.highlight_step(frame, "window", use_sam=False)
    # peers within 65% of the top both survive
    assert len(dets) == 2


def test_full_frame_box_without_mask_is_dropped():
    frame = np.zeros((100, 100, 3), np.uint8)
    eng = PerceptionEngine(
        detect=lambda f, p, c: (
            DETECT_OK, [{"label": "x", "conf": 0.9, "box": (0, 0, 99, 99)}]
        ),
        mask_for_box=lambda f, b: None,
        vlm_ask=None
    )
    dets, masks, _ = eng.highlight_step(frame, "x")
    assert dets == [] and masks == []


def test_box_scaling_both_conventions():
    shape = (100, 200, 3)
    assert scale_vlm_box((0.5, 0.5, 1.0, 1.0), shape) == (100, 50, 200, 100)
    assert scale_vlm_box((500, 500, 1000, 1000), shape) == (100, 50, 200, 100)


def test_failed_detect_draws_nothing_and_reports_it():
    frame = np.zeros((100, 100, 3), np.uint8)
    eng = PerceptionEngine(
        detect=lambda f, p, c: (DETECT_NOT_READY, []),
        mask_for_box=lambda f, b: None,
        vlm_ask=None
    )
    dets, masks, dbg = eng.highlight_step(frame, "window")
    assert dets == [] and masks == [] and dbg["status"] == DETECT_NOT_READY


# ==================== verify ====================
def test_split_target_keeps_the_related_clause():
    t = split_target("man with glasses talking to woman in yellow shirt")
    assert t.head == "man with glasses" and t.relation == "near"
    assert (
        t.related[0].noun == "woman in yellow shirt" and t.related[0].color == "yellow"
    )
    t = split_target("backpack held by child with green shirt")
    assert (
        t.head == "backpack"
        and t.relation == "touch"
        and t.related[0].noun == "child with green shirt"
        and t.related[0].color == "green"
    )
    t = split_target("person standing on the roof of the white building")
    assert (
        t.head == "person"
        and t.relation == "on"
        and t.related[0].noun.startswith("roof")
    )
    # 'white' belongs to the building, not the roof
    assert t.related[0].color == ""
    assert (
        split_target("the chair").related == []
        and split_target("the chair").relation == "none"
    )


def test_rel_holds_geometry():
    roof = (100, 100, 500, 200)
    person_on = (250, 20, 300, 110)
    person_far = (250, 400, 300, 500)
    assert rel_holds("on", person_on, roof) and not rel_holds("on", person_far, roof)
    # sitting on = overlap, not bottom-on-top
    chair = (100, 230, 900, 720)
    sitter = (100, 0, 900, 720)
    assert rel_holds("on", sitter, chair)
    a = (0, 0, 100, 100)
    near = (110, 0, 200, 100)
    far = (900, 0, 1000, 100)
    assert rel_holds("near", a, near) and not rel_holds("near", a, far)
    # gap 40 > 25
    assert (
        rel_holds("touch", a, (90, 0, 150, 100))
        and not rel_holds("touch", a, (140, 0, 240, 100))
    )
    assert (
        rel_holds("in", (10, 10, 50, 50), a)
        and not rel_holds("in", (60, 60, 200, 200), a)
    )


def test_region_is_color():
    # BGR green
    fr = np.zeros((100, 100, 3), np.uint8)
    fr[:, :] = (0, 200, 0)
    assert (
        region_is_color(fr, (0, 0, 100, 100), "green")
        and not region_is_color(fr, (0, 0, 100, 100), "red")
    )


def _fake(dets_by_phrase):
    return lambda frame, phrase, floor: (DETECT_OK, list(dets_by_phrase.get(phrase, [])))


def test_verify_absent_related_noun_refuses():
    fr = np.zeros((720, 1280, 3), np.uint8)
    t = split_target("backpack held by child with green shirt")
    # no child anywhere
    det = _fake({
        "backpack": [{"label": "backpack", "conf": 0.9, "box": (100, 100, 300, 400)}]
    })
    v = verify_highlight(det, fr, t)
    assert v.verdict == "absent" and "child" in v.reason


def test_verify_draws_when_relation_holds_and_flags_misplaced():
    # everything green, so the color check passes
    fr = np.zeros((720, 1280, 3), np.uint8)
    fr[:, :] = (0, 200, 0)
    t = split_target("backpack held by child with green shirt")
    bp = {"label": "backpack", "conf": 0.9, "box": (100, 100, 300, 400)}
    child_near = {"label": "child", "conf": 0.8, "box": (280, 100, 500, 600)}
    child_far = {"label": "child", "conf": 0.8, "box": (900, 100, 1100, 600)}
    assert verify_highlight(
        _fake({"backpack": [bp], "child with green shirt": [child_near]}), fr, t
    ).verdict == "draw"
    assert verify_highlight(
        _fake({"backpack": [bp], "child with green shirt": [child_far]}), fr, t
    ).verdict == "misplaced"


def test_verify_simple_query_is_untouched():
    fr = np.zeros((720, 1280, 3), np.uint8)
    v = verify_highlight(
        _fake({"chair": [{"label": "chair", "conf": 0.9, "box": (100, 100, 300, 400)}]}),
        fr,
        split_target("the chair")
    )
    assert v.verdict == "draw" and v.reason == "simple"


def test_failed_sam3_call_is_a_failed_verdict_not_absent():
    fr = np.zeros((480, 640, 3), np.uint8)

    def failing(frame, phrase, floor):
        return DETECT_NOT_READY, []

    v = verify_highlight(failing, fr, split_target("the backpack held by the child"))
    # the app fails open on this; "absent" would veto the highlight
    assert v.verdict == "failed"


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
    class Failing(GemmaStub):
        def request(self, *args, **kwargs):
            return False, ""

    frame = np.zeros((16, 16, 3), np.uint8)
    assert vlm_client.ask(Failing(), frame, "what do you see", []) == (False, None)


def test_ask_parses_a_successful_reply(monkeypatch):
    reply = (
        "LONG RESPONSE: A red car.\n"
        "SHORT RESPONSE: A car.\n"
        "HIGHLIGHT: red car\n"
        "VLM_BOX: 0.1,0.1,0.5,0.5"
    )
    frame = np.zeros((16, 16, 3), np.uint8)
    ok, (long_, tgt, box, short) = vlm_client.ask(GemmaStub(reply), frame,
                                                  "highlight the red car", [])
    assert ok and tgt == "red car" and short == "A car." and box == (0.1, 0.1, 0.5, 0.5)


def test_presence_gate_fails_open_when_gemma_fails():
    eng = PerceptionEngine(
        detect=None, mask_for_box=None, vlm_ask=lambda f, q, d: (False, None)
    )
    assert eng.presence_gate(np.zeros((100, 100, 3), np.uint8), "cat") == (True, None)


# ==================== direct cases for the helpers ====================


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
    # the box stays, the garbage mask goes
    assert masks2 == [] and kept2 == [det]
    kept3, _ = eng2.apply_masks(
        frame, [{"label": "x", "conf": 0.9, "box": (0, 0, 99, 99)}]
    )
    # a full-frame box with no clean mask
    assert kept3 == []


# ==================== sam3_lock: the SAM3 priority lock ====================
def _wait_for(pred, timeout=3.0):
    return wait_for(pred, timeout)


def test_the_lock_serves_a_command_before_waiting_refreshes():
    lock = PriorityLock()
    order = []
    lock.acquire(PRIORITY_REFRESH)                     # busy: everyone else waits

    def waiter(name, priority):
        lock.acquire(priority)
        order.append(name)
        lock.release()

    threads = []
    for name, prio in (("refresh-1", PRIORITY_REFRESH), ("refresh-2", PRIORITY_REFRESH),
                       ("command", PRIORITY_COMMAND)):
        th = threading.Thread(target=waiter, args=(name, prio))
        th.start()
        threads.append(th)
        time.sleep(0.05)                               # a fixed arrival order
    lock.release()
    for th in threads:
        th.join(2)
    assert order == ["command", "refresh-1", "refresh-2"]   # priority, then arrival


# ==================== dispatcher: one thread per task ====================
def test_each_task_runs_on_its_own_thread():
    d = Dispatcher(max_tasks=8)
    names = []
    done = threading.Event()

    def task():
        names.append(threading.current_thread().name)
        if len(names) == 3:
            done.set()

    for i in range(3):
        assert d.submit(task, name=f"t{i}") == SUBMIT_OK
    assert done.wait(2)
    assert len(set(names)) == 3
    d.shutdown()


def test_a_sleeping_task_does_not_block_another():
    d = Dispatcher(max_tasks=8)
    finished = []
    d.submit(lambda: (time.sleep(0.5), finished.append("slow")))
    d.submit(lambda: finished.append("fast"))
    assert _wait_for(lambda: finished == ["fast"], 0.4)
    assert _wait_for(lambda: finished == ["fast", "slow"], 2)
    d.shutdown()


def test_past_max_tasks_a_submit_is_refused_not_queued():
    d = Dispatcher(max_tasks=2)
    release = threading.Event()
    assert d.submit(release.wait) == SUBMIT_OK
    assert d.submit(release.wait) == SUBMIT_OK
    assert d.submit(lambda: None) == SUBMIT_FULL
    release.set()
    assert _wait_for(lambda: d.alive() == 0)
    assert d.submit(lambda: None) == SUBMIT_OK
    d.shutdown()


# ============== vision: the REAL service on a stand-in backend ==============
class Recorder:
    """Records every vision callback in order."""

    def __init__(self):
        self.events = []

    def sinks(self):
        return V.Sinks(
            on_start=lambda task, kind, phrase: self.events.append(
                ("start", task, kind)),
            on_count=lambda task, st, n, phrase, counts: self.events.append(
                ("count", task, st, n)),
            on_highlight=lambda u: self.events.append(("hl", u.task, u.state, u)),
            on_describe=lambda task, ok, text, spoken, frame: self.events.append(
                ("describe", task, ok, spoken)),
            on_pass=lambda task, frame, dets, ms: self.events.append(("pass", task)))

    def states(self, task):
        return [e[2] for e in self.events if e[0] == "hl" and e[1] == task]


def _vision(monkeypatch, hits, delay=0.0, max_tasks=8, **cfg):
    settings = dict(COUNT_FRAMES=3, COUNT_GAP=0.05, SAM3_PERIOD=0.1, HL_GIVEUP=0.3,
                    GATE="sam3", VERIFY="off", MIN_BOX_FRAC=0.0)
    settings.update(cfg)
    for key, value in settings.items():
        monkeypatch.setattr(V.config, key, value)
    backend = StandInBackend(hits, delay)
    rec = Recorder()
    frame = np.zeros((100, 100, 3), np.uint8)
    gemma = GemmaStub("LONG RESPONSE: long answer\nSHORT RESPONSE: short\n"
                      "HIGHLIGHT: none")
    vision = V.Vision(backend, gemma, frame.copy, rec.sinks(), use_masks=lambda: False,
                      max_tasks=max_tasks)
    return vision, backend, rec


def test_count_is_the_median_then_it_highlights_what_it_counted(monkeypatch):
    vision, backend, rec = _vision(monkeypatch, {"car": CAR})
    status, task = vision.count("cars")
    assert status == V.TASK_OK
    assert _wait_for(lambda: V.HL_TRACKING in rec.states(task))
    assert ("count", task, V.TASK_OK, 2) in rec.events
    assert rec.events[0] == ("start", task, "count")
    vision.clear()
    assert _wait_for(lambda: rec.states(task)[-1] == V.HL_CLEARED)
    assert _wait_for(lambda: vision.alive() == 0)


def test_count_while_sam3_loads_is_not_ready_never_zero(monkeypatch):
    vision, backend, rec = _vision(monkeypatch, {"car": DETECT_NOT_READY})
    _, task = vision.count("car")
    assert _wait_for(lambda: ("count", task, V.TASK_NOT_READY, 0) in rec.events)


def test_an_absent_object_is_refused_with_the_reason(monkeypatch):
    vision, backend, rec = _vision(monkeypatch, {})
    _, task = vision.highlight("unicorn")
    assert _wait_for(lambda: rec.states(task) == [V.HL_ABSENT])
    update = [e[3] for e in rec.events if e[0] == "hl"][0]
    assert update.reason == "SAM3 found nothing"


def test_a_highlight_tracks_until_cleared_and_its_thread_ends(monkeypatch):
    vision, backend, rec = _vision(monkeypatch, {"car": CAR})
    _, task = vision.highlight("car")
    assert _wait_for(lambda: rec.states(task).count(V.HL_TRACKING) >= 3)
    first = [e[3] for e in rec.events if e[0] == "hl"][0]
    assert first.first and len(first.dets) == 2
    vision.clear()
    assert _wait_for(lambda: rec.states(task)[-1] == V.HL_CLEARED)
    assert _wait_for(lambda: vision.alive() == 0)


def test_a_highlight_gives_up_when_the_object_leaves(monkeypatch):
    hits = {"car": CAR}
    vision, backend, rec = _vision(monkeypatch, hits)
    _, task = vision.highlight("car")
    assert _wait_for(lambda: V.HL_TRACKING in rec.states(task))
    hits["car"] = []                                     # it left the frame
    assert _wait_for(lambda: rec.states(task)[-1] == V.HL_LOST, 3)
    assert _wait_for(lambda: vision.alive() == 0)


def test_a_new_highlight_replaces_the_old_one(monkeypatch):
    vision, backend, rec = _vision(monkeypatch, {"car": CAR, "person": CAR})
    _, old = vision.highlight("car")
    assert _wait_for(lambda: V.HL_TRACKING in rec.states(old))
    _, new = vision.highlight("person")
    assert _wait_for(lambda: rec.states(old)[-1] == V.HL_CLEARED)
    assert _wait_for(lambda: V.HL_TRACKING in rec.states(new))
    vision.clear()


def test_sam3_forward_passes_never_overlap(monkeypatch):
    vision, backend, rec = _vision(monkeypatch, {"car": CAR, "person": CAR}, delay=0.02)
    vision.highlight("car")
    vision.count("person")
    vision.count("car")
    assert _wait_for(lambda: len(backend.starts) >= 12, 5)
    assert backend.max_inside == 1                       # the SAM3 lock serializes them
    vision.clear()


def test_past_the_cap_a_request_is_full(monkeypatch):
    vision, backend, rec = _vision(monkeypatch, {"car": CAR}, max_tasks=1)
    _, task = vision.highlight("car")
    assert _wait_for(lambda: V.HL_TRACKING in rec.states(task))
    assert vision.count("car")[0] == V.TASK_FULL
    vision.clear()


def test_the_refresh_period_counts_from_the_start_of_each_detect(monkeypatch):
    """Period 0.2 s, one detect 0.08 s: starts come 0.2 s apart, not 0.28 s."""
    vision, backend, rec = _vision(monkeypatch, {"car": CAR}, delay=0.08,
                                   SAM3_PERIOD=0.2)
    vision.highlight("car")
    assert _wait_for(lambda: len(backend.starts) >= 6, 5)
    vision.clear()
    gaps = [b - a for a, b in zip(backend.starts[1:], backend.starts[2:])]   # refreshes
    assert sum(gaps) / len(gaps) < 0.24


def test_describe_answers_through_its_callback(monkeypatch):
    vision, backend, rec = _vision(monkeypatch, {})
    _, task = vision.describe("מה אתה רואה")
    assert _wait_for(lambda: ("describe", task, True, "short") in rec.events)


def test_every_forward_pass_is_reported_with_its_task(monkeypatch):
    vision, backend, rec = _vision(monkeypatch, {"car": CAR})
    _, task = vision.count("car")
    assert _wait_for(lambda: ("count", task, V.TASK_OK, 2) in rec.events)
    assert [e for e in rec.events if e[0] == "pass"][:3] == [("pass", task)] * 3
    vision.clear()


def test_the_backend_loader_is_not_ready_until_loaded():
    from perception2.backend import BackendLoader
    release = threading.Event()

    def slow_model():
        release.wait(2)
        return type("M", (), {"detect": lambda self, f, p, conf, topk: (DETECT_OK, CAR),
                              "mask_for_box": lambda self, f, b: "mask"})()

    loader = BackendLoader("sam3", loader=slow_model)
    assert loader.detect(None, "car", 0.1) == (DETECT_NOT_READY, [])
    assert state_of(loader) == "STARTING"
    release.set()
    loader.thread.join(2)
    assert state_of(loader) == "UP" and loader.detect(None, "car", 0.1)[1] == CAR
    assert loader.mask_for_box(None, (1, 2, 3, 4)) == "mask"


def test_boxes_overlap_math():
    """The one home of the box overlap math: exact values, not just "overlaps"."""
    a = (0, 0, 10, 10)
    b = (5, 0, 15, 10)
    assert area(a) == 100 and area((10, 10, 0, 0)) == 0
    assert intersection(a, b) == 50
    assert iou(a, b) == 50 / 150
    assert inside(a, b) == 0.5
    assert inside((2, 2, 4, 4), a) == 1.0
    far = (20, 20, 30, 30)
    assert intersection(a, far) == 0 and iou(a, far) == 0.0 and inside(a, far) == 0.0


# ==================== the real SAM3 (GPU; opt-in) ====================
@pytest.mark.skipif(
    os.environ.get("HARDEN2_GPU_TESTS") != "1",
    reason="loads the real SAM3 model on the GPU: set HARDEN2_GPU_TESTS=1"
)
def test_real_sam3_detects_and_masks_a_window():
    """The real backend on a real picture: detect finds windows, and mask_for_box
    returns the frame-sized mask it cached. (Moved here from sam3_backend._smoke
    2026-09-24.)"""
    import cv2
    from perception2.sam3_backend import Sam3Backend

    frame = cv2.imread(
        "/root/groundstation/bench/vision-verify-bench/dataset/images/img0.png"
    )
    assert frame is not None
    backend = Sam3Backend()
    status, dets = backend.detect(frame, "window", conf=0.30)
    assert status == DETECT_OK and dets

    mask = backend.mask_for_box(frame, dets[0]["box"])
    assert mask is not None and mask.shape[:2] == frame.shape[:2]
