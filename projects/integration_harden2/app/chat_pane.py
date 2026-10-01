"""Chat-pane renderer for the live scene window. PURE rendering: no app state, no
threads. `render_chat` takes a snapshot of the chat and returns a BGR panel; the caller
holds the lock and passes the snapshot in. The pane is a header (top-down) then the
conversation (bottom-up) as a tag column + value, in TrueType through PIL."""
import numpy as np
from bidi.algorithm import get_display
from PIL import Image, ImageDraw

import config
from app.chat_rows import CHAT_COLOURS, chat_header, group_turns, turn_rows
from app.draw import FONT_HE, FONT_TAG, FONT_VAL, PANE_GROUND, RAQM, wrap_px

# the colours and the layout live in config (owner D8 a)
_TAG_COL = config.COL_CHAT_TAG
_RULE_COL = config.COL_CHAT_RULE
_HINT_COL = config.COL_CHAT_HINT
_MARGIN = config.CHAT_MARGIN
_TAG_RIGHT = config.CHAT_TAG_RIGHT
_VALUE_X = config.CHAT_VALUE_X
_HEADER_LINE = config.CHAT_HEADER_LINE
_ROW_LINE = config.CHAT_ROW_LINE


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

    header = chat_header(session_dir, killed)
    conv_top = _MARGIN + _HEADER_LINE * len(header) + 8

    rows = turn_rows(group_turns(chat, thinking))
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
        conv_top += _HEADER_LINE
    return _draw_pane(panel, header, rows, conv_top, height)


# ==================================== pane drawing ====================================
def _draw_pane(panel, header, rows, conv_top, height):
    """Draw the pane: a header (top-down) then the conversation (bottom-up) as a tag
    column + value.
    header: list of (text, bgr_color, fontkey).
    rows: (tag, value, bgr_color, rtl) or None (turn split).
    Fonts per element: Hebrew values = DejaVuSans, English values = Ubuntu,
    tags = DejaVuSansMono.
    Hebrew values are right-aligned (RTL); English values start after the tag."""
    font = None
    vfont = None
    wrapped = []
    ly = 0
    visual = ""
    text_w = 0
    tag_w = 0
    width = panel.shape[1]
    fonts = {"tag": FONT_TAG, "val": FONT_VAL, "he": FONT_HE}
    img = Image.fromarray(panel)
    draw = ImageDraw.Draw(img)
    y = _MARGIN
    yy = height - config.CHAT_BOTTOM - FONT_HE.size

    for text, col, fontkey in header:                          # header top-down
        font = fonts.get(fontkey, FONT_VAL)
        draw.text((_MARGIN, y), text, font=font, fill=tuple(int(x) for x in col))
        y += _HEADER_LINE
    draw.line((10, conv_top - 8, width - 10, conv_top - 8), fill=_RULE_COL)

    for row in reversed(rows):
        if yy < conv_top:
            break
        if row is None:                                        # turn separator
            draw.line((10, yy + 13, width - 10, yy + 13), fill=_RULE_COL)
            yy -= config.CHAT_TURN_GAP
            continue

        tag, value, col, rtl = row
        col = tuple(int(x) for x in col)
        vfont = FONT_HE if rtl else FONT_VAL
        wrapped = wrap_px(value, width - _VALUE_X - _MARGIN, vfont)

        # bottom wrapped line first
        for j, wrapped_line in enumerate(reversed(wrapped)):
            ly = yy - j * _ROW_LINE
            if not rtl:
                draw.text((_VALUE_X, ly), wrapped_line, font=vfont, fill=col)
                continue
            visual = wrapped_line if RAQM else get_display(wrapped_line)
            text_w = draw.textlength(visual, font=vfont)
            draw.text(
                (max(_VALUE_X, width - text_w - _MARGIN), ly),
                visual,
                font=vfont,
                fill=col
            )

        # tag on the row's TOP line, right-aligned, mono
        if tag:
            tag_w = draw.textlength(tag, font=FONT_TAG)
            draw.text(
                (max(6, _TAG_RIGHT - tag_w), yy - (len(wrapped) - 1) * _ROW_LINE),
                tag,
                font=FONT_TAG,
                fill=_TAG_COL
            )
        yy -= _ROW_LINE * len(wrapped)
    return np.array(img)
