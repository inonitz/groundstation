"""The screen: the ONE module that draws. Camera full width on top; below it the status
pane and the chat pane side by side (owner layout 2026-09-22). Window keys and the mouse
wheel are read here. The kill key is NOT here: it is global (app/keys.py)."""
import os
import time

import cv2
import numpy as np

import config
from app.render import FONT, draw_box, render_chat, render_status
from app.state import S
from log.perf import NO_PERF
from video.video import source_kind

WINDOW = "integration:mvd"
HUD_SHADOW = (0, 0, 0)              # a shadow under HUD text: readable on a white wall
PROMPT_COLOUR = (163, 149, 139)
KEY_ESC = 27
QUIT_KEYS = (KEY_ESC, ord("q"))
SCROLL_ROWS = 3                     # chat rows per wheel notch or [ / ] press


# ---- The window loop ----
class _FrameTimer:
    """Sums the loop's parts and records one "frame" event per second: fps and the mean
    ms of reading a frame, drawing (overlays + panes) and showing it (imshow +
    waitKey)."""

    def __init__(self, perf):
        self._perf = perf
        self._start = time.monotonic()
        self._frames = 0
        self._sums = {"read": 0.0, "draw": 0.0, "show": 0.0}
        return

    def add(self, read_s, draw_s, show_s):
        self._frames += 1
        self._sums["read"] += read_s
        self._sums["draw"] += draw_s
        self._sums["show"] += show_s

        elapsed = time.monotonic() - self._start
        if elapsed < 1.0:
            return

        n = self._frames
        self._perf.record(
            "frame",
            sum(self._sums.values()) / n * 1000,
            fps=round(n / elapsed, 1),
            read_ms=round(self._sums["read"] / n * 1000, 1),
            draw_ms=round(self._sums["draw"] / n * 1000, 1),
            show_ms=round(self._sums["show"] / n * 1000, 1)
        )
        self.__init__(self._perf)
        return


class Ui:
    """@video: the Video module (frames). @board: the status board (the status pane).
    @session_dir: shown in the chat pane's header. @manual_on: () -> bool, the manual
    mode banner (a callback: the screen never holds control)."""

    def __init__(self, video, board, session_dir, manual_on, perf=NO_PERF):
        self._perf = perf
        self._video = video
        self._board = board
        self._session_dir = session_dir
        self._manual_on = manual_on
        self._src_label = source_label(video.source)
        self._dji_text = dji_label()
        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)   # content size, no empty margins
        cv2.setMouseCallback(WINDOW, on_mouse)          # the wheel scrolls the chat
        return

    def close(self):
        """Close the window. The last waitKey lets the window system process it."""
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        return

    def run(self, on_clear):
        """Draw frames and handle keys until quit. on_clear runs on the c key. A live
        source never "ends": a missed read is a hiccup, so it shows "waiting"."""
        previous = time.time()
        now = 0.0
        fps = 0.0
        misses = 0
        ok = False
        frame = None
        boxes = []
        masks = []
        use_masks = False
        display = None
        canvas = None
        t0 = 0.0
        t_read = 0.0
        t_draw = 0.0
        timer = _FrameTimer(self._perf)

        while True:
            t0 = time.monotonic()
            ok, frame = self._video.read()
            t_read = time.monotonic()

            if not ok:
                misses += 1
                if not self._video.live and misses > config.READ_RETRY:
                    print("[ui] input ended", flush=True)
                    return
                if self._show_waiting():
                    return
                continue

            misses = 0
            with S.lock:
                boxes = list(S.hl_dets)
                masks = list(S.hl_masks)
                use_masks = S.use_sam

            display = frame.copy()
            draw_overlays(display, boxes, masks, use_masks)

            now = time.time()
            fps = 0.9 * fps + 0.1 / max(now - previous, 1e-3)
            previous = now

            canvas = self._canvas(display, fps)
            t_draw = time.monotonic()
            cv2.imshow(WINDOW, canvas)
            key = cv2.waitKey(1) & 0xFF
            timer.add(t_read - t0, t_draw - t_read, time.monotonic() - t_draw)
            if handle_key(key, on_clear):
                return
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                return

    def _show_waiting(self):
        """The 'waiting for video' placeholder WITH the status and chat panes, so
        start-up progress (Gemma STARTING, ...) shows before the first frame. -> True on
        quit."""
        placeholder = np.zeros((config.CAM_H, config.CAM_W, 3), np.uint8)
        cv2.putText(
            placeholder,
            "waiting for video...",
            (30, config.CAM_H // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 200, 255),
            2
        )
        cv2.imshow(WINDOW, self._canvas(placeholder, 0.0))
        return (cv2.waitKey(50) & 0xFF) in QUIT_KEYS

    def _canvas(self, display, fps):
        return compose_canvas(
            display,
            fps,
            self._src_label,
            self._dji_text,
            self._session_dir,
            self._board,
            self._manual_on()
        )


# ---- HUD labels ----
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


def dji_label():
    """A short HUD label for the phone-app target (mock or real)."""
    prefix = "REAL " if config.DJI_REAL else "mock "
    return prefix + config.DJI_HOST + ":" + str(config.DJI_PORT)


# ---- Drawing ----
def tint_masks(display, masks):
    """Blend every mask onto display in the mask colour. A mask of another size (a
    frame of another resolution) is scaled to the display first."""
    blended = display.copy()
    size = (display.shape[1], display.shape[0])

    for mask in masks:
        if mask.shape[:2] != display.shape[:2]:
            mask = cv2.resize(
                mask.astype("uint8"),
                size,
                interpolation=cv2.INTER_NEAREST
            ).astype(bool)
        blended[mask] = config.COL_SAM2_HL

    cv2.addWeighted(blended, 0.45, display, 0.55, 0, display)
    return


def draw_overlays(display, boxes, masks, use_masks):
    """Draw the mask tint and the highlight boxes onto display."""
    label = ""

    if use_masks and masks:
        tint_masks(display, masks)

    for det in boxes:
        label = f'{det["label"]} {det["conf"]:.2f}'
        draw_box(display, det["box"], config.COL_YOLOE_HL, label, 2)
    return


def compose_canvas(display, fps, src_label, dji_text, session_dir, board, manual):
    """The camera full width on top; below it the status pane and the chat pane side by
    side (owner layout 2026-09-22). The HUD and the talk prompt sit on the camera
    part."""
    with S.lock:
        chat = list(S.chat)
        thinking = S.thinking
        scroll = S.chat_scroll

    width = display.shape[1]
    status_panel = render_status(config.STATUS_W, config.BOTTOM_H, board.snapshot())
    chat_panel = render_chat(
        width - config.STATUS_W,
        config.BOTTOM_H,
        chat,
        thinking,
        manual,
        session_dir,
        scroll
    )
    canvas = cv2.vconcat([display, cv2.hconcat([status_panel, chat_panel])])

    hud = f"{fps:4.1f} fps | {src_label} | {dji_text}"
    cv2.putText(canvas, hud, (10, 22), FONT, 0.55, HUD_SHADOW, 3, cv2.LINE_AA)
    cv2.putText(canvas, hud, (10, 22), FONT, 0.55, config.COL_HUD, 1, cv2.LINE_AA)

    ptt = config.PUSH_TO_TALK_KEY_NAME
    prompt = f"{ptt} to talk ({ptt}, speak, {ptt})"
    at = (10, display.shape[0] - 12)
    cv2.putText(canvas, prompt, at, FONT, 0.48, HUD_SHADOW, 3, cv2.LINE_AA)
    cv2.putText(canvas, prompt, at, FONT, 0.48, PROMPT_COLOUR, 1, cv2.LINE_AA)
    return canvas


# ---- Input: mouse wheel and window keys ----
def on_mouse(event, _x, _y, flags, _param):
    """The mouse wheel scrolls the chat: up = older rows, down = back toward the
    newest."""
    if event != cv2.EVENT_MOUSEWHEEL:
        return

    # the wheel delta is the sign of flags' upper 16 bits
    # (cv2 4.11 has no getMouseWheelDelta)
    step = SCROLL_ROWS if flags > 0 else -SCROLL_ROWS
    with S.lock:
        S.chat_scroll = max(0, S.chat_scroll + step)
    return


def handle_key(key, on_clear):
    """Apply one window key. -> True when the app should quit. c = clear the highlight, t
    = masks on/off, [ / ] = scroll the chat, x = clear the chat. The kill key is NOT
    here: it is global (app/keys.py)."""
    if key in QUIT_KEYS:
        return True

    if key == ord("c"):
        on_clear()
    elif key == ord("t"):
        with S.lock:
            S.use_sam = not S.use_sam
    elif key == ord("["):
        with S.lock:
            S.chat_scroll += SCROLL_ROWS
    elif key == ord("]"):
        with S.lock:
            S.chat_scroll = max(0, S.chat_scroll - SCROLL_ROWS)
    elif key == ord("x"):
        with S.lock:
            S.chat.clear()
    return False
