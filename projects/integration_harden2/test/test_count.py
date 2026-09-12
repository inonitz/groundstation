"""count_instances / median_count: the block-A counting fix (2026-09-09). Pure python, no GPU."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from perception2.counting import count_instances, median_count


def _d(conf, box): return {"conf": conf, "box": box}


def test_threshold_drops_low_conf():
    assert len(count_instances([_d(0.9, (0, 0, 100, 100)), _d(0.3, (200, 200, 300, 300))])) == 1


def test_part_inside_whole_is_one_instance():
    whole = _d(0.93, (100, 100, 400, 500)); back = _d(0.62, (120, 110, 380, 300)); other = _d(0.7, (600, 100, 900, 500))
    kept = count_instances([back, whole, other])
    assert [k["box"] for k in kept] == [whole["box"], other["box"]]


def test_side_by_side_chairs_both_count():
    a = _d(0.9, (0, 0, 100, 100)); b = _d(0.8, (90, 0, 190, 100))   # 10 % overlap
    assert len(count_instances([a, b])) == 2


def test_zero_area_box_ignored():
    assert count_instances([_d(0.9, (5, 5, 5, 50))]) == []


def test_median_count():
    assert median_count([2, 5, 4]) == 4 and median_count([6, 1]) == 1 and median_count([]) == 0 and median_count([3]) == 3


def test_speck_boxes_dropped_with_frame_area():
    speck = _d(0.86, (10, 10, 20, 20)); real = _d(0.7, (100, 100, 400, 400))     # 100 px2 vs 90000 px2
    kept = count_instances([speck, real], 0.5, frame_area=1280 * 720, min_frac=0.001)
    assert [k["box"] for k in kept] == [real["box"]]
    assert len(count_instances([speck, real], 0.5)) == 2                            # no floor when frame_area is absent
