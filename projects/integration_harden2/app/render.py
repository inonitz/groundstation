#!/usr/bin/env python3
"""Chat-pane and status-pane renderer for the live scene window. PURE rendering: no app
state, no threads. `render_chat` takes a snapshot of the chat and returns a BGR panel;
the caller holds the lock and passes the snapshot in. Font composition (owner-inspected
2026-09-12, mockup tools/ui-mockups/live-pane.html): DejaVu Sans for Hebrew, DejaVu Sans
Mono for the tag column, Ubuntu Regular for English values + header. Degrades to
ASCII-only cv2 Hershey text if PIL/bidi are missing."""
import importlib.util
import os
import textwrap

import cv2
import numpy as np

import config
from system.status import UP, WAITING
from system.fatal import die
from util.hebrew import is_hebrew

FONT = cv2.FONT_HERSHEY_SIMPLEX

# ================================== layout + colours ==================================
_TAG_COL = (163, 149, 139)   # dim tag column (BGR = mockup #8b95a3)
PANE_GROUND = (31, 25, 22)  # the dark ground of the status + chat panes (#16191f)
_TAG_RIGHT = 66              # tags are right-aligned, ending at this x
_VALUE_X = 76               # values start at this x
_RULE_COL = (59, 49, 43)     # the header rule and the turn separators

CHAT_COLOURS = {
    "you": (120, 210, 255),
    "light": (240, 235, 231),
    "dim": (163, 149, 139),
    "green": (100, 220, 60),
    "amber": (41, 180, 240),
    "model": (176, 235, 160),
    "red": (107, 107, 255),
    "spoken": (74, 210, 255),
    "cmd": (245, 235, 150),
}
_HINT_COL = (150, 150, 150)   # the empty-chat hint

# Rows switch on the KIND tagged at the write site -- no startswith, no partition.
_KIND_TAG = {
    "user": "You",
    "scene": "Scene",
    "spoken": "Spoken",
    "answer": "Answer",
    "action": "Action",
    "reject": "reject",
    "miss": "miss",
    "en": "En",
    "kind_hl": "Kind",
    "kind_meta": "Kind",
    "action_meta": "Action",
    "sam3": "SAM3",
    "cmd_head": "Cmds",
    "cmd": "",
}
# The colour of each kind. kind_hl is coloured by the turn's highlight outcome; a kind
# not listed here (scene, answer) is a model line.
_KIND_COLOUR = {
    "action": "green",
    "sam3": "green",
    "reject": "red",
    "miss": "amber",
    "user": "you",
    "spoken": "spoken",
    "cmd_head": "cmd",
    "cmd": "cmd",
    "en": "light",
    "kind_meta": "light",
    "action_meta": "light",
}
# Kinds with a fixed direction; every other kind is RTL when its text is mostly Hebrew.
_RTL_FIXED = {
    "answer": True,
    "action": False,
    "kind_hl": False,
    "cmd_head": False,
    "cmd": False,
}

PLANNER_NAMES = {"gemma4": "Gemma-4-E4B"}

# any other state draws red
STATUS_COLOURS = {UP: config.COL_STATUS_UP, WAITING: config.COL_STATUS_WAITING}

# ======================================= fonts =======================================
# Hebrew/RTL for the chat overlay. OpenCV's Hershey font is ASCII-only, so Hebrew is
# drawn with a TrueType font (DejaVuSans has Hebrew glyphs) and python-bidi for correct
# right-to-left order. PIL/bidi are optional (checked without importing -> no try on
# the import); a MISSING FONT is fatal.
_HAVE_HE = (
    importlib.util.find_spec("PIL") is not None
    and importlib.util.find_spec("bidi") is not None
)
if _HAVE_HE:
    from PIL import Image, ImageDraw, ImageFont, features as _pil_features
    from bidi.algorithm import get_display
    _SZ = config.HE_FONT_SIZE
    # The Hebrew font is REQUIRED (a missing one is fatal, per the owner). Ubuntu
    # (English) and the mono font (tags) are optional niceties: fall back to the Hebrew
    # font if absent. os.path.exists, no try.
    _HE_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not os.path.exists(_HE_PATH):
        die(f"overlay Hebrew font missing: {_HE_PATH} (apt-get install fonts-dejavu)")
    _FONT_HE = ImageFont.truetype(_HE_PATH, _SZ)

    _VAL_PATH = "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"
    _FONT_VAL = _FONT_HE
    if os.path.exists(_VAL_PATH):
        _FONT_VAL = ImageFont.truetype(_VAL_PATH, _SZ)

    _TAG_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    _FONT_TAG = _FONT_HE
    if os.path.exists(_TAG_PATH):
        _FONT_TAG = ImageFont.truetype(_TAG_PATH, _SZ - 2)

    # Raqm does bidi natively -> do NOT pre-reverse
    _RAQM = bool(_pil_features.check("raqm"))
else:
    print("[overlay] Hebrew overlay off (PIL/bidi missing); ASCII fallback", flush=True)


# ==================================== text helpers ====================================
def ascii_only(s):
    """Drop non-ASCII characters; cv2.putText cannot draw them."""
    return (s or "").encode("ascii", "ignore").decode("ascii")


def _is_rtl(s):
    """A line renders RTL only if it is PREDOMINANTLY Hebrew. A mixed line (Hebrew +
    English words + numbers) lays out badly under PIL bidi, so we keep it LTR -- and
    system messages are single-script."""
    heb = sum(1 for c in s if is_hebrew(c))
    lat = sum(1 for c in s if c.isascii() and c.isalpha())
    return heb > lat


def _wrap_px(text, maxpx, font=None):
    """Wrap to fit maxpx using the real font metrics (per-element font). PIL path
    only. A line break in the text starts a new line: PIL cannot measure multi-line
    text (a transcript with a line break crashed the app, 2026-09-25)."""
    lines = []
    font = font or _FONT_HE
    if not text:
        return [""]

    for paragraph in text.split("\n"):
        lines.extend(_wrap_line(paragraph, maxpx, font))
    return lines or [""]


def _wrap_line(text, maxpx, font):
    """Wrap one line (no line break inside) at spaces to fit maxpx."""
    trial = ""
    cur = ""
    lines = []

    for wd in text.split(" "):
        trial = (cur + " " + wd).strip()
        if not cur or font.getlength(trial) <= maxpx:
            cur = trial
            continue
        lines.append(cur)
        cur = wd
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_box(img, box, color, label=None, thick=2):
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)
    if label:
        cv2.putText(img, label, (x1, max(y1 - 6, 12)), FONT, 0.5, color, 1, cv2.LINE_AA)
    return


# ==================================== chat model ====================================
def _model_lines():
    """The live model stack, one (label, value) per subsystem, read from the env/config
    so it reflects what is actually wired -- not a hardcoded string. harden2 is
    single-stack (Gemma 4 / SAM3 / whisper); the env knobs still drive these, so a
    future swap shows here automatically."""
    planner = PLANNER_NAMES.get(config.PLANNER, config.PLANNER)
    eyes = os.path.basename(config.SAM3_MODEL_DIR)

    asr = config.ASR_MODEL_PATH
    if "ivrit" in asr:
        ears = "whisper-ivrit-v3"
    elif asr:
        ears = os.path.basename(os.path.dirname(asr)) or "whisper"
    else:
        ears = "whisper-ivrit-v3"
    return [("brain", planner), ("eyes", eyes), ("ears", ears)]


def _is_miss(t):
    """A model line reporting the target is not present (tags miss +
    the red status light)."""
    return (
        t.startswith('no "')
        or t.startswith("I don't see")
        or t.startswith("\u05dc\u05d0 \u05e8\u05d5\u05d0\u05d4")
        or t.startswith("\u05dc\u05d0 \u05de\u05e6\u05d0\u05ea\u05d9")
    )


def chat_kind(text):
    """Classify a GENERIC model say() line to its kind. Used ONLY at the say() write
    site, where the kind is not known structurally; every other write site tags
    directly. Overlay never re-parses."""
    if text.startswith("rejected -- "):
        return "reject"
    if _is_miss(text):
        return "miss"
    if text.startswith("Highlighting:"):
        return "action"
    if text.startswith("\u05e1\u05e4\u05e8\u05ea\u05d9"):
        return "answer"
    return "scene"


def _chat_header(session_dir, killed):
    """The header: title (Ubuntu), then ONE line per subsystem derived from the live
    env/config (mono), then the dump path + key hints. Each line follows the real
    config, so it never lies -- if the env names a different backend, the line changes
    with it. "·" is the mid-line dot (not ".")."""
    dump = ""
    C = CHAT_COLOURS

    header = [("MVD harden2 — Hebrew voice drone", C["light"], "val")]
    for label, value in _model_lines():
        header.append((f"{label:<6}{value}", C["dim"], "tag"))

    if session_dir:
        dump = "/".join(session_dir.rstrip("/").split("/")[-2:])
        header.append(("dump: " + ascii_only(dump)[:54], C["dim"], "tag"))

    header.append((
        f"{config.PUSH_TO_TALK_KEY_NAME} talk  ·  {config.KILL_KEY_NAME} kill  ·  "
        "c clear  ·  [ ] or wheel scroll  ·  q quit",
        C["dim"],
        "tag"
    ))
    if killed:
        header.append((
            f"MANUAL OVERRIDE — press {config.KILL_KEY_NAME} to re-arm",
            C["red"],
            "val"
        ))
    return header


def _group_turns(chat, thinking):
    """Group the flat chat into turns. A turn STARTS at a user line and runs to the next
    user line. Highlight + describe results land SECONDS later from a worker thread, so
    they must stay in the turn that produced them. The old ("meta","") separator was
    emitted synchronously BEFORE those async lines -- it split a turn from its own
    result, so a miss bled into the next turn's Kind colour. Grouping on the user line
    fixes that; the legacy separator row is ignored."""
    turns = []
    cur = []

    for role, text, kind in chat:
        if role == "user":
            if cur:
                turns.append(cur)
            cur = [(role, text, kind)]
            continue
        cur.append((role, text, kind))
    if cur:
        turns.append(cur)

    # "thinking..." belongs to the live (last) turn
    if not thinking:
        return turns
    if turns:
        turns[-1].append(("model", "thinking...", "scene"))
    else:
        turns.append([("model", "thinking...", "scene")])
    return turns


def _highlight_colour(lines):
    """The colour of a turn's highlight outcome: red on a miss, green on a hit, amber
    while it is still open."""
    fail = any(k == "miss" for _r, _t, k in lines)
    ok = any(k in ("action", "sam3") for _r, _t, k in lines)
    if fail:
        return CHAT_COLOURS["red"]
    if ok:
        return CHAT_COLOURS["green"]
    return CHAT_COLOURS["amber"]


def _chat_rows(turns):
    """The pane rows: (tag, value, bgr_color, rtl) per line; None between turns."""
    hl_col = None
    col = None
    rtl = False
    rows = []

    for ti, lines in enumerate(turns):
        if ti:
            rows.append(None)                                 # divider between turns

        hl_col = _highlight_colour(lines)
        for _role, text, kind in lines:
            if kind == "kind_hl":
                col = hl_col
            else:
                col = CHAT_COLOURS[_KIND_COLOUR.get(kind, "model")]
            rtl = _RTL_FIXED.get(kind, _is_rtl(text))
            rows.append((_KIND_TAG.get(kind, "Scene"), text, col, rtl))
    return rows


def render_chat(width, height, chat, thinking, killed, session_dir, scroll=0):
    """Build the chat panel from a SNAPSHOT. The caller holds S.lock and passes
    chat/thinking/killed; this function touches no shared state.
    chat: list of (role, text, kind). A turn runs from one user line to the next; async
    results (highlight/describe land from a worker thread) stay in their turn.
    scroll: how many of the newest rows to skip (0 = follow the newest). The pane
    draws bottom-up."""
    ptt = config.PUSH_TO_TALK_KEY_NAME
    panel = np.empty((height, width, 3), np.uint8)
    panel[:] = PANE_GROUND

    header = _chat_header(session_dir, killed)
    conv_top = 12 + 19 * len(header) + 8

    rows = _chat_rows(_group_turns(chat, thinking))
    if not rows:
        rows = [
            ("", f"press {ptt}, speak, press {ptt}.", _HINT_COL, False),
            ("", 'e.g. "highlight the red car"', _HINT_COL, False),
        ]

    scroll = max(0, min(scroll, len(rows) - 1))
    if scroll:
        rows = rows[:len(rows) - scroll]
        header.append((
            f"scrolled up {scroll} rows  ·  ] to go back down",
            CHAT_COLOURS["amber"],
            "tag"
        ))
        conv_top += 19
    return _draw_pane(panel, header, rows, conv_top, height)


# ==================================== pane drawing ====================================
def _draw_pane(panel, header, rows, conv_top, height):
    """Draw the pane: a header (top-down) then the conversation (bottom-up) as a tag
    column + value.
    header: list of (text, bgr_color, fontkey).
    rows: (tag, value, bgr_color, rtl) or None (turn split).
    Fonts per element: Hebrew values = DejaVuSans, English values = Ubuntu,
    tags = DejaVuSansMono.
    Hebrew values are right-aligned (RTL); English values start after the tag.
    Falls back to cv2 Hershey."""
    if not _HAVE_HE:
        return _draw_pane_ascii(panel, header, rows, conv_top, height)
    return _draw_pane_pil(panel, header, rows, conv_top, height)


def _draw_pane_ascii(panel, header, rows, conv_top, height):
    """Fallback pane in cv2 Hershey (ASCII only), used when PIL/bidi are missing."""
    tag_w = 0
    y = 22
    yy = height - 14

    for text, col, _fontkey in header:
        cv2.putText(
            panel,
            ascii_only(text),
            (12, y),
            FONT,
            0.5,
            tuple(int(x) for x in col),
            1,
            cv2.LINE_AA
        )
        y += 19

    for row in reversed(rows):
        if yy < conv_top + 14:
            break
        if row is None:
            yy -= 11
            continue

        tag, value, col, _rtl = row
        col = tuple(int(x) for x in col)
        if tag:
            (tag_w, _), _ = cv2.getTextSize(ascii_only(tag), FONT, 0.42, 1)
            cv2.putText(
                panel,
                ascii_only(tag),
                (max(6, _TAG_RIGHT - tag_w), yy),
                FONT,
                0.42,
                _TAG_COL,
                1,
                cv2.LINE_AA
            )
        cv2.putText(
            panel,
            ascii_only(value),
            (_VALUE_X, yy),
            FONT,
            0.46,
            col,
            1,
            cv2.LINE_AA
        )
        yy -= 21
    return panel


def _draw_pane_pil(panel, header, rows, conv_top, height):
    """The full pane in PIL: TrueType Hebrew (RTL) + Ubuntu English values + mono
    tags."""
    font = None
    vfont = None
    wrapped = []
    ly = 0
    visual = ""
    text_w = 0
    tag_w = 0
    width = panel.shape[1]
    fonts = {"tag": _FONT_TAG, "val": _FONT_VAL, "he": _FONT_HE}
    img = Image.fromarray(panel)
    draw = ImageDraw.Draw(img)
    y = 12
    yy = height - 14 - _FONT_HE.size

    for text, col, fontkey in header:                          # header top-down
        font = fonts.get(fontkey, _FONT_VAL)
        draw.text((12, y), text, font=font, fill=tuple(int(x) for x in col))
        y += 19
    draw.line((10, conv_top - 8, width - 10, conv_top - 8), fill=_RULE_COL)

    for row in reversed(rows):
        if yy < conv_top:
            break
        if row is None:                                        # turn separator
            draw.line((10, yy + 13, width - 10, yy + 13), fill=_RULE_COL)
            yy -= 14
            continue

        tag, value, col, rtl = row
        col = tuple(int(x) for x in col)
        vfont = _FONT_HE if rtl else _FONT_VAL
        wrapped = _wrap_px(value, width - _VALUE_X - 12, vfont)

        # bottom wrapped line first
        for j, wrapped_line in enumerate(reversed(wrapped)):
            ly = yy - j * 21
            if not rtl:
                draw.text((_VALUE_X, ly), wrapped_line, font=vfont, fill=col)
                continue
            visual = wrapped_line if _RAQM else get_display(wrapped_line)
            text_w = draw.textlength(visual, font=vfont)
            draw.text(
                (max(_VALUE_X, width - text_w - 12), ly),
                visual,
                font=vfont,
                fill=col
            )

        # tag on the row's TOP line, right-aligned, mono
        if tag:
            tag_w = draw.textlength(tag, font=_FONT_TAG)
            draw.text(
                (max(6, _TAG_RIGHT - tag_w), yy - (len(wrapped) - 1) * 21),
                tag,
                font=_FONT_TAG,
                fill=_TAG_COL
            )
        yy -= 21 * len(wrapped)
    return np.array(img)


# ==================================== status pane ====================================
def render_status(width, height, rows):
    """The system status pane (owner rulings 2026-09-22/23): one row per subsystem; a
    green box when UP, an orange box when WAITING, a red box in every other state; the
    state name; and the detail wrapped under every row that is not UP.
    rows: a system.status snapshot, [(system, state, detail), ...].
    Touches no shared state."""
    col = None
    state_w = 0
    y = 50
    panel = np.empty((height, width, 3), np.uint8)
    panel[:] = PANE_GROUND

    cv2.putText(
        panel,
        "SYSTEM STATUS",
        (12, 26),
        FONT,
        0.55,
        config.COL_HUD,
        1,
        cv2.LINE_AA
    )
    for system, state, detail in rows:
        col = STATUS_COLOURS.get(state, config.COL_STATUS_DOWN)
        cv2.rectangle(panel, (12, y - 12), (26, y + 2), col, -1)
        cv2.putText(
            panel,
            ascii_only(system),
            (36, y),
            FONT,
            0.5,
            (235, 235, 235),
            1,
            cv2.LINE_AA
        )
        (state_w, _), _ = cv2.getTextSize(state, FONT, 0.45, 1)
        cv2.putText(
            panel,
            state,
            (width - 12 - state_w, y),
            FONT,
            0.45,
            col,
            1,
            cv2.LINE_AA
        )
        y += 22

        # The detail explains a row that is not UP: at most 3 wrapped lines.
        if state != UP and detail:
            for line in textwrap.wrap(ascii_only(detail), 38)[:3]:
                cv2.putText(
                    panel,
                    line,
                    (36, y),
                    FONT,
                    0.4,
                    (170, 170, 170),
                    1,
                    cv2.LINE_AA
                )
                y += 17
        y += 6
        if y > height - 10:
            break
    return panel
