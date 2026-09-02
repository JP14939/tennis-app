"""Tests for infer_angle.net_roll_deg / usable_roll (in-plane camera roll
from the net-cord slope)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from infer_angle import (  # noqa: E402
    net_roll_deg, usable_roll, ROLL_CORRECTION_MIN_DEG, ROLL_CORRECTION_MAX_DEG,
)


def test_none_when_a_net_top_point_missing():
    assert net_roll_deg({}) is None
    assert net_roll_deg({'net_top_left': (0.2, 0.5)}) is None
    assert net_roll_deg({'net_top_right': (0.8, 0.5)}) is None


def test_level_net_reads_zero():
    kp = {'net_top_left': (0.2, 0.5), 'net_top_right': (0.8, 0.5)}
    assert abs(net_roll_deg(kp)) < 1e-9


def test_right_end_lower_is_positive():
    # right net-top point sits lower in the image (larger y) -> positive roll
    kp = {'net_top_left': (0.2, 0.5), 'net_top_right': (0.8, 0.6)}
    assert math.isclose(net_roll_deg(kp), math.degrees(math.atan2(0.1, 0.6)), abs_tol=1e-9)
    assert net_roll_deg(kp) > 0


def test_label_order_independence():
    # model swapped which point it called left/right on a canted frame:
    # ordering by x still gives the same slope sign
    a = {'net_top_left': (0.2, 0.5), 'net_top_right': (0.8, 0.6)}
    b = {'net_top_left': (0.8, 0.6), 'net_top_right': (0.2, 0.5)}
    assert math.isclose(net_roll_deg(a), net_roll_deg(b), abs_tol=1e-9)


def test_usable_roll_band():
    assert usable_roll(None) is None
    assert usable_roll(0.0) is None
    assert usable_roll(ROLL_CORRECTION_MIN_DEG - 0.5) is None
    assert usable_roll(ROLL_CORRECTION_MAX_DEG + 5) is None
    assert usable_roll(10.0) == 10.0
    assert usable_roll(-10.0) == -10.0
