#!/usr/bin/env python3
"""integration scene demo -- the full integration experience (native-res video + ChatGPT-style chat
pane + legend + voice); the open-vocab HIGHLIGHT is one SAM3-nf4 forward (boxes + masks), the successor
to the old OmDet+SAM2.1 pair. Every SAM3 call runs on one consumer thread (VISION queue).

  voice "highlight the red backpack" -> SAM3 finds it and masks it every frame (box follows)
  voice "what do you see / how many people" -> the model answers in the chat pane
  voice "clear" -> drop the highlight
  python3 mvd.py --source 0 --target "guitar case"   # webcam, no ASR (test)
  python3 mvd.py                                       # drone RTSP + live ASR
Keys: q/Esc quit | c clear highlight | t masks on/off | [ ] or mouse wheel scroll the chat | x clear chat
"""
import argparse
import collections
import importlib.util
import os
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # self-contained: import only local modules
import config
from perception2.engine import PerceptionEngine
from perception2.text_parse import parse_highlight, parse_count
from perception2 import vlm_client as vlm
from gemma import server as gemma_server
from system.status import BOARD, DOWN, STARTING, UP, fail
from system.supervisor import Supervisor
from perception2.concept import phrase_concepts        # pure python; SAM3 itself loads lazily
from perception2.backend import DETECT_OK, DETECT_NOT_READY
from perception2.task_queue import TaskQueue, PRIORITY_REFRESH, SUBMIT_OK
from perception2.counting import count_instances, median_count   # block-A fix 2026-09-09: dedup + median over frames
from video.camera_stream import open_capture, source_kind, StallGuard, start_services as start_video_services
from control.router import Router
from control.commands import Tier
from control.dji_wire import DjiWire, start_services as start_control_services
from control.kill import KillSwitch
from audio.phone_asr import PhoneEars
from recognizer import Pipeline
from perception2.backend import BACKENDS
from perception2.verify import split_target, verify_highlight

# The ROS2 mic path is optional (a webcam run on a machine without ROS has none). Checked without importing,
# so there is no try on the import (the camera_stream pattern).
_HAVE_EARS = importlib.util.find_spec("rclpy") is not None and importlib.util.find_spec("std_msgs") is not None
if _HAVE_EARS:
    from audio.ros2_asr import Ears, start_services as start_asr_services

from overlay import FONT, draw_box, render_chat, render_status, chat_kind
from session_log import SessionLog, reject_why


from fatal import die, install_crash_hooks

def _fmt_cmd(c):
    """One mission Action -> compact 'type k=v k=v' for the overlay Cmd List."""
    if not isinstance(c, dict):
        return str(c)
    t = c.get("type", "?")
    rest = " ".join(f"{k}={v}" for k, v in c.items() if k != "type")
    return (t + " " + rest).strip()


SESSION = None
# Highlight backend: SAM3 only. One SAM3-nf4 forward gives boxes AND masks (perception2.Sam3Backend).
# The old OmDet-Turbo + SAM2.1 pair was removed 2026-09-17.
SEG = config.SEG      # only "sam3" is valid; build_highlight rejects anything else
SAM3_PERIOD = config.SAM3_PERIOD   # min seconds between SAM3 forwards
HL_GIVEUP = config.HL_GIVEUP
GATE = config.GATE    # highlight presence: sam3 (DEFAULT, owner ruling 2026-09-09 07:35: Gemma plans, SAM3 sees) | either | vlm (Gemma decides)
VERIFY = config.VERIFY  # on | off (default ON, config): after the gate, also require the related noun + relation (perception2/verify.py)
COUNT_FRAMES = config.COUNT_FRAMES         # frames per count answer, median taken (2026-09-09)
COUNT_GAP = config.COUNT_GAP           # seconds between those frames
MIN_BOX_FRAC = config.MIN_BOX_FRAC
# No arbitrary object cap. SAM3 returns boxes+masks in ONE cached pass, so there is no per-box cost to
# limit (the old 3/8 caps were inherited from OmDet+SAM2.1, where each box cost a separate SAM2.1 mask).
# The real ceiling is SAM3's own object-query budget (sam3-mask-bench: 47 windows, 51 in market-2; exact
# budget not yet measured). We set these ABOVE that budget so we never clip a real scene; they exist only
# as a latency safety-valve, tunable by env, not as a product limit. Counting must never be clipped.
HL_TOPK = config.HL_TOPK   # SAM3 boxes per query; above SAM3's own budget so it never clips
HL_MAX  = config.HL_MAX    # detections DRAWN per frame; effectively draw-all
OM = {"det": None}
ENGINE = {"e": None}       # PerceptionEngine, built in main()
VISION = {"q": None}       # the ONE SAM3 consumer (perception2.TaskQueue); every SAM3 call runs on it
SUPERVISOR = {"s": None}   # the ONE process supervisor (system.Supervisor); the app starts every process with it


class Shared:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.hl_dets, self.hl_masks = [], []
        self.target = None
        self.thinking = False
        self.use_sam = True
        self.chat = collections.deque(maxlen=60)
        self.kill = None                      # KillSwitch once the wire exists (M toggles kill / re-arm)
        self.hl_miss_since = None             # give-up clock for a highlight SAM3 stops finding
        self.chat_scroll = 0                  # chat rows scrolled up from the newest (0 = follow)
        self.hl_id = 0                        # bumps on every new highlight or clear; a stale refresh drops itself
S = Shared()


def _snapshot_frame():
    """A private copy of the latest frame, or None. The reference is taken under the lock and the copy runs
    outside it, so the display loop never waits on a full-frame copy (it never mutates a published frame)."""
    with S.lock:
        frame = S.frame
    return None if frame is None else frame.copy()


# --- the SAM3 consumer's task bodies: they run ONLY on VISION["q"]'s one thread ------------
def submit_vision(fn):
    """Producer side: hand one COMMAND to the single SAM3 consumer. A full queue is reported in the
    chat, not queued. Returns True when the task was accepted."""
    if VISION["q"].submit(fn) == SUBMIT_OK:
        return True
    with S.lock:
        S.thinking = False
        S.chat.append(("model", f"Too many vision tasks ({config.VISION_MAX_TASKS}). Clear one, or wait.", "miss"))
    print("[mvd] vision queue full: task refused", flush=True)
    return False


def _drop_specks(frame, hl, masks):
    """Drop boxes under MIN_BOX_FRAC of the frame (same floor as the gate and the count)."""
    if not hl or MIN_BOX_FRAC <= 0:
        return hl, masks
    min_area = frame.shape[0] * frame.shape[1] * MIN_BOX_FRAC
    ms = list(masks) if masks else []
    keep = [i for i, d in enumerate(hl) if (d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]) >= min_area]
    return [hl[i] for i in keep], [ms[i] for i in keep if i < len(ms)]


def start_highlight(concepts):
    """Consumer thread. Make `concepts` the live highlight and start its refresh loop."""
    VISION["q"].cancel("highlight")
    with S.lock:
        S.hl_id += 1
        hl_id = S.hl_id
        S.target = concepts
        S.hl_miss_since = None
    VISION["q"].submit(lambda: refresh_highlight(hl_id), PRIORITY_REFRESH, 0.0, "highlight")
    return


def clear_highlight():
    """Consumer thread (the single writer). Stop the refresh loop and drop the drawn highlight."""
    VISION["q"].cancel("highlight")
    with S.lock:
        S.hl_id += 1
        S.target = None
        S.hl_dets = []
        S.hl_masks = []
        S.hl_miss_since = None
    return


def refresh_highlight(hl_id):
    """Consumer thread. One SAM3 re-detect of the live highlight, then reschedule it one SAM3
    period later. Stops when the highlight was replaced or cleared, or after HL_GIVEUP seconds
    without a hit."""
    with S.lock:
        if hl_id != S.hl_id:
            return
        target, use_sam = S.target, S.use_sam
    frame = _snapshot_frame()
    if frame is not None and ENGINE["e"] is not None:
        hl, masks, _dbg = ENGINE["e"].highlight_step(frame, target, None, use_sam)   # Gemma boxes are never drawn
        hl, masks = _drop_specks(frame, hl, masks)
        gave_up = False
        with S.lock:
            if hl_id != S.hl_id:
                return
            S.hl_dets, S.hl_masks = hl, masks
            if hl:
                S.hl_miss_since = None
            elif S.hl_miss_since is None:
                S.hl_miss_since = time.time()
            elif time.time() - S.hl_miss_since > HL_GIVEUP:
                gave_up = True
                S.chat.append(("model", f"לא מצאתי: {target}", "miss"))
        if gave_up:
            clear_highlight()
            print(f"[mvd] highlight dropped after {HL_GIVEUP:.0f}s without a SAM3 hit: {target}", flush=True)
            if SESSION:
                SESSION.end_request({"gave_up": True, "after_s": HL_GIVEUP})
            return
    VISION["q"].submit(lambda: refresh_highlight(hl_id), PRIORITY_REFRESH, SAM3_PERIOD, "highlight")
    return


def build_highlight(seg, loader=None):
    """The vision backend behind the engine's two injected callables (detect, mask_for_box).
    The backend is chosen once from SCENE_SEG (perception2/backend.py::BACKENDS) and loads on a
    background thread; until it is ready detect() returns (DETECT_NOT_READY, []). Every detect() is a
    real forward: the ONE vision consumer paces the highlight refresh (one per SAM3_PERIOD), so there is
    no phrase cache here any more -- it made count frames 2 and 3 reuse frame 1 (review finding R8).
    `loader` injects a factory (tests). Returns (detect, mask_for_box, loader_thread)."""
    make = loader or BACKENDS.get(seg)
    if make is None:
        die(f"SCENE_SEG={seg!r} has no vision backend (known: {', '.join(sorted(BACKENDS))})")

    def _load():
        BOARD.report("sam3", STARTING)
        OM["det"] = make()                           # a load failure reaches the crash hook -> die (required model)
        BOARD.report("sam3", UP)
    th = threading.Thread(target=_load, daemon=True)
    th.start()

    def detect(f, p, c):
        be = OM["det"]
        if be is None:
            return DETECT_NOT_READY, []
        t0 = time.time()
        status, dets = be.detect(f, p, conf=c, topk=HL_TOPK)
        if status != DETECT_OK:
            return status, []
        if SESSION is not None:                    # one recorded pass per forward
            SESSION.save_pass(f, SESSION.det_payload(dets), round((time.time() - t0) * 1000))
        return DETECT_OK, dets
    mask_for_box = lambda f, b: OM["det"].mask_for_box(f, b) if OM["det"] else None
    return detect, mask_for_box, th


def _absent_reason(veto, gate_raw, best):
    """Why a highlight was refused, in plain words, for the chat."""
    if veto:
        return veto
    if not gate_raw:
        return "SAM3 found nothing"
    if best < 0.5:
        return f"SAM3 best {best:.2f} < 0.50 gate"
    return f"SAM3 best {best:.2f} but below the size floor"


class TextHandler:
    """One transcript in, one action out. The dispatch is __call__; each branch is its own method.
    Vision work (highlight gate, count, clear) is SUBMITTED to the one SAM3 consumer (VISION queue);
    only the Gemma answer runs on its own thread. The ASR callback never blocks. Holds the router and
    voice it was built with; all shared state is S."""

    def __init__(self, router, voice):
        self.router = router
        self.voice = voice

    def __call__(self, text, source="mic"):
        text = (text or "").strip()
        if not text:
            return
        print("[mvd] you:", text, flush=True)
        with S.lock:
            S.chat.append(("user", text, "user"))
        if SESSION:
            SESSION.begin(text, source)
        if not self._handle_drone(text):
            self.perceive(text)
        self._record_turn()

    def _record_turn(self):
        """Show what the turn did (kind, mission, action, a reject's reason) and commit the session record."""
        if not SESSION:
            return
        rec = SESSION.current()
        if rec:
            kind = rec.get("kind")
            action = str(rec.get("action") or "")
            with S.lock:
                if kind:
                    S.chat.append(("meta", str(kind), "kind_hl" if kind == "highlight" else "kind_meta"))
                for i, step in enumerate(rec.get("mission") or []):
                    S.chat.append(("cmd", f"{i}  " + _fmt_cmd(step), "cmd_head" if i == 0 else "cmd"))
                if action and not action.startswith("perception("):
                    S.chat.append(("meta", action, "action_meta"))
                if action.startswith("reject") or kind == "reject":
                    S.chat.append(("model", reject_why(action), "reject"))
        SESSION.commit()
        return

    def perceive(self, text):
        """The perception dispatch: highlight / clear / VLM ask. Reused as the Recognizer
        Pipeline's vlm_query, so a Hebrew see-question (translated to English) lands here."""
        cnt = parse_count(text)
        if cnt is not None:
            self._handle_count(cnt)
            return
        phrase = parse_highlight(text)
        if phrase == "":
            self._handle_clear()
        elif phrase is not None:
            self._handle_highlight(phrase)
        else:
            self._handle_ask(text)

    # --- branches -------------------------------------------------------------------
    def _handle_drone(self, text):
        """-> True when a router is present (it consumes every turn). Basic/emergency/override act on
        the wire here; COMPLEX is handled inside router.handle by the Recognizer (on_complex). With no
        router, return False so perceive() runs directly -- the no-drone perception path."""
        if self.router is None:
            return False
        res = self.router.handle(text)   # the wire returns a status now; a failure is in res.action, not a throw
        if SESSION:
            if res.tier is not Tier.COMPLEX:
                SESSION.set(kind=str(res.tier).split(".")[-1])
            _rec = SESSION.current()      # router label only as FALLBACK; the
            if _rec is not None and not _rec.get("action"):  # pipeline wrap sets the real action
                _rec["action"] = getattr(res, "action", None)
        if res.tier is not Tier.COMPLEX:                 # basic/emergency/override acted on the wire
            with S.lock:
                S.chat.append(("model", f"[drone] {res.action}", "scene"))
        return True                                      # COMPLEX handled by the Recognizer (on_complex)

    def _handle_count(self, phrase):
        """harden2: count with SAM3 alone (score floor 0.5, the lane-3c setting), highlight what it counted, say the number."""
        frame = _snapshot_frame()
        with S.lock:
            S.thinking = True
        if SESSION:
            SESSION.begin_request("count", phrase, query=f"count {phrase}")
        submit_vision(lambda: self._count_task(frame, phrase))

    def _count_task(self, fr, phrase):
        """Count = median over COUNT_FRAMES consecutive frames of the contained-box-deduplicated SAM3
        instances at conf >= 0.5 (live 2026-09-09 block A: one frame, no dedup, gave 2/5/4/6 for the same chairs)."""
        concepts = phrase_concepts(phrase)
        counts = []
        frame = fr
        for i in range(COUNT_FRAMES):
            if i:
                time.sleep(COUNT_GAP)
                frame = _snapshot_frame()
            if frame is None or ENGINE["e"] is None:
                continue
            status, raw = ENGINE["e"].detect(frame, concepts, 0.5)
            if status != DETECT_OK:
                continue                          # a failed frame is not a zero count; skip it
            kept = count_instances(raw, 0.5, frame_area=frame.shape[0] * frame.shape[1], min_frac=MIN_BOX_FRAC)
            counts.append(len(kept))
        if not counts:                                  # every frame failed: not a zero count (R23)
            self._vision_not_ready(phrase)
            return
        n = median_count(counts)
        with S.lock:
            S.thinking = False
            S.chat.append(("model", f"ספרתי {n}: {phrase}", "answer"))
        if n:
            start_highlight(concepts)                 # highlight what was counted
        else:
            clear_highlight()
        print(f"[mvd] count '{phrase}' -> {n} (median of {counts}; SAM3 @0.5 + dedup, concepts '{concepts}')", flush=True)
        if SESSION:
            SESSION.end_request({"n": n, "per_frame_counts": counts})
        if self.voice is not None:
            self.voice.say(f"יש {n}" if n else "לא מצאתי")   # say() never raises: it only fills the mailbox

    def _vision_not_ready(self, what):
        """A vision command that could not run: SAM3 is not ready (or every forward failed). Say so, keep any
        live highlight, and record it. The sam3 row on the status pane shows why."""
        with S.lock:
            S.thinking = False
            S.chat.append(("model", f'"{what}": SAM3 is not ready yet -- see the status pane, then try again', "miss"))
        if SESSION:
            SESSION.end_request({"not_ready": True})
        if self.voice is not None:
            self.voice.say("המערכת עדיין לא מוכנה")         # "the system is not ready yet"
        return

    def _handle_clear(self):
        submit_vision(self._clear_task)

    def _clear_task(self):
        clear_highlight()
        with S.lock:
            S.chat.append(("model", "Cleared the highlight.", "scene"))
        if SESSION:
            SESSION.end_request("cleared")

    def _handle_highlight(self, phrase):
        """Snapshot the frame and gate off-thread. The VLM presence GATE exists because OmDet (like
        any open-vocab detector) returns a confident box even when the object is absent -- it grounds
        'red backpack' onto the salient person. Ask the strong VLM first; suppress if not visible."""
        frame = _snapshot_frame()
        with S.lock:
            S.thinking = True
        if SESSION:
            SESSION.begin_request("highlight", phrase, query=f"highlight {phrase}")
        submit_vision(lambda: self._gate_task(frame, phrase))

    def _handle_ask(self, text):
        frame = _snapshot_frame()
        with S.lock:
            S.thinking = True
        if frame is None:
            with S.lock:
                S.thinking = False
            return
        if SESSION:
            SESSION.begin_request("describe", text, query=text)
        threading.Thread(target=self._ask_thread, args=(frame, text), daemon=True).start()

    # --- thread bodies --------------------------------------------------------------
    def _gate_task(self, fr, tgt):
        """Is the target in view? SAM3 decides (GATE=sam3, the default); GATE=either also asks Gemma; VERIFY
        checks a relation clause ("backpack held by a child"). Present -> start the highlight refresh."""
        present = True
        gate_raw = []                                   # SAM3 dets for the record (empty on the VLM-only gate)
        engine = ENGINE["e"]
        if GATE != "sam3" and fr is not None and engine is not None:
            present, _ = engine.presence_gate(fr, tgt)  # Gemma's box is never drawn (median IoU 0.02)
        concepts = phrase_concepts(tgt)                 # SAM3 grounds bare concepts
        if fr is not None and engine is not None and (GATE == "sam3" or (GATE == "either" and not present)):
            status, gate_raw = engine.detect(fr, concepts, 0.1)   # LOW floor so the absent message can report near-misses
            if status != DETECT_OK:                     # SAM3 not ready: say so; never a false "absent" (R22)
                self._vision_not_ready(tgt)
                return
            hits = count_instances(gate_raw, 0.5, frame_area=fr.shape[0] * fr.shape[1], min_frac=MIN_BOX_FRAC)
            if GATE == "sam3":
                present = bool(hits)
            elif hits:
                present = True
                print(f"[mvd] gate '{tgt}': Gemma said absent, SAM3 has {len(hits)} at >=0.5 -> present (SCENE_GATE=either)", flush=True)
        veto = None
        if VERIFY == "on" and present and fr is not None and engine is not None:
            target = split_target(tgt)
            if target.related:                          # only phrases with a related noun pay for it
                verdict = verify_highlight(engine.detect, fr, target, floor=0.1,
                                           frame_area=fr.shape[0] * fr.shape[1], min_frac=MIN_BOX_FRAC)
                print(f"[mvd] verify '{tgt}': {verdict.verdict} -- {verdict.reason}", flush=True)
                if verdict.verdict not in ("draw", "failed"):   # failed = a SAM3 call failed: fail open
                    present, veto = False, verdict.reason
        best = max((float(d["conf"]) for d in gate_raw), default=0.0)
        why = ""
        with S.lock:
            S.thinking = False
            if present:
                S.chat.append(("model", f"Highlighting: {tgt}", "action"))
                S.chat.append(("meta", f"{concepts} · best {best:.2f} ✓", "sam3"))
            else:
                why = _absent_reason(veto, gate_raw, best)
                S.chat.append(("model", f'no "{concepts}" in view -- {why}', "miss"))
        if present:
            start_highlight(concepts)
        else:
            clear_highlight()
        print(f"[mvd] gate '{tgt}': present={present}", flush=True)
        if SESSION and not present:
            SESSION.end_request({"present": False, "best_conf": round(best, 3), "why": why})

    def _ask_thread(self, fr, q):
        ok, reply = vlm.ask(fr, q, [])
        if not ok:                     # Gemma's state is on the status panel; no chat line (owner 2026-09-22)
            with S.lock:
                S.thinking = False
            if SESSION:
                SESSION.end_request({"answer": None, "gemma": "failed"}, slot="describe")
            return
        desc, _, _, spoken = reply
        with S.lock:
            S.chat.append(("model", desc, "scene"))                       # long -> Scene:
            if spoken and spoken != desc:
                S.chat.append(("spoken", spoken, "spoken"))                # short -> Spoken: (also on screen)
            S.thinking = False
        print("[mvd] scene:", desc, "|| spoken:", spoken, flush=True)
        if SESSION:
            SESSION.save_pass(fr, {"answer": desc, "spoken": spoken}, slot="describe")
            SESSION.end_request({"answer": desc, "spoken": spoken}, slot="describe")
        if self.voice is not None and spoken:   # screen shows both; speak the SHORT
            self.voice.say(spoken)


# ---------------------------------------------------------------- startup helpers
def parse_source():
    """The one CLI argument: the video source (falls back to config.INPUT)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=config.INPUT)
    return parser.parse_args().source


def build_perception_engine():
    """Build the vision engine. The highlight backend (SAM3, see SEG) loads on its own thread,
    so the injected callables check OM at call time. Env knobs are read once, here."""
    detect, mask_for_box, _ = build_highlight(SEG)
    print(f"[mvd] vision backend: {SEG}", flush=True)
    VISION["q"] = TaskQueue(config.VISION_MAX_TASKS, name="sam3-worker")
    ENGINE["e"] = PerceptionEngine(
        detect=detect,
        mask_for_box=mask_for_box,
        vlm_ask=vlm.ask,
        floor=config.DETECT_FLOOR,
        draw_conf=config.HL_CONF,
        rel=config.HL_REL,
        mask_k=HL_MAX)   # 2026-09-09: was the constructor default 3; "highlight all the cars" needs many


def build_voice():
    """Build the TTS voice, or None when TTS is off. A fatal misconfig calls die() inside Voice()."""
    if config.TTS_BACKEND == "off":
        return None
    from audio.tts_io import Voice   # LAZY on purpose: tts_io loads the offline-TTS (phonikud/onnx) stack when present
    return Voice()


def setup_drone_router(on_text, voice):
    """Bring up the drone wire, the command pipeline, the router and the kill switch -- explicitly, with
    no catch (review blocker: one broad catch used to hide a half-wired router or a missing kill switch).
    A real host without allow_real die()s inside DjiWire; an unreachable phone shows on the status pane
    (the drone link never dies). The fly/halt wrappers record each mission into the session log."""
    wire = DjiWire.from_env()
    original_fly = wire.fly_mission
    original_halt = wire.halt

    def record_fly(mission, _fly=original_fly):
        if SESSION:
            SESSION.set(mission=mission)
        return _fly(mission)

    def record_halt(_halt=original_halt):
        if SESSION:
            SESSION.set(mission=[{"delay": 0}])
        return _halt()

    def say(message):
        with S.lock:
            S.chat.append(("model", message, chat_kind(message)))
        print("[say]", message, flush=True)   # always in app.log; KILL/refused lines were chat-only in block A
        if voice is not None:
            voice.say(message)

    wire.fly_mission = record_fly
    wire.halt = record_halt
    # A Hebrew command becomes a mission on the wire; a see-question routes back to
    # perception via on_text.perceive; a reject is said out loud.
    pipeline = Pipeline(wire, vlm_query=on_text.perceive, say=say, observe=(SESSION.set if SESSION else None))
    router = Router(wire, on_complex=pipeline.handle)
    pipeline.flight_allowed = lambda: router.mode == "auto"   # manual override (voice) blocks flight
    S.kill = KillSwitch(wire, say=say)   # owner 2026-09-08: M = manual override toggle (stop + RC control + latch)
    on_text.router = router
    print("[mvd] drone router ON ->", config.WIRE_HOST, "(real)" if config.WIRE_REAL else "(mock)", flush=True)
    return


def start_ears(on_text):
    """Start the ROS2 mic transcript subscriber (when ROS2 exists) and the phone-as-mic channel."""
    ears = Ears(lambda text: on_text(text, "mic")) if _HAVE_EARS else None
    phone_ears = None
    if config.PHONE_ASR_ENABLED:
        phone_ears = PhoneEars(lambda text: on_text(text, "phone"), port=config.PHONE_ASR_PORT)
    return ears, phone_ears


def open_source_with_retry(source):
    """Open the video source, retrying until config.OPEN_TIMEOUT. Returns None if it never opens."""
    cap = open_capture(source)
    start = time.time()
    while not cap.isOpened() and time.time() - start < config.OPEN_TIMEOUT:
        print("[mvd] waiting for input", source, flush=True)
        time.sleep(1.5)
        cap.release()
        cap = open_capture(source)
    if not cap.isOpened():
        print("cannot open", source)
        return None
    return cap


# ---------------------------------------------------------------- display helpers
def source_label(source):
    """A short HUD label for the video source."""
    text = str(source)
    kind = source_kind(text)
    if kind == "stream":
        scheme, rest = text.split("://", 1)
        return scheme + "://" + rest.split("/")[0]
    if kind == "webcam":
        return "webcam " + text
    return os.path.basename(text) or text


def wire_label():
    """A short HUD label for the drone-wire target."""
    prefix = "REAL " if config.WIRE_REAL else "mock "
    return prefix + config.WIRE_HOST + ":" + str(config.WIRE_PORT)


def draw_overlays(disp, hl, masks, use_sam):
    """Draw the SAM mask overlay and the highlight boxes onto disp."""
    if use_sam and masks:
        blended = disp.copy()
        for mask in masks:
            if mask.shape[:2] != disp.shape[:2]:
                mask = cv2.resize(mask.astype("uint8"), (disp.shape[1], disp.shape[0]),
                                  interpolation=cv2.INTER_NEAREST).astype(bool)
            blended[mask] = config.COL_SAM2_HL
        cv2.addWeighted(blended, 0.45, disp, 0.55, 0, disp)
    for det in hl:
        draw_box(disp, det["box"], config.COL_YOLOE_HL, f'{det["label"]} {det["conf"]:.2f}', 2)


def show_waiting_frame(win, src_label, wire_text):
    """Draw the 'waiting for video' placeholder WITH the status and chat panes, so start-up progress
    (Gemma STARTING, ...) is visible before the first frame. Returns True if the user pressed quit."""
    placeholder = np.zeros((config.CAM_H, config.CAM_W, 3), np.uint8)
    cv2.putText(placeholder, "waiting for video...", (30, config.CAM_H // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
    cv2.imshow(win, compose_canvas(placeholder, 0.0, src_label, wire_text))
    return (cv2.waitKey(50) & 0xFF) in (27, ord("q"))


def compose_canvas(disp, fps, src_label, wire_text):
    """The camera stream full width on top; below it the status pane and the chat pane side by side
    (owner layout 2026-09-22). The HUD and the talk prompt are drawn on the camera part."""
    with S.lock:
        chat = list(S.chat)
        thinking = S.thinking
        scroll = S.chat_scroll
        killed = bool(S.kill and S.kill.killed)
    width = disp.shape[1]
    status_panel = render_status(config.STATUS_W, config.BOTTOM_H, BOARD.snapshot())
    chat_panel = render_chat(width - config.STATUS_W, config.BOTTOM_H, chat, thinking, killed,
                             SESSION.dir if SESSION else None, scroll)
    canvas = cv2.vconcat([disp, cv2.hconcat([status_panel, chat_panel])])
    hud = f"{fps:4.1f} fps | {src_label} | {wire_text}"
    cv2.putText(canvas, hud, (10, 22), FONT, 0.55, (0, 0, 0), 3, cv2.LINE_AA)          # shadow -> readable on a white wall
    cv2.putText(canvas, hud, (10, 22), FONT, 0.55, config.COL_HUD, 1, cv2.LINE_AA)     # cyan
    prompt = "F5 to talk (F5, speak, F5)"
    cv2.putText(canvas, prompt, (10, disp.shape[0] - 12), FONT, 0.48, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(canvas, prompt, (10, disp.shape[0] - 12), FONT, 0.48, (163, 149, 139), 1, cv2.LINE_AA)
    return canvas


def on_mouse(event, _x, _y, flags, _param):
    """Mouse wheel over the window scrolls the chat: up = older rows, down = back toward the newest."""
    if event != cv2.EVENT_MOUSEWHEEL:
        return
    step = 3 if flags > 0 else -3              # the wheel delta is the signed upper 16 bits of flags; cv2 4.11 has no getMouseWheelDelta
    with S.lock:
        S.chat_scroll = max(0, S.chat_scroll + step)
    return


def handle_key(key):
    """Apply one keypress. Returns True when the app should quit.
    c = clear the highlight, t = toggle masks, [ / ] = scroll the chat up / down, x = clear chat,
    m/M = manual-override toggle (kill / re-arm)."""
    if key in (27, ord("q")):
        return True
    if key == ord("c"):
        submit_vision(clear_highlight)
    elif key == ord("t"):
        with S.lock:
            S.use_sam = not S.use_sam
    elif key == ord("["):
        with S.lock:
            S.chat_scroll += 3
    elif key == ord("]"):
        with S.lock:
            S.chat_scroll = max(0, S.chat_scroll - 3)
    elif key == ord("x"):
        with S.lock:
            S.chat.clear()
    elif key in (ord("m"), ord("M")) and S.kill is not None:
        S.kill.toggle()
    return False


def run_display_loop(cap, win, source, guard=None):
    """Read frames, draw the overlays and HUD, and handle keys until quit. For a ROS source the stall
    guard watches the NEW-frame count (a stalled stream still returns its last frame)."""
    src_label = source_label(source)
    wire_text = wire_label()
    # live sources never "end": a read miss is a hiccup, not EOF, so we do not stop on it.
    live = source_kind(source) in ("ros", "stream", "gstreamer")
    tprev = time.time()
    fps = 0.0
    readfail = 0
    seen_frames = 0
    while True:
        ok, frame = cap.read()
        if guard is not None:
            guard.tick(cap.frames != seen_frames)
            seen_frames = cap.frames
        if not ok:
            readfail += 1
            if not live and readfail > config.READ_RETRY:
                print("[mvd] input ended", flush=True)
                break
            if show_waiting_frame(win, src_label, wire_text):
                break
            continue
        readfail = 0
        with S.lock:
            S.frame = frame
            hl = list(S.hl_dets)
            masks = list(S.hl_masks)
            use_sam = S.use_sam
        disp = frame.copy()
        draw_overlays(disp, hl, masks, use_sam)
        now = time.time()
        fps = 0.9 * fps + 0.1 / max(now - tprev, 1e-3)
        tprev = now
        cv2.imshow(win, compose_canvas(disp, fps, src_label, wire_text))
        if handle_key(cv2.waitKey(1) & 0xFF):
            break
        if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
            break


def teardown(cap, ears):
    """Release the camera, close the windows, stop ASR, and exit with a clean code."""
    time.sleep(0.05)
    cap.release()
    cv2.destroyAllWindows()
    cv2.waitKey(1)
    if ears:
        ears.shutdown()
    SUPERVISOR["s"].stop_all()     # stop every process the app started (Gemma, ...)
    session = os.environ.get("SCENE_TMUX_SESSION")
    if session:   # launched by the tmux script -> quit tears the whole session down
        subprocess.run(["tmux", "kill-session", "-t", session], check=False)
    os._exit(0)   # bypass the torch/ROCm interpreter-teardown crash -> clean exit code 0, no core dump


# ---------------------------------------------------------------- entry point
def main():
    global SESSION
    install_crash_hooks()                    # an uncaught exception in any thread -> die(), never a silent dead thread
    source = parse_source()
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

    SESSION = SessionLog()                   # required at start-up: an unwritable folder dies (principle 2)
    log_dir = SESSION.dir
    sup = SUPERVISOR["s"] = Supervisor()     # the app starts EVERY process; the supervisor keeps each alive
    gemma_server.start_services(sup, log_dir)
    if _HAVE_EARS:
        start_asr_services(sup, log_dir)     # the whisper ASR server + the push-to-talk keyboard hook
    else:
        BOARD.report("asr", DOWN, "ROS2 not available: no mic ASR (the phone channel still works)")
    start_video_services(sup, log_dir, source)   # the gstreamer receiver, for a dji source
    start_control_services(sup, log_dir)         # the DJI API test double, in mock control mode

    build_perception_engine()
    voice = build_voice()
    on_text = TextHandler(None, voice)   # router assigned in setup_drone_router (breaks the wiring cycle)
    setup_drone_router(on_text, voice)
    ears, _phone_ears = start_ears(on_text)

    BOARD.report("video", STARTING)
    cap = open_source_with_retry(source)
    if cap is None:                          # the source is required: fail() -> die() stops every child first (R4)
        fail("video", f"cannot open {source}", f"cannot open the video source {source!r} within {config.OPEN_TIMEOUT:.0f}s")
    guard = StallGuard(sup, BOARD) if source_kind(source) == "ros" else None
    if guard is None:
        BOARD.report("video", UP)

    win = "integration:mvd"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)   # AUTOSIZE: opens at content size, not resizable to empty margins
    cv2.setMouseCallback(win, on_mouse)          # the wheel scrolls the chat
    run_display_loop(cap, win, source, guard)   # a crash here reaches the crash hook -> die (never exit 0, R24)
    teardown(cap, ears)


if __name__ == "__main__":
    main()
