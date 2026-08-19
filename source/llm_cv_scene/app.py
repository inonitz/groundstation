"""llm_cv_scene: live camera at NATIVE resolution + real-time detection overlays + a
ChatGPT-style chat pane with a legend, driven by voice (ASR) and a VLM brain.

Perception runs on a WORKER THREAD so the display stays at camera FPS; the heavy open-vocab
highlight is throttled to SCENE_HL_HZ and SAM2 is opt-in (lazy). Overlays: grey=background,
green=grounded highlight (LLMDet), magenta=SAM2 mask, amber=VLM's own box.

Keys: q quit | c clear highlight | t SAM2 mask on/off | b background on/off | x clear chat
Record the session to share for debugging:  SCENE_RECORD=/path/out.mp4 python3 app.py
"""
import re, time, textwrap, threading, collections
import cv2, numpy as np
import config, vlm
from eyes import Eyes
from ears import Ears

FONT = cv2.FONT_HERSHEY_SIMPLEX
_TRANSLIT = {'\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"',
             '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00b0': ' deg', '\u2022': '*'}
def to_ascii(t):
    for k, v in _TRANSLIT.items():
        t = t.replace(k, v)
    return t.encode('ascii', 'ignore').decode('ascii')   # drop any remaining non-ASCII


# Deterministic highlight trigger straight from the transcript (no dependence on the VLM).
_CLEAR_RE = re.compile(r"\b(?:stop (?:highlight\w*|track\w*)|clear|reset|deselect|never ?mind)\b", re.I)
_FIND_RE  = re.compile(r"\b(?:highlight|locate|track|mark|find|show me|point (?:at|to)|where(?:'s| is| are))\s+(?:the |a |an |that |my )?(.+)", re.I)
_FILLER_RE = re.compile(r"\b(?:please|for me|in the (?:frame|image|scene|room|camera)|right now|thank you|thanks)\b.*$", re.I)

def parse_highlight(text):
    """-> phrase to highlight, '' to clear, or None if the sentence has no highlight intent."""
    if _CLEAR_RE.search(text):
        return ""
    m = _FIND_RE.search(text)
    if not m:
        return None
    phrase = _FILLER_RE.sub("", m.group(1)).strip().strip(".?! ,")
    return phrase or None


class Shared:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.bg_dets, self.hl_dets, self.hl_mask = [], [], None
        self.t_bg, self.t_hl = 0.0, 0.0
        self.target, self.vlm_box = None, None
        self.thinking = False
        self.use_sam2, self.show_bg = False, True
        self.chat = collections.deque(maxlen=60)
        self.running = True

S = Shared()


def open_capture(src):
    src = str(src)
    if src.isdigit():
        c = cv2.VideoCapture(int(src))
        c.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_W)
        c.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_H)
        return c
    if "!" in src:                       # GStreamer pipeline (drone stream, Phase 6)
        return cv2.VideoCapture(src, cv2.CAP_GSTREAMER)
    return cv2.VideoCapture(src)         # video file / URL


def perception_worker(eyes):
    """Detection loop, rate-capped to config.DETECT_HZ so it can't starve the display thread."""
    last_hl = 0.0
    min_dt = 1.0 / max(config.DETECT_HZ, 1.0)
    while S.running:
        loop_t0 = time.perf_counter()
        with S.lock:
            frame = None if S.frame is None else S.frame.copy()
            target, use_sam2, show_bg = S.target, S.use_sam2, S.show_bg
        if frame is None:
            time.sleep(0.005); continue

        t0 = time.perf_counter()
        bg = eyes.background(frame) if show_bg else []
        t_bg = (time.perf_counter() - t0) * 1000.0

        hl, mask, t_hl = None, None, None
        if target and (time.time() - last_hl) >= 1.0 / max(config.HIGHLIGHT_HZ, 0.1):
            last_hl = time.time()
            t1 = time.perf_counter()
            hl, mask = eyes.highlight(frame, want_mask=use_sam2)
            t_hl = (time.perf_counter() - t1) * 1000.0

        with S.lock:
            S.bg_dets, S.t_bg = bg, t_bg
            if hl is not None:                 # only on a fresh (non-throttled) highlight
                S.hl_dets, S.hl_mask, S.t_hl = hl, mask, t_hl
            if not target:
                S.hl_dets, S.hl_mask = [], None

        dt = time.perf_counter() - loop_t0
        if dt < min_dt:
            time.sleep(min_dt - dt)            # yield to the display thread


def draw_box(img, box, color, label=None, thick=2):
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)
    if label:
        cv2.putText(img, label, (x1, max(y1 - 6, 12)), FONT, 0.5, color, 1, cv2.LINE_AA)


def render_chat(height, use_sam2, show_bg):
    w = config.CHAT_W
    panel = np.full((height, w, 3), 26, np.uint8)
    y = 24
    cv2.putText(panel, "llm_cv_scene", (12, y), FONT, 0.6, (225, 225, 225), 1, cv2.LINE_AA)
    y += 10; cv2.line(panel, (0, y), (w, y), (70, 70, 70), 1); y += 20

    def legend(color, label, state=None):
        nonlocal y
        cv2.rectangle(panel, (12, y - 10), (28, y + 2), color, -1)
        cv2.rectangle(panel, (12, y - 10), (28, y + 2), (90, 90, 90), 1)
        txt = label if state is None else f"{label}   [{state}]"
        cv2.putText(panel, txt, (36, y), FONT, 0.46, (210, 210, 210), 1, cv2.LINE_AA)
        y += 20

    legend(config.COL_BACKGROUND, "background",           f"b: {'on' if show_bg else 'off'}")
    legend(config.COL_YOLOE_HL,   "highlight (LLMDet)")
    legend(config.COL_SAM2_HL,    "SAM2 mask",             f"t: {'on' if use_sam2 else 'off'}")
    legend(config.COL_VLM_BOX,    "VLM's own box")
    cv2.putText(panel, "Press H: record on/off", (12, y), FONT, 0.5, config.COL_HUD, 1, cv2.LINE_AA); y += 20
    cv2.putText(panel, "keys: c clear  x chat  q quit", (12, y), FONT, 0.44, (150, 150, 150), 1, cv2.LINE_AA)
    y += 10; cv2.line(panel, (0, y), (w, y), (70, 70, 70), 1); conv_top = y + 8

    maxchars = max(int((w - 26) / 9), 12)
    with S.lock:
        chat = list(S.chat); thinking = S.thinking
    lines = []
    for role, text in chat:
        text = to_ascii(text)
        lines.append(("You:" if role == "user" else "Scene:",
                      config.COL_CHAT_USER if role == "user" else config.COL_CHAT_MODEL))
        body = (205, 225, 255) if role == "user" else (225, 225, 225)
        for wl in (textwrap.wrap(text, maxchars) or [""]):
            lines.append((wl, body))
        lines.append(("", (0, 0, 0)))
    if thinking:
        lines.append(("Scene: thinking...", config.COL_CHAT_MODEL))
    if not lines:
        lines = [("press H, speak, press H.", (150, 150, 150)), ('e.g. "what do you see?"', (150, 150, 150))]

    yy = height - 14
    for text, col in reversed(lines):
        if yy < conv_top + 14:
            break
        indent = 12 if text.endswith(":") else 22
        cv2.putText(panel, text, (indent, yy), FONT, 0.5, col, 1, cv2.LINE_AA)
        yy -= 20
    return panel


def main():
    eyes = Eyes()

    def on_text(text):
        print(f"[chat] you:   {text}", flush=True)
        with S.lock:
            S.chat.append(("user", text)); S.thinking = True
            frame = None if S.frame is None else S.frame.copy()
            dets = list(S.bg_dets)

        # Highlight straight from the spoken words -- reliable, no VLM cooperation needed.
        phrase = parse_highlight(text)
        if phrase is not None:
            eyes.set_target(phrase or None)
            print(f"[highlight] target -> {phrase!r}", flush=True)
            with S.lock:
                S.target = phrase or None
                if not S.target:
                    S.hl_dets, S.hl_mask, S.vlm_box = [], None, None

        if frame is None:
            with S.lock: S.thinking = False
            return
        ans, tgt, box = vlm.ask(frame, text, dets)
        print(f"[chat] scene: {ans}", flush=True)
        with S.lock:
            S.chat.append(("model", ans)); S.thinking = False
            if box is not None: S.vlm_box = box
        if tgt and phrase != "":                         # VLM resolved/refined the referent (route highlight via Qwen3-VL)
            eyes.set_target(tgt)
            print(f"[highlight] target (via VLM) -> {tgt!r}", flush=True)
            with S.lock: S.target = tgt

    ears = Ears(on_text)
    cap = open_capture(config.INPUT)
    if not cap.isOpened():
        print("cannot open input:", config.INPUT); return

    threading.Thread(target=perception_worker, args=(eyes,), daemon=True).start()
    cv2.namedWindow(config.WIN_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)

    writer = None
    t_prev, fps, last_log = time.time(), 0.0, 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        with S.lock:
            S.frame = frame
            bg, hl, mask = list(S.bg_dets), list(S.hl_dets), S.hl_mask
            target, vbox = S.target, S.vlm_box
            use_sam2, show_bg = S.use_sam2, S.show_bg
            t_bg, t_hl = S.t_bg, S.t_hl

        disp = frame.copy()
        if show_bg:
            for d in bg:
                draw_box(disp, d["box"], config.COL_BACKGROUND, d["label"], 1)
        if mask is not None and use_sam2:
            if mask.shape[:2] != disp.shape[:2]:
                mask = cv2.resize(mask.astype("uint8"), (disp.shape[1], disp.shape[0]),
                                  interpolation=cv2.INTER_NEAREST).astype(bool)
            ov = disp.copy(); ov[mask] = config.COL_SAM2_HL
            cv2.addWeighted(ov, 0.45, disp, 0.55, 0, disp)
        for d in hl:
            draw_box(disp, d["box"], config.COL_YOLOE_HL, f'{target} {d["conf"]:.2f}', 2)
        if vbox:
            h, w = disp.shape[:2]
            bx = (int(vbox[0] * w), int(vbox[1] * h), int(vbox[2] * w), int(vbox[3] * h))
            draw_box(disp, bx, config.COL_VLM_BOX, "VLM", 2)

        canvas = cv2.hconcat([disp, render_chat(disp.shape[0], use_sam2, show_bg)])

        now = time.time(); fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-3); t_prev = now
        hud = f"{fps:4.1f} fps   {disp.shape[1]}x{disp.shape[0]}   {eyes.device}"
        if config.PERF:
            hud += f"   detect: bg {t_bg:.0f}ms hl {t_hl:.0f}ms"
        cv2.putText(canvas, hud, (10, 22), FONT, 0.55, config.COL_HUD, 1, cv2.LINE_AA)
        if config.PERF and now - last_log > 1.0:
            last_log = now
            print(f"[perf] display={fps:.1f}fps bg_detect={t_bg:.0f}ms highlight={t_hl:.0f}ms dev={eyes.device}", flush=True)

        if config.RECORD:
            if writer is None:
                writer = cv2.VideoWriter(config.RECORD, cv2.VideoWriter_fourcc(*"mp4v"),
                                         20, (canvas.shape[1], canvas.shape[0]))
                print("[llm_cv_scene] recording ->", config.RECORD)
            writer.write(canvas)

        cv2.imshow(config.WIN_NAME, canvas)
        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        elif k == ord('c'):
            with S.lock: S.target = None; S.vlm_box = None; S.hl_dets = []; S.hl_mask = None
            eyes.set_target(None)
        elif k == ord('t'):
            with S.lock: S.use_sam2 = not S.use_sam2
        elif k == ord('b'):
            with S.lock: S.show_bg = not S.show_bg
        elif k == ord('x'):
            with S.lock: S.chat.clear()

    S.running = False
    time.sleep(0.05)
    if writer:
        writer.release()
    cap.release(); cv2.destroyAllWindows(); ears.shutdown()


if __name__ == "__main__":
    main()
