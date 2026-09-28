"""Status-pane renderer for the live scene window: one row per subsystem, coloured by its
state. PURE rendering: no app state, no threads."""
import textwrap

import cv2
import numpy as np

import config
from app.draw import FONT, PANE_GROUND, ascii_only
from system.status import UP, WAITING

# any other state draws red
STATUS_COLOURS = {UP: config.COL_STATUS_UP, WAITING: config.COL_STATUS_WAITING}


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
