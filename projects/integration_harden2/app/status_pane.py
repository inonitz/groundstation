"""Status-pane renderer for the live scene window: one row per subsystem, coloured by its
state. PURE rendering: no app state, no threads."""
import textwrap

import cv2
import numpy as np

import config
from app.draw import FONT, PANE_GROUND, ascii_only
from runtime.status import UP, WAITING

# any other state draws red
STATUS_COLOURS = {UP: config.COL_STATUS_UP, WAITING: config.COL_STATUS_WAITING}


# ==================================== status pane ====================================
def render_status(width, height, rows):
    """The system status pane (owner rulings 2026-09-22/23): one row per subsystem; a
    green box when UP, an orange box when WAITING, a red box in every other state; the
    state name; and the detail wrapped under every row that is not UP.
    rows: a runtime.status snapshot, [(system, state, detail), ...].
    Touches no shared state."""
    col = None
    state_w = 0
    y = config.STATUS_FIRST_ROW_Y
    margin = config.STATUS_MARGIN
    text_x = config.STATUS_TEXT_X
    panel = np.empty((height, width, 3), np.uint8)
    panel[:] = PANE_GROUND

    cv2.putText(
        panel,
        "SYSTEM STATUS",
        (margin, 26),
        FONT,
        0.55,
        config.COL_HUD,
        1,
        cv2.LINE_AA
    )
    for system, state, detail in rows:
        col = STATUS_COLOURS.get(state, config.COL_STATUS_DOWN)
        cv2.rectangle(panel, (margin, y - 12), (margin + 14, y + 2), col, -1)
        cv2.putText(
            panel,
            ascii_only(system),
            (text_x, y),
            FONT,
            0.5,
            config.COL_STATUS_NAME,
            1,
            cv2.LINE_AA
        )
        (state_w, _), _ = cv2.getTextSize(state, FONT, 0.45, 1)
        cv2.putText(
            panel,
            state,
            (width - margin - state_w, y),
            FONT,
            0.45,
            col,
            1,
            cv2.LINE_AA
        )
        y += config.STATUS_ROW_LINE

        # The detail explains a row that is not UP: at most 3 wrapped lines.
        if state != UP and detail:
            for line in detail_lines(detail):
                cv2.putText(
                    panel,
                    line,
                    (text_x, y),
                    FONT,
                    0.4,
                    config.COL_STATUS_DETAIL,
                    1,
                    cv2.LINE_AA
                )
                y += config.STATUS_DETAIL_LINE
        y += config.STATUS_ROW_GAP
        if y > height - 10:
            break
    return panel


def detail_lines(detail):
    """The detail, wrapped, at most config.STATUS_DETAIL_LINES lines."""
    lines = textwrap.wrap(ascii_only(detail), config.STATUS_DETAIL_CHARS)
    return lines[:config.STATUS_DETAIL_LINES]
