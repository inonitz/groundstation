#!/usr/bin/env python3
"""integration scene demo -- the full integration experience (native-res video + ChatGPT-style chat
pane + legend + voice); the open-vocab HIGHLIGHT is one SAM3-nf4 forward (boxes + masks), the successor
to the old OmDet+SAM2.1 pair. Background is the closed-set YOLO26-seg (kept, off by default).
vlm.py/ears.py/eyes.py.

  voice "highlight the red backpack" -> SAM3 finds it and masks it every frame (box follows)
  voice "what do you see / how many people" -> Qwen3-VL answers in the chat pane
  voice "clear" -> drop the highlight
  python3 mvd.py --source 0 --target "guitar case"   # webcam, no ASR (test)
  python3 mvd.py                                       # drone RTSP + live ASR
Keys: q/Esc quit | c clear highlight | t SAM2 masks on/off | b background on/off | x clear chat
"""
import json
import os, sys, time, threading, textwrap, collections, subprocess, argparse
import cv2, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # self-contained: import only local modules
import config
import config_constants as _K, config_defaults as _D   # the two merged config files are the source of truth
from perception import PerceptionEngine, parse_highlight, ascii_only, parse_count
from perception import vlm_client as vlm
from perception.detectors import Eyes
from perception2.concept import phrase_concepts        # pure python; SAM3 itself loads lazily
from perception2.counting import count_instances, median_count   # block-A fix 2026-09-09: dedup + median over frames
from video.camera_stream import open_capture, ROS_SOURCES
from control.router import Router
from control.commands import Tier
from control.dji_wire import DjiWire
from control.kill import KillSwitch
try:
    from audio.ros2_asr import Ears; _HAVE_EARS = True
except Exception:
    _HAVE_EARS = False

from overlay import FONT, draw_box, render_chat
from session_log import SessionLog, reject_why







def _fmt_cmd(c):
    """One mission Action -> compact 'type k=v k=v' for the overlay Cmd List."""
    if not isinstance(c, dict):
        return str(c)
    t = c.get("type", "?")
    rest = " ".join(f"{k}={v}" for k, v in c.items() if k != "type")
    return (t + " " + rest).strip()






SESSION = None
# Highlight backend, chosen by SCENE_SEG:
#   omdet (default) = OmDet-Turbo detect + SAM2.1 mask, two models -- the proven demo path.
#   sam3            = one SAM3-nf4 forward gives boxes AND masks (perception2.Sam3Backend); OmDet
#                     and SAM2.1 never load, which frees the ~705 MiB a GPU translator needs
#                     (ruling 2026-09-07). Flip the default only after the live test passes on it.
SEG = os.environ.get("SCENE_SEG", _K.SEGMENTER)      # default sam3 since 2026-09-08 (owner ruling); omdet = the old OmDet+SAM2.1 pair
SAM3_PERIOD = float(os.environ.get("SCENE_SAM3_PERIOD", str(_K.SAM3_MIN_SECONDS_BETWEEN_FORWARDS)))   # min seconds between SAM3 forwards
HL_GIVEUP = float(os.environ.get("SCENE_HL_GIVEUP", str(_K.HIGHLIGHT_GIVEUP_SECONDS)))
GATE = _D.HIGHLIGHT_PRESENCE_GATE    # highlight presence: sam3 (DEFAULT, owner ruling 2026-09-09 07:35: Gemma plans, SAM3 sees) | either | vlm (Gemma decides)
COUNT_FRAMES = int(os.environ.get("SCENE_COUNT_FRAMES", str(_K.COUNT_MEDIAN_FRAMES)))         # frames per count answer, median taken (2026-09-09)
COUNT_GAP = float(os.environ.get("SCENE_COUNT_GAP", str(_K.COUNT_FRAME_GAP_SECONDS)))           # seconds between those frames
MIN_BOX_FRAC = float(os.environ.get("SCENE_MIN_BOX_FRAC", str(_K.MIN_BOX_FRACTION_OF_FRAME)))
# No arbitrary object cap. SAM3 returns boxes+masks in ONE cached pass, so there is no per-box cost to
# limit (the old 3/8 caps were inherited from OmDet+SAM2.1, where each box cost a separate SAM2.1 mask).
# The real ceiling is SAM3's own object-query budget (sam3-mask-bench: 47 windows, 51 in market-2; exact
# budget not yet measured). We set these ABOVE that budget so we never clip a real scene; they exist only
# as a latency safety-valve, tunable by env, not as a product limit. Counting must never be clipped.
HL_TOPK = int(os.environ.get("SCENE_HL_TOPK", str(_K.SAM3_MAX_BOXES_PER_QUERY)))   # SAM3 boxes per query; above SAM3's own budget so it never clips
HL_MAX  = int(os.environ.get("SCENE_HL_MAX", str(_K.MAX_HIGHLIGHTS_DRAWN_PER_FRAME)))    # detections DRAWN per frame; effectively draw-all
OM = {"det": None, "name": "SAM3"}
ENGINE = {"e": None}       # PerceptionEngine, built in main() once eyes exist


class Shared:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.bg_dets, self.hl_dets, self.hl_masks = [], [], []
        self.target = None; self.thinking = False; self.vlm_box = None
        self.use_sam, self.show_bg = True, True
        self.conf, self.mask_k = 0.62, 3
        self.chat = collections.deque(maxlen=60)
        self.fps = 0.0; self.running = True
        self.kill = None                      # KillSwitch once the wire exists (M toggles kill / re-arm)
        self.hl_miss_since, self.hl_miss_target = None, None   # give-up clock for a highlight SAM3 never finds
S = Shared()


_last_hl_dbg = [0.0]
def _hl_debug(tgt, raw, shape, thr=0.0):
    """Throttled: show what OmDet actually returns for the gated target, with box coverage %.
    Reads: 'found but low conf' vs 'found but too big' vs 'not found at all'."""
    now = time.time()
    if now - _last_hl_dbg[0] < 2.0: return
    _last_hl_dbg[0] = now
    Hf, Wf = shape[:2]; fa = float(Hf * Wf)
    if not raw:
        print(f"[hl-cand] '{tgt}': {OM['name']} found NOTHING above floor", flush=True); return
    top = ", ".join(f"{d['label']}={d['conf']:.2f}@{100*((d['box'][2]-d['box'][0])*(d['box'][3]-d['box'][1])/fa):.0f}%"
                    for d in raw[:5])
    kept = sum(1 for d in raw if d["conf"] >= thr)
    print(f"[hl-cand] '{tgt}' keep>={thr:.2f} ({kept}/{len(raw)}): {top}", flush=True)


def worker(eyes):
    while S.running:
        with S.lock:
            frame = None if S.frame is None else S.frame.copy()
            target, use_sam, show_bg, conf, mk = S.target, S.use_sam, S.show_bg, S.conf, S.mask_k
            vbox_px = S.vlm_box
        if frame is None:
            time.sleep(0.005); continue
        bg = eyes.background(frame) if show_bg else []
        hl, masks = [], []
        engine = ENGINE["e"]
        if target and engine is not None:
            hl, masks, dbg = engine.highlight_step(frame, target, vbox_px, use_sam)
            _hl_debug(target, dbg.get("raw", []), frame.shape, dbg.get("threshold", 0.0))
            if hl and MIN_BOX_FRAC > 0:                     # drop speck boxes (same floor as the gate and the count)
                fa = frame.shape[0] * frame.shape[1]; ms = list(masks) if masks else []
                keep = [i for i, d in enumerate(hl) if (d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]) >= fa * MIN_BOX_FRAC]
                hl = [hl[i] for i in keep]; masks = [ms[i] for i in keep if i < len(ms)]
        with S.lock:
            S.bg_dets = bg
            if target: S.hl_dets, S.hl_masks = hl, masks
            else: S.hl_dets, S.hl_masks = [], []
            if target and not hl:                       # nothing found this cycle: start / continue the give-up clock
                if S.hl_miss_since is None or S.hl_miss_target != target: S.hl_miss_since, S.hl_miss_target = time.time(), target
                elif time.time() - S.hl_miss_since > HL_GIVEUP:
                    S.target = None; S.vlm_box = None; S.hl_miss_since = None
                    S.chat.append(("model", f"לא מצאתי: {target}")); print(f"[mvd] highlight dropped after {HL_GIVEUP:.0f}s without a SAM3 hit: {target}", flush=True)
                    if SESSION: SESSION.end_request({"gave_up": True, "after_s": HL_GIVEUP})
            else:
                S.hl_miss_since = None
        time.sleep(0.003)


def build_highlight(seg, eyes, loader=None):
    """The highlight backend behind the engine's two injected callables (detect, mask_for_box).
    The model loads on a background thread; until it is ready detect() returns [] (no highlight).
    sam3: detect() is rate-limited to one SAM3 forward per SCENE_SAM3_PERIOD seconds per phrase --
    the worker runs highlight_step every frame, and an unthrottled ~0.45 s forward would hog the
    GPU the VLM and whisper share. Between forwards the last boxes (and their cached masks) stand.
    `loader` injects a backend factory (tests). Returns (detect, mask_for_box, loader_thread)."""
    if seg != "sam3":
        raise ValueError(f"SCENE_SEG must be sam3, got {seg!r}")
    def make():
        from perception2.sam3_backend import Sam3Backend
        return Sam3Backend()
    make = loader or make

    def _load():
        try:
            OM["det"] = make(); print(f"[mvd] {OM['name']} ready", flush=True)
        except Exception as e:
            print(f"[mvd] {OM['name']} load FAILED:", e, flush=True)
    th = threading.Thread(target=_load, daemon=True); th.start()

    last = {"phrase": None, "t": 0.0, "dets": []}
    def detect(f, p, c):
        be = OM["det"]
        if be is None:
            return []
        now = time.time()
        if p == last["phrase"] and now - last["t"] < SAM3_PERIOD:
            return last["dets"]
        dets = be.detect(f, p, conf=c, topk=HL_TOPK)
        last.update(phrase=p, t=now, dets=dets)
        if SESSION is not None:                    # one pass per FRESH forward (cached returns above never reach here)
            SESSION.save_pass(f, SESSION.det_payload(dets), round((time.time() - now) * 1000))
        return dets
    mask_for_box = lambda f, b: OM["det"].mask_for_box(f, b) if OM["det"] else None
    return detect, mask_for_box, th




class TextHandler:
    """One transcript in, one action out. The dispatch is __call__; each branch is its own method,
    and the two slow branches (VLM presence gate, VLM answer) run on their own threads so the ASR
    callback never blocks. Holds the router and voice it was built with; all shared state is S."""

    def __init__(self, router, voice):
        self.router = router
        self.voice = voice

    def __call__(self, text):
        text = (text or "").strip()
        if not text:
            return
        print("[mvd] you:", text, flush=True)
        with S.lock: S.chat.append(("user", text))
        if SESSION: SESSION.begin(text)
        try:
            if self._handle_drone(text):
                return
            self.perceive(text)
        finally:
            if SESSION:
                rec = getattr(SESSION._tl, "rec", None)
                if rec:
                    en = rec.get("english")
                    mis = rec.get("mission")
                    with S.lock:
                        if en: S.chat.append(("meta", f"{'En':<7}| " + en))
                        if rec.get("kind"):
                            S.chat.append(("meta", f"{'Kind':<7}| " + str(rec["kind"])))
                        if mis:
                            for i, c in enumerate(mis):
                                lbl = "Cmds" if i == 0 else ""
                                S.chat.append(("cmd", f"{lbl:<7}| {i}  " + _fmt_cmd(c)))
                        if rec.get("action") and not str(rec.get("action")).startswith("perception("):
                            S.chat.append(("meta", f"{'Action':<7}| " + str(rec["action"])))
                        if str(rec.get("action", "")).startswith("reject") or rec.get("kind") == "reject":
                            S.chat.append(("model", "rejected -- " + reject_why(rec.get("action", ""))))
                        S.chat.append(("meta", ""))
                SESSION.commit()

    def perceive(self, text):
        """The perception dispatch: highlight / clear / VLM ask. Reused as the Recognizer
        Pipeline's vlm_query, so a Hebrew see-question (translated to English) lands here."""
        cnt = parse_count(text)
        if cnt is not None:
            self._handle_count(cnt); return
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
        try:
            res = self.router.handle(text)
        except Exception as e:
            with S.lock: S.chat.append(("model", f"[drone unreachable: {e}]"))
            if SESSION: SESSION.set(action=f"error: {e}")
            return True
        if SESSION:
            if res.tier is not Tier.COMPLEX: SESSION.set(kind=str(getattr(res, "tier", "")).split(".")[-1])
            _rec = getattr(SESSION._tl, "rec", None)      # router label only as FALLBACK; the
            if _rec is not None and not _rec.get("action"):  # pipeline wrap sets the real action
                _rec["action"] = getattr(res, "action", None)
        if res.tier is not Tier.COMPLEX:                 # basic/emergency/override acted on the wire
            with S.lock: S.chat.append(("model", f"[drone] {res.action}"))
        return True                                      # COMPLEX handled by the Recognizer (on_complex)

    def _handle_count(self, phrase):
        """harden2: count with SAM3 alone (score floor 0.5, the lane-3c setting), highlight what it counted, say the number."""
        with S.lock:
            frame = None if S.frame is None else S.frame.copy(); S.thinking = True
        if SESSION: SESSION.begin_request("count", phrase, query=f"count {phrase}")
        threading.Thread(target=self._count_thread, args=(frame, phrase), daemon=True).start()

    def _count_thread(self, fr, phrase):
        """Count = median over COUNT_FRAMES consecutive frames of the contained-box-deduplicated SAM3
        instances at conf >= 0.5 (live 2026-09-09 block A: one frame, no dedup, gave 2/5/4/6 for the same chairs)."""
        concepts = phrase_concepts(phrase) if SEG == "sam3" else phrase
        counts = []
        cap_frame = None; cap_raw = []; cap_kept = []          # first analysed frame + its dets, for the record
        try:
            frame = fr
            for i in range(COUNT_FRAMES):
                if i:
                    time.sleep(COUNT_GAP)
                    with S.lock: frame = None if S.frame is None else S.frame.copy()
                if frame is not None and ENGINE["e"] is not None:
                    raw = ENGINE["e"].detect(frame, concepts, 0.5)
                    kept = count_instances(raw, 0.5, frame_area=frame.shape[0] * frame.shape[1], min_frac=MIN_BOX_FRAC)
                    counts.append(len(kept))
                    if cap_frame is None:
                        cap_frame, cap_raw, cap_kept = frame, raw, kept
        except Exception as e:
            print(f"[mvd] count failed: {e}", flush=True)
        n = median_count(counts)
        with S.lock:
            S.thinking = False
            S.target = concepts if n else None; S.vlm_box = None
            S.chat.append(("model", f"ספרתי {n}: {phrase}"))
        print(f"[mvd] count '{phrase}' -> {n} (median of {counts}; SAM3 @0.5 + dedup, concepts '{concepts}')", flush=True)
        if SESSION: SESSION.end_request({"n": n, "per_frame_counts": counts})
        if self.voice is not None:
            try: self.voice.say(f"יש {n}" if n else "לא מצאתי")
            except Exception: pass

    def _handle_clear(self):
        with S.lock:
            S.target = None; S.hl_dets = []; S.hl_masks = []
            S.chat.append(("model", "Cleared the highlight."))
        if SESSION: SESSION.end_request("cleared")

    def _handle_highlight(self, phrase):
        """Snapshot the frame and gate off-thread. The VLM presence GATE exists because OmDet (like
        any open-vocab detector) returns a confident box even when the object is absent -- it grounds
        'red backpack' onto the salient person. Ask the strong VLM first; suppress if not visible."""
        with S.lock:
            frame = None if S.frame is None else S.frame.copy(); S.thinking = True
        if SESSION: SESSION.begin_request("highlight", phrase, query=f"highlight {phrase}")
        threading.Thread(target=self._gate_thread, args=(frame, phrase), daemon=True).start()

    def _handle_ask(self, text):
        with S.lock:
            frame = None if S.frame is None else S.frame.copy(); S.thinking = True
        if frame is None:
            with S.lock: S.thinking = False
            return
        if SESSION: SESSION.begin_request("describe", text, query=text)
        threading.Thread(target=self._ask_thread, args=(frame, text), daemon=True).start()

    # --- thread bodies --------------------------------------------------------------
    def _gate_thread(self, fr, tgt):
        present, px = True, None
        gate_raw, hits = [], []                                 # SAM3 dets for the record (empty on the VLM-only gate)
        if GATE != "sam3" and fr is not None and ENGINE["e"] is not None:
            present, px = ENGINE["e"].presence_gate(fr, tgt)
        concepts = phrase_concepts(tgt) if SEG == "sam3" else tgt   # SAM3 grounds bare concepts
        if fr is not None and ENGINE["e"] is not None and (GATE == "sam3" or (GATE == "either" and not present)):
            try:
                gate_raw = ENGINE["e"].detect(fr, concepts, 0.1)   # LOW floor so the absent message can report near-misses
                hits = count_instances(gate_raw, 0.5, frame_area=fr.shape[0] * fr.shape[1], min_frac=MIN_BOX_FRAC)
            except Exception as e: gate_raw = []; hits = []; print(f"[mvd] gate SAM3 check failed: {e}", flush=True)
            if GATE == "sam3": present, px = bool(hits), None
            elif hits: present, px = True, None; print(f"[mvd] gate '{tgt}': VLM said absent, SAM3 has {len(hits)} at >=0.5 -> present (SCENE_GATE=either)", flush=True)
        if px is not None and (px[2] - px[0] < 8 or px[3] - px[1] < 8):   # a zero/degenerate box = the VLM saw nothing (live 2026-09-08, line 34)
            present, px = False, None
        if os.environ.get("MVD_PLANNER", "gemma4") == "gemma4":         # Gemma's boxes: median IoU 0.02 -> never draw them as a fallback
            px = None
        with S.lock:
            S.thinking = False
            if present:
                S.target = concepts; S.vlm_box = px; S.chat.append(("model", f"Highlighting: {tgt}"))
                _best = max((float(d["conf"]) for d in gate_raw), default=0.0)
                S.chat.append(("meta", f"{'SAM3':<7}| {concepts} · best {_best:.2f} ✓"))
            else:
                S.target = None; S.vlm_box = None; S.hl_dets = []; S.hl_masks = []
                _best = max((float(d["conf"]) for d in gate_raw), default=0.0)
                if not gate_raw:      _why = "SAM3 found nothing"
                elif _best < 0.5:     _why = f"SAM3 best {_best:.2f} < 0.50 gate"
                else:                 _why = f"SAM3 best {_best:.2f} but below the size floor"
                S.chat.append(("model", f'no "{concepts}" in view -- {_why}'))
        print(f"[mvd] gate '{tgt}': present={present} -> px={px}", flush=True)
        if SESSION and not present:
            SESSION.end_request({"present": False, "best_conf": round(_best, 3), "why": _why})

    def _ask_thread(self, fr, q):
        try: desc, _, _, spoken = vlm.ask(fr, q, [])
        except Exception as e: desc = f"[VLM err: {e}]"; spoken = ""
        with S.lock:
            S.chat.append(("model", desc))                       # long -> Scene:
            if spoken and spoken != desc and not desc.startswith("["):
                S.chat.append(("spoken", spoken))                # short -> Spoken: (also on screen)
            S.thinking = False
        print("[mvd] scene:", desc, "|| spoken:", spoken, flush=True)
        if SESSION:
            SESSION.save_pass(fr, {"answer": desc, "spoken": spoken})
            SESSION.end_request({"answer": desc, "spoken": spoken})
        if self.voice is not None and spoken and not desc.startswith("["):   # screen shows both; speak the SHORT
            self.voice.say(spoken)






def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.environ.get("SCENE_INPUT", "rtsp://127.0.0.1:8554/live"))
    ap.add_argument("--target", default=None, help="seed a highlight without ASR (testing)")
    ap.add_argument("--no-ears", action="store_true")
    ap.add_argument("--keep-llama", action="store_true")
    a = ap.parse_args()
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

    global SESSION
    try:
        SESSION = SessionLog()
    except Exception as e:
        print("[mvd] session log disabled:", e, flush=True); SESSION = None

    threading.Thread(target=vlm.ensure_server, daemon=True).start()
    eyes = Eyes()
    we_started_llama = subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True).returncode != 0
    # The engine is pure logic; the highlight backend (OmDet+SAM2.1 or SAM3, see SEG) arrives on
    # its background thread, so the callables check OM at call time. Env knobs are read once here.
    detect, mask_for_box, _ = build_highlight(SEG, eyes)
    print(f"[mvd] highlight backend: {OM['name']} (SCENE_SEG={SEG})", flush=True)
    ENGINE["e"] = PerceptionEngine(
        detect=detect,
        mask_for_box=mask_for_box,
        vlm_ask=vlm.ask,
        floor=float(os.environ.get("SCENE_DETECT_FLOOR", str(_K.DETECTOR_QUERY_THRESHOLD))),
        draw_conf=float(os.environ.get("SCENE_HL_CONF", str(_K.MIN_DRAW_CONFIDENCE))),
        rel=_D.RELATIVE_CONFIDENCE_GATE,
        mask_k=HL_MAX)   # 2026-09-09: was the constructor default 3; "highlight all the cars" needs many

    voice = None
    if os.environ.get("MVD_TTS", "1") != "0":
        try:
            from audio.tts_io import Voice
            voice = Voice()
        except Exception as e:
            print("[mvd] voice/TTS unavailable:", e, flush=True)

    on_text = TextHandler(None, voice)          # router assigned below (breaks the wiring cycle)

    if os.environ.get("MVD_DRONE"):
        try:
            wire = DjiWire.from_env()
            _orig_fly = wire.fly_mission                  # record the mission the system sends
            def _fly_rec(mission, _o=_orig_fly):
                if SESSION: SESSION.set(mission=mission)
                return _o(mission)
            wire.fly_mission = _fly_rec
            _orig_halt = wire.halt
            def _halt_rec(_o=_orig_halt):
                if SESSION: SESSION.set(mission=[{"delay": 0}])
                return _o()
            wire.halt = _halt_rec
            from recognizer import Pipeline
            def _say(msg):
                with S.lock: S.chat.append(("model", msg))
                print("[say]", msg, flush=True)          # always in app.log: the KILL / refused lines were chat-only in block A (2026-09-09)
                if voice is not None: voice.say(msg)
            # COMPLEX text now runs the Recognizer: a Hebrew command becomes a mission on the
            # wire, a see-question routes back to perception via on_text.perceive, a reject is said.
            pipe = Pipeline(wire, vlm_query=on_text.perceive, say=_say, observe=(SESSION.set if SESSION else None))
            _orig_handle = pipe.handle                    # record the pipeline's REAL action string
            def _handle_rec(text, _o=_orig_handle):
                out = _o(text)
                if SESSION: SESSION.set(action=out)
                return out
            pipe.handle = _handle_rec
            router = Router(wire, on_complex=pipe.handle)
            S.kill = KillSwitch(wire, say=_say)   # owner ruling 2026-09-08: M = manual override toggle (stop + RC control + latch)
            on_text.router = router
            print("[mvd] MVD drone router ON ->",
                  os.environ.get("MVD_WIRE_HOST", "127.0.0.1"),
                  "(real)" if os.environ.get("MVD_WIRE_REAL") else "(mock)", flush=True)
        except Exception as e:
            print("[mvd] drone router DISABLED:", e, flush=True)

    ears = None
    if _HAVE_EARS and not a.no_ears:
        try: ears = Ears(on_text); print("[mvd] ASR live", flush=True)
        except Exception as e: print("[mvd] Ears unavailable:", e)
    phone_ears = None                                  # the PHONE as the user's mic (inbound ASR socket)
    if os.environ.get("MVD_PHONE_ASR", "1") != "0" and not a.no_ears:
        try:
            from audio.phone_asr import PhoneEars
            phone_ears = PhoneEars(on_text, port=int(os.environ.get("MVD_PHONE_ASR_PORT", "8080")))
        except Exception as e:
            print("[mvd] PhoneEars unavailable:", e, flush=True)
    if a.target:
        with S.lock: S.target = a.target

    cap = open_capture(a.source); t0 = time.time()
    while not cap.isOpened() and time.time() - t0 < config.OPEN_TIMEOUT:
        print("[mvd] waiting for input", a.source, flush=True); time.sleep(1.5); cap.release(); cap = open_capture(a.source)
    if not cap.isOpened():
        print("cannot open", a.source); return

    threading.Thread(target=worker, args=(eyes,), daemon=True).start()
    win = "integration:mvd"; cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)   # AUTOSIZE: opens at content size (frame+chat), not resizable to empty margins
    tprev = time.time(); readfail = 0
    live = str(a.source) in ROS_SOURCES or "://" in str(a.source) or "!" in str(a.source)
    _src = str(a.source)                                 # HUD: what we are watching + who we talk to (static per run)
    if "://" in _src:   _srclabel = _src.split("://", 1)[0] + "://" + _src.split("://", 1)[1].split("/")[0]
    elif _src.isdigit(): _srclabel = "webcam " + _src
    else:               _srclabel = os.path.basename(_src) or _src
    if os.environ.get("MVD_DRONE"):
        _wlabel = (("REAL " if os.environ.get("MVD_WIRE_REAL") else "mock ")
                   + os.environ.get("MVD_WIRE_HOST", "127.0.0.1") + ":" + os.environ.get("MVD_WIRE_PORT", "8080"))
    else:
        _wlabel = "no-drone"
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                readfail += 1
                if not live and readfail > config.READ_RETRY:
                    print("[mvd] input ended", flush=True); break
                ph = np.zeros((config.CAM_H, config.CAM_W, 3), np.uint8)
                cv2.putText(ph, "waiting for video...", (30, config.CAM_H // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
                cv2.imshow(win, ph)
                if (cv2.waitKey(50) & 0xFF) in (27, ord("q")): break
                continue
            readfail = 0
            with S.lock: S.frame = frame
            disp = frame.copy()
            with S.lock:
                bg, hl, masks = list(S.bg_dets), list(S.hl_dets), list(S.hl_masks)
                show_bg, use_sam = S.show_bg, S.use_sam
            if show_bg:
                for d in bg: draw_box(disp, d["box"], config.COL_BACKGROUND, d.get("label"), 1)
            if use_sam and masks:
                ov = disp.copy()
                for m in masks:
                    if m.shape[:2] != disp.shape[:2]:
                        m = cv2.resize(m.astype("uint8"), (disp.shape[1], disp.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
                    ov[m] = config.COL_SAM2_HL
                cv2.addWeighted(ov, 0.45, disp, 0.55, 0, disp)
            for d in hl:
                draw_box(disp, d["box"], config.COL_YOLOE_HL, f'{d["label"]} {d["conf"]:.2f}', 2)
            now = time.time()
            with S.lock: S.fps = 0.9 * S.fps + 0.1 / max(now - tprev, 1e-3); fps = S.fps
            tprev = now
            with S.lock:
                _chat, _thinking = list(S.chat), S.thinking
                _killed = bool(S.kill and S.kill.killed)
            chat_panel = render_chat(disp.shape[0], _chat, _thinking, _killed,
                                     SESSION.dir if SESSION else None, OM["name"])
            canvas = cv2.hconcat([disp, chat_panel])
            hud = f"{fps:4.1f} fps | {OM['name']}:{'ready' if OM['det'] else 'loading'} | {_srclabel} | {_wlabel}"
            cv2.putText(canvas, hud, (10, 22), FONT, 0.55, (0, 0, 0), 3, cv2.LINE_AA)            # shadow -> readable on a white wall
            cv2.putText(canvas, hud, (10, 22), FONT, 0.55, config.COL_HUD, 1, cv2.LINE_AA)       # cyan
            ptt = "F5 to talk (F5, speak, F5)"
            cv2.putText(canvas, ptt, (10, disp.shape[0] - 12), FONT, 0.48, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(canvas, ptt, (10, disp.shape[0] - 12), FONT, 0.48, (163, 149, 139), 1, cv2.LINE_AA)
            cv2.imshow(win, canvas)
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord('q')): break
            elif k == ord('c'):
                with S.lock: S.target = None; S.hl_dets = []; S.hl_masks = []
            elif k == ord('t'):
                with S.lock: S.use_sam = not S.use_sam
            elif k == ord('b'):
                with S.lock: S.show_bg = not S.show_bg
            elif k == ord('x'):
                with S.lock: S.chat.clear()
            elif k in (ord('m'), ord('M')) and S.kill is not None:   # M: manual override toggle (kill / re-arm)
                S.kill.toggle()
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1: break
    finally:
        S.running = False; time.sleep(0.05)
        cap.release(); cv2.destroyAllWindows(); cv2.waitKey(1)
        if ears: ears.shutdown()
        if we_started_llama and not a.keep_llama:
            subprocess.run(["pkill", "-f", "llama-server"], check=False)
        sess = os.environ.get("SCENE_TMUX_SESSION")
        if sess:                              # launched by the tmux script -> quit = full teardown
            subprocess.run(["tmux", "kill-session", "-t", sess], check=False)
        os._exit(0)   # bypass torch/ROCm interpreter-teardown crash -> clean exit code 0, no core dump

if __name__ == "__main__":
    main()
