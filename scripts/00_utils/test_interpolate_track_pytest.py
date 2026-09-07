"""Tests for interpolate_track.py -- short-gap positional interpolation.
Synthetic series only, no real footage."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from interpolate_track import interpolate_series, interpolate_named_points  # noqa: E402


def _lin(ts, i):  # a straight line, for exact linear-fill checks
    return 3.0 * ts[i] - 2.0


def test_single_sample_hole_on_a_curve_uses_a_quadratic():
    # y = t^2: a chord under-shoots the true value, a quadratic nails it.
    ts = [round(0.1 * i, 4) for i in range(9)]
    true = [t * t for t in ts]
    values = list(true)
    values[4] = None

    out = interpolate_series(ts, values, max_gap_seconds=0.5)

    assert out[4] == pytest.approx(true[4], abs=1e-9)


def test_multi_sample_hole_falls_back_to_a_straight_line():
    ts = [round(0.1 * i, 4) for i in range(9)]
    values = [_lin(ts, i) for i in range(9)]
    values[3] = values[4] = None

    out = interpolate_series(ts, values, max_gap_seconds=0.5)

    assert out[3] == pytest.approx(_lin(ts, 3))
    assert out[4] == pytest.approx(_lin(ts, 4))


def test_gap_longer_than_cap_is_left_untouched():
    ts = [round(0.1 * i, 4) for i in range(12)]
    values = [float(i) for i in range(12)]
    for g in range(3, 9):  # 0.6s hole, well past the 0.25s default cap
        values[g] = None

    out = interpolate_series(ts, values)

    assert all(out[g] is None for g in range(3, 9))


def test_cap_is_time_not_sample_count():
    # Two samples missing but the brackets are only 0.09s apart -> filled,
    # even though a "3 sample" cap on a 10x-denser series would reject it.
    ts = [round(0.03 * i, 4) for i in range(9)]
    values = [_lin(ts, i) for i in range(9)]
    values[4] = values[5] = None

    out = interpolate_series(ts, values)  # default 0.25s cap

    assert out[4] == pytest.approx(_lin(ts, 4))
    assert out[5] == pytest.approx(_lin(ts, 5))


def test_leading_and_trailing_gaps_are_not_extrapolated():
    ts = [round(0.1 * i, 4) for i in range(8)]
    values = [None, None, 2.0, 3.0, 4.0, 5.0, None, None]

    out = interpolate_series(ts, values, max_gap_seconds=0.5)

    assert out[0] is None and out[1] is None
    assert out[6] is None and out[7] is None
    assert out[2:6] == [2.0, 3.0, 4.0, 5.0]


def test_two_anchor_linear_fallback():
    ts = [0.0, 0.1, 0.2, 0.3]
    values = [10.0, None, None, 40.0]

    out = interpolate_series(ts, values, max_gap_seconds=0.5)

    assert out[1] == pytest.approx(20.0)
    assert out[2] == pytest.approx(30.0)


def test_flat_series_stays_flat():
    ts = [round(0.1 * i, 4) for i in range(6)]
    values = [7.0, 7.0, None, 7.0, 7.0, 7.0]

    out = interpolate_series(ts, values, max_gap_seconds=0.5)

    assert out[2] == pytest.approx(7.0)


def test_interpolate_named_points_fills_per_point():
    frames = [
        {'t': 0.0, 'points': {'tip': {'x': 0.0, 'y': 0.0}, 'handle': None}},
        {'t': 0.1, 'points': {'tip': None, 'handle': None}},
        {'t': 0.2, 'points': {'tip': {'x': 2.0, 'y': 4.0}, 'handle': None}},
    ]
    interpolate_named_points(frames, ['tip', 'handle'])

    assert frames[1]['points']['tip'] == {'x': pytest.approx(1.0), 'y': pytest.approx(2.0)}
    # handle never had two anchors -> stays None
    assert frames[1]['points']['handle'] is None
