"""Tests for overlay.py: the system status pane and the chat pane (width, scroll)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
import numpy as np

from overlay import render_chat, render_status


def _box_colour(panel, row):
    y = 50 + row * 28                         # first row baseline; a green row is 22 + 6 px tall
    return tuple(int(v) for v in panel[y - 5, 19])


def test_pane_has_the_frame_height_and_the_status_width():
    panel = render_status(config.STATUS_W, 480, [])
    assert panel.shape == (480, config.STATUS_W, 3)


def test_up_is_green_and_any_other_state_is_red():
    panel = render_status(config.STATUS_W, 480, [("gemma", "UP", ""), ("sam3", "UP", "")])
    assert _box_colour(panel, 0) == config.COL_STATUS_UP
    panel = render_status(config.STATUS_W, 480, [("gemma", "RECOVERING", "")])
    assert _box_colour(panel, 0) == config.COL_STATUS_DOWN
    for state in ("STARTING", "FAILED", "DOWN"):
        assert _box_colour(render_status(config.STATUS_W, 480, [("x", state, "")]), 0) == config.COL_STATUS_DOWN


def test_long_detail_and_many_rows_never_overflow():
    rows = [(f"system{i}", "FAILED", "exited with code 139; restart 3/3 " * 5) for i in range(40)]
    panel = render_status(config.STATUS_W, 300, rows)
    assert panel.shape == (300, config.STATUS_W, 3)


def test_status_pane_takes_its_width_from_the_caller():
    assert render_status(123, 200, []).shape == (200, 123, 3)


def test_chat_pane_takes_the_width_it_is_given():
    assert render_chat(700, 300, [], False, False, None).shape == (300, 700, 3)


def test_scrolling_hides_the_newest_rows():
    chat = [("user", f"line {i}", "user") for i in range(30)]
    following = render_chat(700, 300, chat, False, False, None, scroll=0)
    scrolled = render_chat(700, 300, chat, False, False, None, scroll=6)
    assert following.shape == scrolled.shape and not np.array_equal(following, scrolled)
    assert np.array_equal(render_chat(700, 300, chat, False, False, None, scroll=10**6),
                          render_chat(700, 300, chat, False, False, None, scroll=len(chat) * 2 - 2))   # clamped



def test_draw_box_draws_the_box_and_its_label():
    from overlay import draw_box
    img = np.zeros((60, 60, 3), np.uint8)
    draw_box(img, (10, 20, 40, 50), (0, 255, 0), label="car")
    assert tuple(img[20, 25]) == (0, 255, 0)                         # the top edge
    assert img[5:18, 10:40].any()                                   # the label above the box


def test_chat_kind_classifies_generic_lines():
    from overlay import chat_kind
    assert chat_kind("rejected -- no action") == "reject"
    assert chat_kind("Highlighting: chair") == "action"
    assert chat_kind("ספרתי 3: chairs") == "answer"
    assert chat_kind("a room with two chairs") == "scene"
