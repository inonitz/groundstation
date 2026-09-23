"""Tests for mvd.py: the app assembly. The vision flow (the ONE SAM3 consumer runs the gate, count,
clear and highlight refresh), the router and Pipeline wiring, the backend wrapper, and the capture hooks
that write the session log. Engines, backends, the wire and Gemma are fakes; the queue is real."""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from perception2.backend import DETECT_OK
from perception2.task_queue import TaskQueue
from control.router import Router
from recognizer import Pipeline
import mvd as M
from mvd import TextHandler


def _session():
    d = tempfile.mkdtemp()
    os.environ["MVD_SESSION_DIR"] = d
    return d, M.SessionLog()


# ---------------- the vision flow: one SAM3 consumer ----------------
HIT = {"label": "chair", "conf": 0.9, "box": (10, 10, 60, 60)}


class FakeEngine:
    """Stands in for PerceptionEngine. `hits` is what SAM3 'sees' right now; tests change it."""
    def __init__(self, hits):
        self.hits = list(hits)
        self.threads = set()
        self.steps = 0

    def detect(self, frame, phrase, floor):
        self.threads.add(threading.get_ident())
        return DETECT_OK, list(self.hits)

    def highlight_step(self, frame, target, vlm_box_px=None, use_sam=True):
        self.threads.add(threading.get_ident())
        self.steps += 1
        return list(self.hits), [], {}


def _wait_for(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def vision(monkeypatch):
    monkeypatch.setattr(M, "GATE", "sam3")
    monkeypatch.setattr(M, "VERIFY", "off")
    monkeypatch.setattr(M, "SAM3_PERIOD", 0.05)
    monkeypatch.setattr(M, "HL_GIVEUP", 0.2)
    monkeypatch.setattr(M, "COUNT_GAP", 0.0)
    monkeypatch.setattr(M, "SESSION", None)
    eng = FakeEngine([HIT])
    M.ENGINE["e"] = eng
    M.VISION["q"] = TaskQueue(max_active=8)
    with M.S.lock:
        M.S.frame = np.zeros((100, 100, 3), np.uint8)
        M.S.target = None
        M.S.hl_dets, M.S.hl_masks = [], []
        M.S.chat.clear()
    yield eng, M.TextHandler(None, voice=None)
    M.VISION["q"].shutdown()
    M.ENGINE["e"] = None
    M.VISION["q"] = None


def test_gate_present_starts_a_refresh_loop(vision):
    eng, th = vision
    th.perceive("highlight the chair")
    assert _wait_for(lambda: M.S.target == "chair" and M.S.hl_dets)
    assert _wait_for(lambda: eng.steps >= 3)          # the refresh reschedules itself


def test_gate_absent_draws_nothing(vision):
    eng, th = vision
    eng.hits = []
    th.perceive("highlight the chair")
    assert _wait_for(lambda: any("in view" in c[1] for c in M.S.chat))
    assert M.S.target is None and eng.steps == 0


def test_clear_stops_the_refresh_loop(vision):
    eng, th = vision
    th.perceive("highlight the chair")
    assert _wait_for(lambda: eng.steps >= 2)
    th.perceive("clear")
    assert _wait_for(lambda: M.S.target is None and not M.S.hl_dets)
    frozen = eng.steps
    time.sleep(0.3)
    assert eng.steps == frozen and M.VISION["q"].pending() == 0


def test_highlight_gives_up_when_sam3_loses_it(vision):
    eng, th = vision
    th.perceive("highlight the chair")
    assert _wait_for(lambda: M.S.target == "chair")
    eng.hits = []
    assert _wait_for(lambda: M.S.target is None)
    assert any("לא מצאתי" in c[1] for c in M.S.chat)


def test_count_is_one_shot_and_highlights_what_it_counted(vision):
    eng, th = vision
    th.perceive("count the chairs")
    assert _wait_for(lambda: any("ספרתי 1" in c[1] for c in M.S.chat))
    assert _wait_for(lambda: M.S.target is not None)


def test_all_sam3_work_runs_on_one_thread_that_is_not_the_caller(vision):
    eng, th = vision
    th.perceive("highlight the chair")
    th.perceive("count the chairs")
    assert _wait_for(lambda: eng.steps >= 3)
    assert len(eng.threads) == 1 and threading.get_ident() not in eng.threads


def test_full_queue_is_reported_not_queued(vision):
    eng, th = vision
    M.VISION["q"].shutdown()
    M.VISION["q"] = TaskQueue(max_active=0)
    th.perceive("highlight the chair")
    assert any("Too many vision tasks" in c[1] for c in M.S.chat)



# ---------------- router + Pipeline wiring ----------------
class FakeWire:
    def __init__(self):
        self.missions = []
        self.halts = 0

    def fly_mission(self, steps):
        self.missions.append(steps)

    def halt(self):
        self.halts += 1
        return 200


def build(plan2=None, with_router=True):
    """Mirror mvd.main()'s ruled wiring, with the Gemma call faked by plan2. seen[] records the
    Pipeline's vlm_query (= TextHandler.perceive); said[] records the Pipeline's say."""
    M.S.chat.clear()
    wire = FakeWire()
    seen, said = [], []
    on_text = TextHandler(None, voice=None)
    on_text.perceive = seen.append              # observe perception routing (patched before pipe)
    if not with_router:
        return on_text, wire, seen, said
    pipe = Pipeline(wire, vlm_query=on_text.perceive, say=said.append,
                    plan2_fn=plan2 or (lambda he: None), trace_dir="/tmp/scene-wiring-traces")
    on_text.router = Router(wire, on_complex=pipe.handle)
    return on_text, wire, seen, said


def test_complex_perception_routes_to_perceive():
    on_text, wire, seen, said = build(plan2=lambda he: {"kind": "highlight", "target_en": "white car", "mission": []})
    on_text("סמן את המכונית הלבנה ליד העץ")
    assert len(seen) == 1 and seen[0].startswith("highlight the")   # reached perceive exactly once
    assert wire.missions == []


def test_hebrew_command_flies_via_pipeline():
    on_text, wire, seen, said = build(plan2=lambda he: {"kind": "mission", "target_en": "", "mission": [{"type": "fly_by", "dx": 5}]})
    on_text("טוס קדימה חמישה מטרים בזהירות רבה")
    assert wire.missions == [[{"type": "fly_by", "dx": 5}]] and seen == []


def test_mission_bypass_flies_without_models():
    on_text, wire, seen, said = build()             # plan2 returns None: a model call would show as no flight
    on_text("עלה עשרה מטרים")
    assert wire.missions == [[{"type": "fly_by", "dz": 10.0}]] and seen == []


def test_reject_is_spoken_not_perceived():
    on_text, wire, seen, said = build(plan2=lambda he: {"kind": "reject", "target_en": "", "mission": []})
    on_text("מה הגובה שלך עכשיו")
    assert said and said[0].startswith(Pipeline.REJECT_HE)
    assert wire.missions == [] and seen == []


def test_emergency_halts_via_router_not_pipeline():
    on_text, wire, seen, said = build()
    on_text("עצור")
    assert wire.halts == 1                              # router tier-4 halt, not the Pipeline backup
    assert seen == [] and wire.missions == []
    assert any(r[0] == "model" and r[1] == "[drone] stop" for r in M.S.chat)


def test_no_router_falls_through_to_perceive():
    on_text, wire, seen, said = build(with_router=False)
    on_text("what do you see")
    assert seen == ["what do you see"]                  # no router -> perceive runs directly


class FakeBackend:
    """Stands in for the SAM3 backend: one detect, one cached mask."""
    def __init__(self):
        self.calls = 0

    def detect(self, frame, phrase, conf=0.3, topk=8):
        self.calls += 1
        return DETECT_OK, [{"label": phrase, "conf": 0.9, "box": (1, 2, 3, 4)}]

    def mask_for_box(self, frame, box):
        return "mask" if box == (1, 2, 3, 4) else None


def test_build_highlight_sam3_one_model_serves_both_callables():
    M.OM["det"] = None
    fake = FakeBackend()
    detect, mask_for_box, th = M.build_highlight("sam3", loader=lambda: fake)
    th.join(5)
    status, hits = detect(None, "car", 0.12)
    assert status == DETECT_OK and hits[0]["box"] == (1, 2, 3, 4)
    assert mask_for_box(None, (1, 2, 3, 4)) == "mask"      # the mask comes from the SAME model
    detect(None, "car", 0.12)
    assert fake.calls == 2          # every call is a real forward; the vision queue paces the refresh (R8)
    M.OM["det"] = None


def test_build_highlight_rejects_unknown_backend():
    # unknown backend -> die() (a hard crash, not an exception). Check the child process crashes loudly.
    here = os.path.dirname(__file__)
    code = ("import sys, os;"
            "sys.path.insert(0, os.path.join(%r, '..'));"
            "sys.path.insert(0, os.path.join(%r, '..', 'recognizer'));"
            "import mvd as scene;"
            "scene.build_highlight('yoloe')" % (here, here))
    r = subprocess.run([sys.executable, "-c", code],
                       env={**os.environ, "MVD_HOME": "integration_harden2", "MVD_TRANSLATOR": "none"},
                       capture_output=True, text=True)
    assert r.returncode != 0, "unknown SCENE_SEG must crash"
    assert "no vision backend" in r.stderr, r.stderr



# ---------------- capture hooks into the session log ----------------
def test_detect_hook_saves_one_pass_per_forward():
    d, log = _session(); M.SESSION = log
    log.begin("סמן גיטרה"); log.begin_request("highlight", "guitar")
    M.OM["det"] = None
    detect, _mask, th = M.build_highlight("sam3", loader=FakeBackend); th.join(5)
    fr = np.zeros((16, 16, 3), np.uint8)
    detect(fr, "guitar", 0.1)
    detect(fr, "guitar", 0.1)                 # no phrase cache any more (R8): a second forward, a second pass
    rd = glob.glob(os.path.join(d, "perception", "0000-highlight-guitar"))[0]
    assert len(glob.glob(os.path.join(rd, "pass_*.jpg"))) == 2, os.listdir(rd)
    M.OM["det"] = None; M.SESSION = None
    shutil.rmtree(d, ignore_errors=True)


def test_ask_thread_saves_gemma_pass_and_closes(monkeypatch):
    d, log = _session(); M.SESSION = log
    monkeypatch.setattr(M.vlm, "ask", lambda fr, q, h: (True, ("a room with chairs", None, None, "a room")))   # restored after the test
    log.begin("מה אתה רואה"); log.begin_request("describe", "what do you see", query="what do you see")
    M.TextHandler(None, voice=None)._ask_thread(np.zeros((16, 16, 3), np.uint8), "what do you see")
    rd = glob.glob(os.path.join(d, "perception", "0000-describe-*"))[0]
    assert os.path.isfile(os.path.join(rd, "pass_00000.jpg"))
    assert json.load(open(os.path.join(rd, "pass_00000.json")))["answer"] == "a room with chairs"
    assert json.load(open(os.path.join(rd, "request.json")))["verdict"]["spoken"] == "a room"
    M.SESSION = None; shutil.rmtree(d, ignore_errors=True)



def test_failed_gemma_answer_adds_no_chat_line(monkeypatch):
    monkeypatch.setattr(M, "SESSION", None)
    monkeypatch.setattr(M.vlm, "ask", lambda fr, q, h: (False, None))
    M.S.chat.clear()
    M.S.thinking = True
    M.TextHandler(None, voice=None)._ask_thread(np.zeros((16, 16, 3), np.uint8), "what do you see")
    assert list(M.S.chat) == [] and M.S.thinking is False


def test_layout_camera_on_top_status_and_chat_below(monkeypatch):
    monkeypatch.setattr(M, "SESSION", None)
    disp = np.zeros((720, 1280, 3), np.uint8)
    canvas = M.compose_canvas(disp, 30.0, "webcam", "mock")
    assert canvas.shape == (720 + M.config.BOTTOM_H, 1280, 3)
    assert np.array_equal(canvas[:720, :, :][400:500, 400:500], disp[400:500, 400:500])   # camera untouched below the HUD


def test_scroll_keys_move_the_chat_and_never_go_below_zero():
    M.S.chat_scroll = 0
    M.handle_key(ord("["))
    M.handle_key(ord("["))
    assert M.S.chat_scroll == 6
    for _ in range(5):
        M.handle_key(ord("]"))
    assert M.S.chat_scroll == 0


# ==================== mvd helpers (all cases) ====================
def test_source_label_for_every_source_kind():
    assert M.source_label("0") == "webcam 0"
    assert M.source_label("rtsp://10.0.0.1:8554/live") == "rtsp://10.0.0.1:8554"
    assert M.source_label("/data/clip.mp4") == "clip.mp4"


def test_wire_label_says_mock_or_real(monkeypatch):
    monkeypatch.setattr(M.config, "WIRE_HOST", "127.0.0.1")
    monkeypatch.setattr(M.config, "WIRE_PORT", 8079)
    monkeypatch.setattr(M.config, "WIRE_REAL", False)
    assert M.wire_label() == "mock 127.0.0.1:8079"
    monkeypatch.setattr(M.config, "WIRE_REAL", True)
    assert M.wire_label().startswith("REAL ")


def test_draw_overlays_tints_the_mask_only_when_masks_are_on():
    disp = np.zeros((20, 20, 3), np.uint8)
    mask = np.zeros((20, 20), bool)
    mask[5:10, 5:10] = True
    M.draw_overlays(disp, [], [mask], use_sam=True)
    assert disp[7, 7].any() and not disp[15, 15].any()
    off = np.zeros((20, 20, 3), np.uint8)
    M.draw_overlays(off, [], [mask], use_sam=False)
    assert not off.any()


def test_a_source_that_never_opens_returns_none(monkeypatch):
    monkeypatch.setattr(M.config, "OPEN_TIMEOUT", 0.0)
    assert M.open_source_with_retry("/nonexistent/clip.mp4") is None


def test_parse_source_reads_the_one_argument(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["mvd.py", "--source", "3"])
    assert M.parse_source() == "3"


def test_mouse_wheel_scrolls_the_chat():
    M.S.chat_scroll = 0
    M.on_mouse(M.cv2.EVENT_MOUSEWHEEL, 0, 0, 120 << 16, None)       # wheel up
    assert M.S.chat_scroll == 3
    M.on_mouse(M.cv2.EVENT_MOUSEWHEEL, 0, 0, -120 << 16, None)      # wheel down
    assert M.S.chat_scroll == 0
    M.on_mouse(M.cv2.EVENT_LBUTTONDOWN, 0, 0, 0, None)              # other events do nothing
    assert M.S.chat_scroll == 0



def test_sam3_not_ready_is_never_absent_and_keeps_the_highlight(vision, monkeypatch):
    """R22 + R23: while SAM3 loads, a gate or a count says 'not ready' -- never 'absent' or 'counted 0' --
    and a live highlight stays."""
    from perception2.backend import DETECT_NOT_READY
    eng, th = vision
    th.perceive("highlight the chair")
    assert _wait_for(lambda: M.S.target == "chair")
    monkeypatch.setattr(eng, "detect", lambda f, p, c: (DETECT_NOT_READY, []))
    th.perceive("highlight the table")
    th.perceive("count the chairs")
    assert _wait_for(lambda: sum("not ready" in c[1] for c in M.S.chat) == 2)
    assert M.S.target == "chair"
    assert not any("in view" in c[1] or "ספרתי 0" in c[1] for c in M.S.chat)


def test_a_phone_transcript_is_recorded_as_phone(monkeypatch, tmp_path):
    """R27: the transcript's source travels to the session log."""
    monkeypatch.setenv("MVD_SESSION_DIR", str(tmp_path))
    log = M.SessionLog()
    monkeypatch.setattr(M, "SESSION", log)
    seen = []
    monkeypatch.setattr(log, "begin", lambda text, source="mic": seen.append(source))
    handler = M.TextHandler(None, voice=None)
    monkeypatch.setattr(handler, "perceive", lambda text: None)
    handler("hello", "phone")
    handler("hello again")
    assert seen == ["phone", "mic"]
