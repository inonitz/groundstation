#!/usr/bin/env python3
"""llm_cv_track scene demo -- the full llm_cv_scene experience (native-res video + ChatGPT-style chat
pane + legend + voice), but the open-vocab HIGHLIGHT is OmDet-Turbo (Apache) -> SAM2.1 masks, replacing
the broken YOLOE/LLMDet. Reuses highlight_seg.py's validated OmDet engine and llm_cv_scene's frozen
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
SCENE = "/root/groundstation/source/llm_cv_scene"
sys.path.insert(0, HERE); sys.path.insert(0, SCENE)
import config, vlm
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
        self.target = None; self.thinking = False
        self.use_sam, self.show_bg = True, True
        self.conf, self.mask_k = 0.30, 3
        self.chat = collections.deque(maxlen=60)
        self.fps = 0.0; self.running = True
S = Shared()


def worker(eyes):
    while S.running:
        with S.lock:
            frame = None if S.frame is None else S.frame.copy()
            target, use_sam, show_bg, conf, mk = S.target, S.use_sam, S.show_bg, S.conf, S.mask_k
        if frame is None:
            time.sleep(0.005); continue
        bg = eyes.background(frame) if show_bg else []
        hl, masks = [], []
        det = OM["det"]
        if target and det is not None:
            try: raw = det.detect(frame, target, conf=conf)
            except Exception as e: raw = []; print("omdet err:", e)
            hl, masks = HS._apply_masks(raw, frame, eyes.mask_for_box, use_sam, mk)
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
    cv2.putText(panel, "llm_cv_track (OmDet)", (12, y), FONT, 0.6, (225, 225, 225), 1, cv2.LINE_AA)
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

    def on_text(text):
        text = (text or "").strip()
        if not text: return
        print("[scene_omdet] you:", text, flush=True)
        with S.lock: S.chat.append(("user", text))
        ph = HS.parse_highlight(text)
        if ph == "":
            with S.lock:
                S.target = None; S.hl_dets = []; S.hl_masks = []
                S.chat.append(("model", "Cleared the highlight."))
            return
        if ph is not None:
            with S.lock:
                S.target = ph; S.chat.append(("model", f"Highlighting: {ph}"))
            return
        with S.lock:
            frame = None if S.frame is None else S.frame.copy(); S.thinking = True
        if frame is None:
            with S.lock: S.thinking = False
            return
        def _ask(fr, q):                      # run OFF the ASR thread so voice never blocks
            try: desc, _, _ = vlm.ask(fr, q, [])
            except Exception as e: desc = f"[VLM err: {e}]"
            with S.lock: S.chat.append(("model", desc)); S.thinking = False
            print("[scene_omdet] scene:", desc, flush=True)
        threading.Thread(target=_ask, args=(frame, text), daemon=True).start()

    ears = None
    if _HAVE_EARS and not a.no_ears:
        try: ears = Ears(on_text); print("[scene_omdet] ASR live", flush=True)
        except Exception as e: print("[scene_omdet] Ears unavailable:", e)
    if a.target:
        with S.lock: S.target = a.target

    cap = HS.open_capture(a.source); t0 = time.time()
    while not cap.isOpened() and time.time() - t0 < config.OPEN_TIMEOUT:
        print("[scene_omdet] waiting for input", a.source, flush=True); time.sleep(1.5); cap.release(); cap = HS.open_capture(a.source)
    if not cap.isOpened():
        print("cannot open", a.source); return

    threading.Thread(target=worker, args=(eyes,), daemon=True).start()
    win = "llm_cv_track:scene_omdet"; cv2.namedWindow(win, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    tprev = time.time(); readfail = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                readfail += 1
                if readfail > config.READ_RETRY: print("[scene_omdet] input ended"); break
                time.sleep(0.03); continue
            readfail = 0
            with S.lock: S.frame = frame
            disp = frame.copy()
            with S.lock:
                bg, hl, masks = list(S.bg_dets), list(S.hl_dets), list(S.hl_masks)
                show_bg, use_sam = S.show_bg, S.use_sam
            if show_bg:
                for d in bg: draw_box(disp, d["box"], config.COL_BACKGROUND, None, 1)
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
