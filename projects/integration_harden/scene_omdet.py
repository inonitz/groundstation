#!/usr/bin/env python3
"""integration scene demo -- the full integration experience (native-res video + ChatGPT-style chat
pane + legend + voice), but the open-vocab HIGHLIGHT is OmDet-Turbo (Apache) -> SAM2.1 masks, replacing
the broken YOLOE/LLMDet. Reuses highlight_seg.py's validated OmDet engine and integration's frozen
vlm.py/ears.py/eyes.py.

  voice "highlight the red backpack" -> OmDet finds it every frame -> SAM2 masks it (box follows)
  voice "what do you see / how many people" -> Qwen3-VL answers in the chat pane
  voice "clear" -> drop the highlight
  python3 scene_omdet.py --source 0 --target "guitar case"   # webcam, no ASR (test)
  python3 scene_omdet.py                                       # drone RTSP + live ASR
Keys: q/Esc quit | c clear highlight | t SAM2 masks on/off | b background on/off | x clear chat
"""
import os, sys, time, threading, textwrap, collections, subprocess, argparse
os.environ.setdefault("SCENE_HL_BACKEND", "vlm")          # Eyes: no YOLOE load; we supply OmDet
import cv2, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # self-contained: import only local modules
import config, vlm
from router import Router
from commands import Tier
from dji_wire import DjiWire
from eyes import Eyes
import highlight_seg as HS                                 # OmDet, _apply_masks, parse_highlight, _ascii, open_capture
try:
    from ears import Ears; _HAVE_EARS = True
except Exception:
    _HAVE_EARS = False

FONT = cv2.FONT_HERSHEY_SIMPLEX
OM = {"det": None}


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
        print(f"[hl-cand] '{tgt}': OmDet found NOTHING above floor", flush=True); return
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
        det = OM["det"]
        if target and det is not None:
            floor     = float(os.environ.get("SCENE_DETECT_FLOOR", "0.12"))   # see ALL candidates
            draw_conf = float(os.environ.get("SCENE_HL_CONF", "0.30"))        # gate guards FPs, so draw low
            try: raw = det.detect(frame, target, conf=floor)
            except Exception as e: raw = []; print("omdet err:", e)
            rel  = float(os.environ.get("SCENE_HL_REL", "0.65"))   # keep only within 65% of the TOP score
            best = raw[0]["conf"] if raw else 0.0                    # raw is sorted desc by conf
            thr  = max(draw_conf, best * rel)                        # relative gate: 0.48 dies next to 0.90; two real windows both survive
            _hl_debug(target, raw, frame.shape, thr)
            keep = [d for d in raw if d["conf"] >= thr]
            hl, masks = HS._apply_masks(keep, frame, eyes.mask_for_box, use_sam, mk)
            if not hl and vbox_px is not None:          # OmDet whiffed -> fall back to the VLM's own box + SAM2
                try: m = eyes.mask_for_box(frame, vbox_px)
                except Exception as e: m = None; print("sam err:", e)
                d = {"label": f"{target} (vlm)", "conf": 1.0, "box": vbox_px}
                if m is not None and m.sum() > 0:
                    ys, xs = np.where(m); d["box"] = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
                    hl, masks = [d], [m]
                else:
                    hl, masks = [d], []
        with S.lock:
            S.bg_dets = bg
            if target: S.hl_dets, S.hl_masks = hl, masks
            else: S.hl_dets, S.hl_masks = [], []
        time.sleep(0.003)


def draw_box(img, box, color, label=None, thick=2):
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)
    if label:
        cv2.putText(img, label, (x1, max(y1 - 6, 12)), FONT, 0.5, color, 1, cv2.LINE_AA)


def render_chat(height):
    w = config.CHAT_W
    panel = np.full((height, w, 3), 26, np.uint8)
    y = 24
    cv2.putText(panel, "integration (OmDet)", (12, y), FONT, 0.6, (225, 225, 225), 1, cv2.LINE_AA)
    y += 10; cv2.line(panel, (0, y), (w, y), (70, 70, 70), 1); y += 20
    with S.lock:
        show_bg, use_sam, target = S.show_bg, S.use_sam, S.target
        chat, thinking = list(S.chat), S.thinking

    def legend(color, label, state=None):
        nonlocal y
        cv2.rectangle(panel, (12, y - 10), (28, y + 2), color, -1)
        cv2.rectangle(panel, (12, y - 10), (28, y + 2), (90, 90, 90), 1)
        txt = label if state is None else f"{label}   [{state}]"
        cv2.putText(panel, txt, (36, y), FONT, 0.46, (210, 210, 210), 1, cv2.LINE_AA); y += 20

    legend(config.COL_BACKGROUND, "background", f"b: {'on' if show_bg else 'off'}")
    legend(config.COL_YOLOE_HL, "highlight (OmDet open-vocab)")
    legend(config.COL_SAM2_HL, "SAM2 mask", f"t: {'on' if use_sam else 'off'}")
    cv2.putText(panel, f"target: {HS._ascii(target or '(none)')}", (12, y), FONT, 0.46, (0, 215, 255), 1, cv2.LINE_AA); y += 20
    cv2.putText(panel, "Press H: record on/off", (12, y), FONT, 0.5, config.COL_HUD, 1, cv2.LINE_AA); y += 20
    cv2.putText(panel, "keys: c clear  x chat  Esc/q quit", (12, y), FONT, 0.44, (150, 150, 150), 1, cv2.LINE_AA)
    y += 10; cv2.line(panel, (0, y), (w, y), (70, 70, 70), 1); conv_top = y + 8

    maxchars = max(int((w - 26) / 9), 12)
    lines = []
    for role, text in chat:
        text = HS._ascii(text)
        if role == "spoken":
            lines.append(("Spoken:", (0, 215, 255)))                 # amber label -> what the drone SAYS aloud
            body = (150, 210, 245)
        else:
            lines.append(("You:" if role == "user" else "Scene:",
                          config.COL_CHAT_USER if role == "user" else config.COL_CHAT_MODEL))
            body = (205, 225, 255) if role == "user" else (225, 225, 225)
        for wl in (textwrap.wrap(text, maxchars) or [""]):
            lines.append((wl, body))
        lines.append(("", (0, 0, 0)))
    if thinking:
        lines.append(("Scene: thinking...", config.COL_CHAT_MODEL))
    if not lines:
        lines = [("press H, speak, press H.", (150, 150, 150)), ('e.g. "highlight the red backpack"', (150, 150, 150))]
    yy = height - 14
    for text, col in reversed(lines):
        if yy < conv_top + 14:
            break
        indent = 12 if text.endswith(":") else 22
        cv2.putText(panel, text, (indent, yy), FONT, 0.5, col, 1, cv2.LINE_AA); yy -= 20
    return panel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.environ.get("SCENE_INPUT", "rtsp://127.0.0.1:8554/live"))
    ap.add_argument("--target", default=None, help="seed a highlight without ASR (testing)")
    ap.add_argument("--no-ears", action="store_true")
    ap.add_argument("--keep-llama", action="store_true")
    a = ap.parse_args()
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

    threading.Thread(target=vlm.ensure_server, daemon=True).start()
    eyes = Eyes()
    we_started_llama = subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True).returncode != 0
    def _load(dev):
        try: OM["det"] = HS.OmDet(dev); print("[scene_omdet] OmDet ready", flush=True)
        except Exception as e: print("[scene_omdet] OmDet load FAILED:", e, flush=True)
    threading.Thread(target=_load, args=(eyes.tdevice,), daemon=True).start()

    router = None
    if os.environ.get("MVD_DRONE"):
        try:
            router = Router(DjiWire.from_env())
            print("[scene_omdet] MVD drone router ON ->",
                  os.environ.get("MVD_WIRE_HOST", "127.0.0.1"),
                  "(real)" if os.environ.get("MVD_WIRE_REAL") else "(mock)", flush=True)
        except Exception as e:
            print("[scene_omdet] drone router DISABLED:", e, flush=True)

    voice = None
    if os.environ.get("MVD_TTS", "1") != "0":
        try:
            from voice import Voice
            voice = Voice()
        except Exception as e:
            print("[scene_omdet] voice/TTS unavailable:", e, flush=True)

    def on_text(text):
        text = (text or "").strip()
        if not text: return
        print("[scene_omdet] you:", text, flush=True)
        with S.lock: S.chat.append(("user", text))
        if router is not None:
            try:
                res = router.handle(text)
            except Exception as e:
                with S.lock: S.chat.append(("model", f"[drone unreachable: {e}]"))
                return
            if res.tier is not Tier.COMPLEX:      # basic/emergency/override handled -> done
                with S.lock: S.chat.append(("model", f"[drone] {res.action}"))
                return
        ph = HS.parse_highlight(text)
        if ph == "":
            with S.lock:
                S.target = None; S.hl_dets = []; S.hl_masks = []
                S.chat.append(("model", "Cleared the highlight."))
            return
        if ph is not None:
            # VLM presence GATE: OmDet (like any open-vocab detector) returns a confident box even when
            # the object is absent -- it grounds "red backpack" onto the salient person. Before letting
            # OmDet draw, ask the strong VLM whether the target is actually visible; suppress if not.
            with S.lock:
                gframe = None if S.frame is None else S.frame.copy(); S.thinking = True
            def _gate(fr, tgt):
                present, vbox, px = True, None, None
                if fr is not None:
                    try:
                        ans, vt, vb, _ = vlm.ask(fr, f"Point at and highlight the {tgt}.", [])
                        present = vt is not None      # VLM writes HIGHLIGHT: none when absent
                        vbox = vb
                    except Exception as e:
                        present = True; print("[scene_omdet] gate VLM err:", e, flush=True)
                    if vbox and fr is not None:
                        Hf, Wf = fr.shape[:2]
                        sc = 1000.0 if max(vbox) > 1.5 else 1.0   # auto-detect 0-1 vs 0-1000 coords
                        px = (int(vbox[0]/sc*Wf), int(vbox[1]/sc*Hf), int(vbox[2]/sc*Wf), int(vbox[3]/sc*Hf))
                with S.lock:
                    S.thinking = False
                    if present:
                        S.target = tgt; S.vlm_box = px; S.chat.append(("model", f"Highlighting: {tgt}"))
                    else:
                        S.target = None; S.vlm_box = None; S.hl_dets = []; S.hl_masks = []
                        S.chat.append(("model", f"I don't see a {tgt} in view."))
                print(f"[scene_omdet] gate '{tgt}': present={present} vlm_box={vbox} -> px={px}", flush=True)
            threading.Thread(target=_gate, args=(gframe, ph), daemon=True).start()
            return
        with S.lock:
            frame = None if S.frame is None else S.frame.copy(); S.thinking = True
        if frame is None:
            with S.lock: S.thinking = False
            return
        def _ask(fr, q):                      # run OFF the ASR thread so voice never blocks
            try: desc, _, _, spoken = vlm.ask(fr, q, [])
            except Exception as e: desc = f"[VLM err: {e}]"; spoken = ""
            with S.lock:
                S.chat.append(("model", desc))                       # long -> Scene:
                if spoken and spoken != desc and not desc.startswith("["):
                    S.chat.append(("spoken", spoken))                # short -> Spoken: (also on screen)
                S.thinking = False
            print("[scene_omdet] scene:", desc, "|| spoken:", spoken, flush=True)
            if voice is not None and spoken and not desc.startswith("["):   # screen shows both; speak the SHORT
                voice.say(spoken)
        threading.Thread(target=_ask, args=(frame, text), daemon=True).start()

    ears = None
    if _HAVE_EARS and not a.no_ears:
        try: ears = Ears(on_text); print("[scene_omdet] ASR live", flush=True)
        except Exception as e: print("[scene_omdet] Ears unavailable:", e)
    phone_ears = None                                  # the PHONE as the user's mic (inbound ASR socket)
    if os.environ.get("MVD_PHONE_ASR", "1") != "0" and not a.no_ears:
        try:
            from phone_ears import PhoneEars
            phone_ears = PhoneEars(on_text, port=int(os.environ.get("MVD_PHONE_ASR_PORT", "8080")))
        except Exception as e:
            print("[scene_omdet] PhoneEars unavailable:", e, flush=True)
    if a.target:
        with S.lock: S.target = a.target

    cap = HS.open_capture(a.source); t0 = time.time()
    while not cap.isOpened() and time.time() - t0 < config.OPEN_TIMEOUT:
        print("[scene_omdet] waiting for input", a.source, flush=True); time.sleep(1.5); cap.release(); cap = HS.open_capture(a.source)
    if not cap.isOpened():
        print("cannot open", a.source); return

    threading.Thread(target=worker, args=(eyes,), daemon=True).start()
    win = "integration:scene_omdet"; cv2.namedWindow(win, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    tprev = time.time(); readfail = 0
    live = str(a.source) in ("ros","camera_stream","camera/stream") or "://" in str(a.source) or "!" in str(a.source)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                readfail += 1
                if not live and readfail > config.READ_RETRY:
                    print("[scene_omdet] input ended", flush=True); break
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
            canvas = cv2.hconcat([disp, render_chat(disp.shape[0])])
            cv2.putText(canvas, f"{fps:4.1f} fps  {disp.shape[1]}x{disp.shape[0]}  OmDet:{'ready' if OM['det'] else 'loading'}",
                        (10, 22), FONT, 0.55, config.COL_HUD, 1, cv2.LINE_AA)
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
