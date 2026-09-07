"""
Unit tests for eval_near_court_ball_detection's pure helpers -- the near/far
classifier convention and the crop-coverage check. No model / no labels.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_near_court_ball_detection import near_or_far, _box_inside, _crop_gt  # noqa: E402


def test_near_or_far_convention():
    # image-y increases downward; ball below the net line (larger y) is NEAR
    assert near_or_far(0.70, 0.40) == 'near'
    assert near_or_far(0.20, 0.40) == 'far'
    assert near_or_far(0.40, 0.40) == 'far'   # exactly on the line -> far
    assert near_or_far(0.5, None) == 'near_unknownnet'


def test_box_inside():
    rect = (100, 100, 500, 500)
    assert _box_inside((150, 150, 300, 300), rect)
    assert not _box_inside((150, 150, 600, 300), rect)   # spills right
    assert not _box_inside((50, 150, 300, 300), rect)    # spills left


def test_crop_gt_maps_into_crop_space():
    # rect top-left (200, 100), upscale x2
    gt = (240, 140, 260, 160)
    mapped = _crop_gt(gt, 2.0, 200, 100)
    assert mapped == (80.0, 80.0, 120.0, 120.0)
