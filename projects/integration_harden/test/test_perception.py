"""Tests for the perception engine. No models, no GPU: the engine's backends are fakes and the
VLM reply parser is fed canned text."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from perception import PerceptionEngine, parse_highlight, scale_vlm_box, selftest
from perception import vlm_client


def test_engine_selftest_clean():
    assert selftest() == []


def test_parse_highlight_forms():
    assert parse_highlight("highlight the red backpack please") == "red backpack"
    assert parse_highlight("where is my guitar case") == "guitar case"
    assert parse_highlight("track that person in the black hat") == "person in the black hat"
    assert parse_highlight("never mind") == ""
    assert parse_highlight("what do you see right now") is None


def test_relative_gate_keeps_near_peers():
    frame = np.zeros((100, 100, 3), np.uint8)
    two_windows = [{"label": "window", "conf": 0.88, "box": (10, 10, 30, 30)},
                   {"label": "window", "conf": 0.85, "box": (50, 50, 70, 70)}]
    eng = PerceptionEngine(detect=lambda f, p, c: two_windows,
                           mask_for_box=lambda f, b: None, vlm_ask=None)
    dets, masks, dbg = eng.highlight_step(frame, "window", use_sam=False)
    assert len(dets) == 2                       # peers within 65% of the top both survive


def test_full_frame_box_without_mask_is_dropped():
    frame = np.zeros((100, 100, 3), np.uint8)
    eng = PerceptionEngine(detect=lambda f, p, c: [{"label": "x", "conf": 0.9, "box": (0, 0, 99, 99)}],
                           mask_for_box=lambda f, b: None, vlm_ask=None)
    dets, masks, _ = eng.highlight_step(frame, "x")
    assert dets == [] and masks == []


def test_vlm_reply_parsing():
    long_, tgt, box, short = vlm_client.parse_reply(
        "LONG RESPONSE: Two people near a car.\nSHORT RESPONSE: Two people.\n"
        "HIGHLIGHT: the red car\nVLM_BOX: 0.1,0.2,0.5,0.6")
    assert tgt == "the red car" and box == (0.1, 0.2, 0.5, 0.6)
    assert long_ == "Two people near a car." and short == "Two people."
    _, tgt2, box2, _ = vlm_client.parse_reply(
        "LONG RESPONSE: No dog visible.\nSHORT RESPONSE: No dog.\nHIGHLIGHT: none")
    assert tgt2 is None and box2 is None


def test_box_scaling_both_conventions():
    shape = (100, 200, 3)
    assert scale_vlm_box((0.5, 0.5, 1.0, 1.0), shape) == (100, 50, 200, 100)
    assert scale_vlm_box((500, 500, 1000, 1000), shape) == (100, 50, 200, 100)
