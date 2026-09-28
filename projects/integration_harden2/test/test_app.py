"""Tests for the app module (app/): the global kill key over a REAL ROS2 topic
(keys.py), the app assembly and its vision flow (main.py), the screen helpers (ui.py),
and the status and chat panes (status_pane.py, chat_pane.py)."""
import glob
import json
import os
import signal
import subprocess
import sys
import time

import numpy as np
import pytest
import rclpy
from std_msgs.msg import Int32MultiArray, String

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from recognizer import Recognizer
import app.main as M
from app import ui as U
from app.keys import Keys
from app.turns import Turns, VisionSinks
from log.session import SessionLog
from perception2.backend import DETECT_NOT_READY
from control.flight import Control
from perception2.vision import Vision
from app.chat_pane import render_chat
from app.status_pane import render_status
from system.status import StatusBoard
from support import CAR, GemmaStub, RecordingPhone, StandInBackend, PlannerStub, wait_for


# ==================== keys.py: the global kill key ====================
def _publish(events):
    """Publish each [code, action] pair from a separate node, as
    the keyboard hook does."""
    node = rclpy.create_node("test_keyboard_hook")
    pub = node.create_publisher(Int32MultiArray, config.KEYBOARD_RAW_TOPIC, 10)
    deadline = time.time() + 5.0
    while pub.get_subscription_count() == 0 and time.time() < deadline:
        time.sleep(0.05)
    for data in events:
        msg = Int32MultiArray()
        msg.data = list(data)
        pub.publish(msg)
    time.sleep(0.5)
    node.destroy_node()
    return


def _run(events):
    """-> the key codes Keys reported for these key events."""
    codes = []
    keys = Keys(on_key=codes.append)
    _publish(events)
    keys.close()
    return codes


def test_a_press_is_reported_once():
    press = [config.KILL_KEY_CODE, config.KEY_ACTION_PRESSED]
    assert _run([press]) == [config.KILL_KEY_CODE]


def test_release_and_repeat_are_not_reported():
    # holding F4: press, auto-repeat x2, release -> exactly one report
    events = [
        [config.KILL_KEY_CODE, 1],
        [config.KILL_KEY_CODE, 2],
        [config.KILL_KEY_CODE, 2],
        [config.KILL_KEY_CODE, 0],
    ]
    assert _run(events) == [config.KILL_KEY_CODE]


def test_keys_reports_every_key_and_knows_nothing_about_the_drone():
    # evdev KEY_M = 50, KEY_Q = 16, KEY_C = 46
    assert _run([[50, 1], [16, 1], [46, 1]]) == [50, 16, 46]


def test_short_message_is_ignored():
    assert _run([[config.KILL_KEY_CODE]]) == []


def test_only_function_keys_act_and_letters_never_do():
    """The app's key handler: F4 toggles manual, F1 quits, F2 clears the highlight; a
    letter (typed in another window) does nothing, Q included (owner 2026-09-23: "Use the
    function keys")."""
    phone = RecordingPhone()
    said = []
    quits = []
    clears = []

    def press(code):
        M.on_global_key(
            code,
            phone.control,
            said.append,
            lambda: quits.append(code),
            lambda: clears.append(code)
        )
        return

    for letter in (50, 16, 46):                 # M, Q, C
        press(letter)
    assert phone.seen == [] and said == [] and quits == [] and clears == []
    press(config.QUIT_KEY_CODE)
    press(config.CLEAR_KEY_CODE)
    assert quits == [config.QUIT_KEY_CODE] and clears == [config.CLEAR_KEY_CODE]
    assert phone.seen == [] and said == []
    press(config.KILL_KEY_CODE)
    assert phone.paths() == ["/c/stop"] and "the RC has control" in said[0]
    press(config.KILL_KEY_CODE)
    assert not phone.control.manual_on() and said[1].startswith("auto")
    phone.close()


def test_every_global_key_is_a_distinct_function_key():
    assert config.KILL_KEY_CODE == 62          # evdev KEY_F4
    assert config.QUIT_KEY_CODE == 59          # evdev KEY_F1
    assert config.CLEAR_KEY_CODE == 60         # evdev KEY_F2
    codes = [
        config.KILL_KEY_CODE,
        config.QUIT_KEY_CODE,
        config.CLEAR_KEY_CODE,
        config.PUSH_TO_TALK_KEY_CODE,
    ]
    assert len(set(codes)) == len(codes)


# ==================== turns.py: a turn, and the vision results ====================
def _session(tmp_path, monkeypatch):
    return SessionLog(str(tmp_path))


def _wait_for(pred, timeout=3.0):
    return wait_for(pred, timeout)


def _app(tmp_path, monkeypatch, hits, plan2=None):
    """The app's wiring (as app.main builds it) over the REAL control + phone-app client
    against a REAL local HTTP server, the REAL vision service on a stand-in SAM3, and the
    REAL session log. Gemma's plan is faked by plan2.
    -> (turns, phone, vision, spoken)."""
    settings = dict(COUNT_FRAMES=3, COUNT_GAP=0.02, SAM3_PERIOD=0.05, HL_GIVEUP=0.3,
                    GATE="sam3", VERIFY="off", MIN_BOX_FRAC=0.0)
    for key, value in settings.items():
        monkeypatch.setattr(config, key, value)
    M.S.chat.clear()
    frame = np.zeros((100, 100, 3), np.uint8)
    session = _session(tmp_path, monkeypatch)
    spoken = []
    sinks = VisionSinks(session, spoken.append)
    gemma = GemmaStub()
    vision = Vision(StandInBackend(hits), gemma, frame.copy, sinks.sinks(),
                    use_masks=lambda: False)
    phone = RecordingPhone()
    control = Control(phone.dji, session)
    planner = PlannerStub(plan2 or (lambda he: None))
    pipeline = Recognizer(control, vision, planner, session)

    def say(text):
        M.S.chat.append(("model", text, "x"))
        spoken.append(text)

    turns = Turns(pipeline, say=say, session=session)
    return turns, phone, vision, spoken


def _chat():
    return [c[1] for c in M.S.chat]


def test_a_highlight_turn_draws_and_logs_it(tmp_path, monkeypatch):
    turns, phone, vision, spoken = _app(
        tmp_path, monkeypatch, {"car": CAR},
        plan2=lambda he: {"kind": "highlight", "target_en": "car", "mission": []})
    turns("סמן את המכונית")
    assert _wait_for(lambda: len(M.S.hl_dets) == 2)
    assert "Highlighting: car" in _chat() and phone.seen == []
    vision.clear()
    assert _wait_for(lambda: "Cleared the highlight." in _chat())
    assert M.S.hl_dets == []
    req = json.load(open(glob.glob(str(tmp_path / "perception" / "*highlight*" /
                                       "request.json"))[0]))
    assert req["verdict"] == "cleared" and req["passes"] >= 2
    phone.close()


def test_a_count_turn_says_the_number(tmp_path, monkeypatch):
    turns, phone, vision, spoken = _app(
        tmp_path, monkeypatch, {"car": CAR},
        plan2=lambda he: {"kind": "count", "target_en": "cars", "mission": []})
    turns("כמה מכוניות יש")
    assert _wait_for(lambda: "ספרתי 2: cars" in _chat())
    assert "יש 2" in spoken
    vision.clear()
    phone.close()


def test_sam3_not_ready_is_never_absent_and_keeps_the_highlight(tmp_path, monkeypatch):
    """R22 + R23: while SAM3 loads, a gate or a count says 'not ready' -- never 'absent'
    or 'counted 0' -- and a live highlight stays."""
    hits = {"car": CAR}
    plans = {"סמן": {"kind": "highlight", "target_en": "car", "mission": []},
             "כמה": {"kind": "count", "target_en": "cars", "mission": []}}
    turns, phone, vision, spoken = _app(tmp_path, monkeypatch, hits,
                                        plan2=lambda he: plans[he.split()[0]])
    turns("סמן את המכונית")
    assert _wait_for(lambda: len(M.S.hl_dets) == 2)
    hits["car"] = DETECT_NOT_READY
    turns("כמה מכוניות יש")
    assert _wait_for(lambda: any("not ready" in c for c in _chat()))
    assert not any("ספרתי 0" in c or "in view" in c for c in _chat())
    assert M.S.target is not None                   # the live highlight stays
    vision.clear()
    phone.close()


def test_an_absent_object_is_said_with_the_reason(tmp_path, monkeypatch):
    turns, phone, vision, spoken = _app(
        tmp_path, monkeypatch, {},
        plan2=lambda he: {"kind": "highlight", "target_en": "unicorn", "mission": []})
    turns("סמן חד קרן")
    assert _wait_for(lambda: any("in view -- SAM3 found nothing" in c for c in _chat()))
    phone.close()


def test_a_describe_turn_shows_and_speaks_the_short_answer(tmp_path, monkeypatch):
    turns, phone, vision, spoken = _app(
        tmp_path, monkeypatch, {},
        plan2=lambda he: {"kind": "describe", "target_en": "", "mission": []})
    turns("מה אתה רואה")
    assert _wait_for(lambda: "room" in spoken)
    assert "a room" in _chat()
    phone.close()


def test_a_mission_turn_flies_and_lists_the_steps(tmp_path, monkeypatch):
    turns, phone, vision, spoken = _app(
        tmp_path, monkeypatch, {},
        plan2=lambda he: {"kind": "mission", "target_en": "",
                          "mission": [{"type": "fly_by", "dx": 5}]})
    turns("טוס קדימה חמישה מטרים בזהירות")
    assert phone.seen == [("/c/fly", [{"type": "fly_by", "dx": 5}])]
    assert "fly_by dx=5" in " ".join(_chat())
    phone.close()


def test_an_emergency_turn_is_spoken(tmp_path, monkeypatch):
    turns, phone, vision, spoken = _app(tmp_path, monkeypatch, {})
    turns("עצור")
    assert phone.seen == [("/c/fly", [{"type": "delay", "seconds": 0.0}])]
    assert spoken and spoken[0].startswith("emergency stop: sent")
    phone.close()


def test_a_phone_transcript_is_recorded_as_phone(tmp_path, monkeypatch):
    """R27: the transcript's source travels to the session log."""
    turns, phone, vision, spoken = _app(tmp_path, monkeypatch, {})
    seen = []
    monkeypatch.setattr(turns.session, "begin",
                        lambda text, source="mic": seen.append(source))
    monkeypatch.setattr(turns.session, "current", lambda: None)
    turns("שלום", "phone")
    turns("שלום שוב")
    assert seen == ["phone", "mic"]
    phone.close()


def test_a_full_vision_service_closes_the_refused_record(tmp_path, monkeypatch):
    turns, phone, vision, spoken = _app(
        tmp_path, monkeypatch, {"car": CAR},
        plan2=lambda he: {"kind": "highlight", "target_en": "car", "mission": []})
    monkeypatch.setattr(vision._dispatch, "mk_maxTasks", 1)
    turns("סמן את המכונית")
    assert _wait_for(lambda: len(M.S.hl_dets) == 2)
    turns("סמן את המכונית")
    assert any("Too many vision tasks" in c for c in _chat())
    refused = [json.load(open(f)) for f in glob.glob(str(tmp_path / "perception" / "*" /
                                                           "request.json"))]
    assert any(r["verdict"] == "refused: too many vision tasks" for r in refused)
    vision.clear()
    phone.close()


# ==================== ui.py and main.py helpers ====================
def test_layout_camera_on_top_status_and_chat_below():
    disp = np.zeros((720, 1280, 3), np.uint8)
    canvas = U.compose_canvas(
        disp,
        30.0,
        "webcam",
        "mock",
        None,
        StatusBoard([]),
        False
    )
    assert canvas.shape == (720 + config.BOTTOM_H, 1280, 3)
    # camera untouched below the HUD
    assert np.array_equal(canvas[:720, :, :][400:500, 400:500], disp[400:500, 400:500])


class _RecordingPerf:
    def __init__(self):
        self.rows = []

    def record(self, stage, ms, **fields):
        self.rows.append(dict(fields, stage=stage, ms=ms))
        return


def test_the_frame_record_keeps_the_worst_frame_of_each_second(monkeypatch):
    clock = iter([0.0, 0.1, 0.2, 0.6, 1.0])
    monkeypatch.setattr(U.time, "monotonic", lambda: next(clock))
    perf = _RecordingPerf()
    timer = U._FrameTimer(perf)
    timer.add(0.01, 0.02, 0.01)
    timer.add(0.01, 0.02, 0.01)
    timer.add(0.30, 0.02, 0.05)                 # one slow read, then a 400 ms gap
    timer.add(0.01, 0.02, 0.01)
    row = perf.rows[0]
    assert row["stage"] == "frame" and row["fps"] == 4.0
    assert row["read_max_ms"] == 300.0 and row["show_max_ms"] == 50.0
    assert row["worst_frame_ms"] == 400.0
    assert row["read_ms"] == 82.5                   # the mean hides the slow frame


def test_scroll_keys_move_the_chat_and_never_go_below_zero():
    M.S.chat_scroll = 0
    U.handle_key(ord("["), on_clear=lambda: None)
    U.handle_key(ord("["), on_clear=lambda: None)
    assert M.S.chat_scroll == 6
    for _ in range(5):
        U.handle_key(ord("]"), on_clear=lambda: None)
    assert M.S.chat_scroll == 0


def test_the_c_key_clears_through_the_given_function():
    cleared = []
    U.handle_key(ord("c"), on_clear=lambda: cleared.append(1))
    assert cleared == [1]


def test_source_label_for_every_source_kind():
    assert U.source_label("0") == "webcam 0"
    assert U.source_label("rtsp://10.0.0.1:8554/live") == "rtsp://10.0.0.1:8554"
    assert U.source_label("/data/clip.mp4") == "clip.mp4"


def test_dji_label_says_mock_or_real(monkeypatch):
    monkeypatch.setattr(config, "DJI_HOST", "127.0.0.1")
    monkeypatch.setattr(config, "DJI_PORT", 8079)
    monkeypatch.setattr(config, "DJI_REAL", False)
    assert U.dji_label() == "mock 127.0.0.1:8079"
    monkeypatch.setattr(config, "DJI_REAL", True)
    assert U.dji_label().startswith("REAL ")


def test_draw_overlays_tints_the_mask_only_when_masks_are_on():
    disp = np.zeros((20, 20, 3), np.uint8)
    mask = np.zeros((20, 20), bool)
    mask[5:10, 5:10] = True
    U.draw_overlays(disp, [], [mask], use_masks=True)
    assert disp[7, 7].any() and not disp[15, 15].any()
    off = np.zeros((20, 20, 3), np.uint8)
    U.draw_overlays(off, [], [mask], use_masks=False)
    assert not off.any()


def test_parse_source_reads_the_one_argument(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["app/main.py", "--source", "3"])
    assert M.parse_source() == "3"


def test_mouse_wheel_scrolls_the_chat():
    M.S.chat_scroll = 0
    U.on_mouse(U.cv2.EVENT_MOUSEWHEEL, 0, 0, 120 << 16, None)       # wheel up
    assert M.S.chat_scroll == 3
    U.on_mouse(U.cv2.EVENT_MOUSEWHEEL, 0, 0, -120 << 16, None)      # wheel down
    assert M.S.chat_scroll == 0
    # other events do nothing
    U.on_mouse(U.cv2.EVENT_LBUTTONDOWN, 0, 0, 0, None)
    assert M.S.chat_scroll == 0


def test_an_unknown_vision_backend_dies():
    """An unknown SCENE_SEG -> die() (a hard crash, not an exception), in a child."""
    here = os.path.dirname(__file__)
    code = ("import sys, os;"
            "sys.path.insert(0, os.path.join(%r, '..'));"
            "from perception2.backend import BackendLoader;"
            "BackendLoader('yoloe')" % (here,))
    r = subprocess.run([sys.executable, "-c", code],
                       env={**os.environ, "MVD_HOME": "integration_harden2"},
                       capture_output=True, text=True)
    assert r.returncode != 0, "unknown SCENE_SEG must crash"
    assert "no vision backend" in r.stderr, r.stderr


def test_ascii_only_drops_non_ascii():
    from app.draw import ascii_only
    assert ascii_only("שלום hello") == " hello" and ascii_only(None) == ""


# ============= status_pane.py, chat_pane.py: status and chat panes =============


def _box_colour(panel, row):
    # first row baseline; a green row is 22 + 6 px tall
    y = 50 + row * 28
    return tuple(int(v) for v in panel[y - 5, 19])


def test_pane_has_the_frame_height_and_the_status_width():
    panel = render_status(config.STATUS_W, 480, [])
    assert panel.shape == (480, config.STATUS_W, 3)


def test_waiting_is_orange():
    panel = render_status(config.STATUS_W, 480, [("dji app", "WAITING", "no answer")])
    assert _box_colour(panel, 0) == config.COL_STATUS_WAITING


def test_up_is_green_and_any_other_state_is_red():
    panel = render_status(
        config.STATUS_W, 480, [("gemma", "UP", ""), ("sam3", "UP", "")]
    )
    assert _box_colour(panel, 0) == config.COL_STATUS_UP
    panel = render_status(config.STATUS_W, 480, [("gemma", "RECOVERING", "")])
    assert _box_colour(panel, 0) == config.COL_STATUS_DOWN
    for state in ("STARTING", "FAILED", "DOWN"):
        assert (
            _box_colour(render_status(config.STATUS_W, 480, [("x", state, "")]), 0)
            == config.COL_STATUS_DOWN
        )


def test_long_detail_and_many_rows_never_overflow():
    rows = [
        (f"system{i}", "FAILED", "exited with code 139; restart 3/3 " * 5)
        for i in range(40)
    ]
    panel = render_status(config.STATUS_W, 300, rows)
    assert panel.shape == (300, config.STATUS_W, 3)


def test_status_pane_takes_its_width_from_the_caller():
    assert render_status(123, 200, []).shape == (200, 123, 3)


def test_chat_pane_takes_the_width_it_is_given():
    assert render_chat(700, 300, [], False, False, None).shape == (300, 700, 3)


def test_scrolling_hides_the_newest_rows():
    chat = [("user", f"line {i}", "user") for i in range(30)]
    following = render_chat(700, 300, chat, False, False, None, scroll=0)
    scrolled = render_chat(700, 300, chat, False, False, None, scroll=6)
    assert following.shape == scrolled.shape and not np.array_equal(following, scrolled)
    assert np.array_equal(
        render_chat(700, 300, chat, False, False, None, scroll=10**6),
        # clamped
        render_chat(700, 300, chat, False, False, None, scroll=len(chat) * 2 - 2)
    )


def test_draw_box_draws_the_box_and_its_label():
    from app.draw import draw_box
    img = np.zeros((60, 60, 3), np.uint8)
    draw_box(img, (10, 20, 40, 50), (0, 255, 0), label="car")
    assert tuple(img[20, 25]) == (0, 255, 0)                         # the top edge
    # the label above the box
    assert img[5:18, 10:40].any()


def test_chat_kind_classifies_generic_lines():
    from app.chat_rows import chat_kind
    assert chat_kind("rejected -- no action") == "reject"
    assert chat_kind("Highlighting: chair") == "action"
    assert chat_kind("ספרתי 3: chairs") == "answer"
    assert chat_kind("a room with two chairs") == "scene"


# ==================== main.py: which processes the settings need ====================
class RecordingSupervisor:
    """Records each ProcessSpec it is asked to start; starts nothing."""

    def __init__(self):
        self.names = []

    def start(self, spec):
        self.names.append(spec.name)
        return spec.name


def test_the_settings_decide_which_processes_start(monkeypatch, tmp_path):
    # not the real clips folder
    monkeypatch.setattr(config, "CLIPS_DIR", str(tmp_path / "asr_clips"))
    monkeypatch.setattr(config, "ASR_SOURCES", ["ros", "phone"])
    monkeypatch.setattr(config, "DJI_REAL", False)
    sup = RecordingSupervisor()
    processes, gstreamer = M.start_processes(sup, str(tmp_path), "0")
    assert gstreamer is None                                       # webcam: no gstreamer
    assert sup.names == ["gemma", "keys", "asr", "mock"] == processes


def test_the_keyboard_hook_starts_without_the_mic(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ASR_SOURCES", ["phone"])
    monkeypatch.setattr(config, "DJI_REAL", True)
    monkeypatch.setattr(config, "PHONE_IP", "10.0.0.7")
    sup = RecordingSupervisor()
    processes, gstreamer = M.start_processes(sup, str(tmp_path), "ros")
    assert gstreamer == "gstreamer"
    assert sup.names == ["gemma", "keys", "gstreamer"] == processes   # keys: always


def test_a_line_break_in_a_chat_line_does_not_crash_the_pane():
    """2026-09-25: a transcript with a line break crashed PIL's textlength (live run)."""
    chat = [("user", "הלו?\nמה זה יפה?", "user"), ("model", "a\nb", "scene")]
    panel = render_chat(900, 300, chat, False, False, None)
    assert panel.shape == (300, 900, 3)


# ============= the whole app over ROS on a virtual screen (plan step 9) =============
# The REAL app (python3 -m app.main) with every process it starts: Gemma, SAM3, the ASR
# server, the keyboard hook, the mock phone app. Speech comes in on the ASR topic and
# keys (F4, F1) on the keyboard topic, as the C++ nodes send them. The window draws on
# the owner's display with HARDEN2_APP_TEST_SCREEN=1, else on a virtual screen (Xvfb).
# Needs the GPU, a webcam and the mic stack; ~1-5 min. Control is the mock ONLY.
APP_TEST = os.environ.get("HARDEN2_APP_TEST") == "1"
ON_SCREEN = os.environ.get("HARDEN2_APP_TEST_SCREEN") == "1"
XVFB_DISPLAY = ":97"
READY_SECONDS = 420.0      # Gemma and SAM3 load from a cold start
ANSWER_SECONDS = 120.0
DESCRIBE = "מה אתה רואה"
COUNT = "כמה אנשים יש"
FLY = "טוס קדימה שני מטר"


class _LiveApp:
    """The app in a child process, its output in a file, and ROS publishers for the
    speech and key topics."""

    def __init__(self, tmp_path):
        self.session = str(tmp_path / "session")
        self.out_path = str(tmp_path / "app.out")
        self.mock_log = os.path.join(self.session, "mock_commands.log")
        display = os.environ.get("DISPLAY", ":0")
        self.xvfb = None
        if not ON_SCREEN:
            display = XVFB_DISPLAY
            self.xvfb = subprocess.Popen(
                [
                    "Xvfb",
                    XVFB_DISPLAY,
                    "-screen", "0", "1920x1600x24",
                    "-nolisten", "tcp",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        env = dict(
            os.environ,
            DISPLAY=display,
            CONTROL="mock",
            VIDEO="webcam",
            TTS_OUTPUTS="phone",
            MVD_SESSION_DIR=self.session,
            SCENE_TMUX_SESSION="",
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            PULSE_SERVER=os.environ.get("PULSE_SERVER", "unix:/tmp/pulse-socket"),
        )
        self.out = open(self.out_path, "w")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "app.main"],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            env=env,
            stdout=self.out,
            stderr=subprocess.STDOUT
        )
        M.ros.start()
        self.node = rclpy.create_node("test_whole_app")
        self.speech = self.node.create_publisher(String, config.ASR_TOPIC, 10)
        self.keys = self.node.create_publisher(
            Int32MultiArray,
            config.KEYBOARD_RAW_TOPIC,
            10
        )
        return

    def close(self):
        """Stop whatever is still running: the app dies through its crash path (which
        stops its children first), then the virtual screen if there is one."""
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            wait_for(lambda: self.proc.poll() is not None, 60.0)
        if self.proc.poll() is None:
            self.proc.kill()
        self.node.destroy_node()
        self.out.close()
        if self.xvfb is None:
            return
        self.xvfb.terminate()
        self.xvfb.wait()
        return

    def output(self):
        with open(self.out_path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def commands(self, path):
        """Every body the mock phone app received on this path, in order."""
        bodies = []
        marker = f" {path} "
        if not os.path.exists(self.mock_log):
            return bodies

        with open(self.mock_log, encoding="utf-8") as f:
            for line in f:
                if marker not in line:
                    continue
                bodies.append(line.split(marker, 1)[1].strip())
        return bodies

    def turns(self):
        """The session's finished turns: the trace records, in order."""
        path = os.path.join(self.session, "trace.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def say(self, text, path="/tts"):
        """Publish one transcript, as the ASR server does, and wait until the mock gets a
        new request on `path`. -> the new bodies on that path."""
        before = len(self.commands(path))
        msg = String()
        msg.data = text
        wait_for(lambda: self.speech.get_subscription_count() > 0, 10.0)
        self.speech.publish(msg)
        assert wait_for(lambda: len(self.commands(path)) > before, ANSWER_SECONDS), (
            f"no {path} after {text!r}\n{self.output()[-3000:]}"
        )
        time.sleep(1.0)            # a turn may send a second request
        return self.commands(path)[before:]

    def press(self, code):
        """A key press and its release, as the keyboard hook publishes them."""
        msg = Int32MultiArray()
        wait_for(lambda: self.keys.get_subscription_count() > 0, 10.0)
        for action in (config.KEY_ACTION_PRESSED, config.KEY_ACTION_RELEASED):
            msg.data = [code, action]
            self.keys.publish(msg)
        return


def _gemma_pid():
    r = subprocess.run(
        ["pgrep", "-f", f"llama-server.*--port {config.LLAMA_SERVER_PORT}"],
        capture_output=True,
        text=True
    )
    if not r.stdout.split():
        return None
    return int(r.stdout.split()[0])


@pytest.mark.skipif(
    not APP_TEST,
    reason="the whole app: GPU, webcam, mic, ~5 min; set HARDEN2_APP_TEST=1"
)
def test_the_whole_app_over_ros(tmp_path):
    running = subprocess.run(["pgrep", "-f", "app[.]main"], capture_output=True)
    assert running.returncode == 1, "another app is running: run.sh down first"
    assert _gemma_pid() is None, "a Gemma server holds the app's port"
    app = _LiveApp(tmp_path)

    try:
        assert wait_for(
            lambda: "[status] gemma: UP" in app.output()
            and "[status] sam3: UP" in app.output(),
            READY_SECONDS
        ), app.output()[-3000:]

        # three questions: Gemma looks, SAM3 counts, the mock flies
        assert app.say(DESCRIBE)
        assert app.say(COUNT)
        assert app.say(FLY, "/c/fly")
        kinds = {turn["heard_he"]: turn["kind"] for turn in app.turns()}
        assert kinds[DESCRIBE] == "describe" and kinds[COUNT] == "count"

        # F4: manual on stops the drone and refuses the next mission
        app.press(config.KILL_KEY_CODE)
        assert wait_for(lambda: app.commands("/c/stop"), 10.0)
        assert any("refused" in body for body in app.say(FLY))
        assert len(app.commands("/c/fly")) == 1
        # F4 again: missions are allowed again
        app.press(config.KILL_KEY_CODE)
        assert wait_for(lambda: any("auto:" in b for b in app.commands("/tts")), 10.0)

        # Gemma dies: the supervisor restarts it, and it answers again
        os.kill(_gemma_pid(), signal.SIGKILL)
        assert wait_for(lambda: "[status] gemma: RECOVERING" in app.output(), 30.0)
        assert wait_for(
            lambda: app.output().count("[status] gemma: UP") == 2,
            READY_SECONDS
        ), app.output()[-3000:]
        assert app.say(DESCRIBE)

        # F1 over ROS, as the hook sends it from any window: every process stopped
        app.press(config.QUIT_KEY_CODE)
        assert wait_for(lambda: app.proc.poll() is not None, 90.0)
        assert app.proc.returncode == 0, app.output()[-3000:]
        assert "FATAL" not in app.output()
        assert _gemma_pid() is None
    finally:
        app.close()
