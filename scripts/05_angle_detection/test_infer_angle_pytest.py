"""
Pure-function coverage for infer_angle.py -- label helpers and the geometry
functions that were previously untested (test_net_roll_pytest.py only covered
net_roll_deg / usable_roll).

No model or video: run_net_keypoint_model / detect_pose are monkeypatched.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import infer_angle as ia
from infer_angle import (
    angle_label, elevation_label, framing_label, height_ratio_from_keypoints,
    detect_net_endpoints_keypoints, detect_view_direction, angle_from_sideline_symmetry,
    evaluate_view_usable, VIEW_GATE_SIDE_ON_ANGLE_DEG, VIEW_GATE_MIN_ANGLE_CONF,
    ELEVATION_LEVEL_MIN, ELEVATION_LOW_MAX, IDX,
)


# ---- angle_label ----

def test_angle_label_boundaries():
    assert angle_label(None) == 'Unknown'
    assert angle_label(0) == 'Front view'
    assert angle_label(19.9) == 'Front view'
    assert angle_label(20) == 'Semi-front'
    assert angle_label(39.9) == 'Semi-front'
    assert angle_label(40) == 'Diagonal (ideal)'
    assert angle_label(59.9) == 'Diagonal (ideal)'
    assert angle_label(60) == 'Semi-side'
    assert angle_label(74.9) == 'Semi-side'
    assert angle_label(75) == 'Side view'
    assert angle_label(90) == 'Side view'


# ---- elevation_label ----

def test_elevation_label():
    assert elevation_label(None) == 'unknown'
    assert elevation_label(ELEVATION_LEVEL_MIN) == 'level'
    assert elevation_label(ELEVATION_LEVEL_MIN + 0.01) == 'level'
    assert elevation_label(ELEVATION_LOW_MAX - 0.001) == 'possibly_elevated'
    # between the two thresholds -> uncertain
    mid = (ELEVATION_LEVEL_MIN + ELEVATION_LOW_MAX) / 2
    assert elevation_label(mid) == 'uncertain'


# ---- framing_label ----

def test_framing_label():
    assert framing_label(None, None) == 'unknown'
    # tilt checked before stance
    assert framing_label(0.20, 20.0) == 'tilted'
    assert framing_label(0.25, 5.0) == 'compressed_stance'
    assert framing_label(0.50, 5.0) == 'ok'
    assert framing_label(0.50, None) == 'ok'


# ---- height_ratio_from_keypoints ----

def test_height_ratio_from_keypoints():
    kp = {
        'net_top_left': (0.1, 0.50), 'net_top_right': (0.9, 0.50),
        'left_post_base': (0.1, 0.60), 'right_post_base': (0.9, 0.62),
    }
    # net_top_y = 0.50 ; ratios = |0.60-0.50|, |0.62-0.50| -> mean 0.11
    assert abs(height_ratio_from_keypoints(kp) - 0.11) < 1e-9
    # only one base
    kp1 = dict(kp); kp1.pop('right_post_base')
    assert abs(height_ratio_from_keypoints(kp1) - 0.10) < 1e-9
    # no bases
    kp0 = {'net_top_left': (0.1, 0.5), 'net_top_right': (0.9, 0.5)}
    assert height_ratio_from_keypoints(kp0) is None
    # no top corners
    assert height_ratio_from_keypoints({'left_post_base': (0.1, 0.6)}) is None


# ---- detect_net_endpoints_keypoints ----

def test_detect_net_endpoints_keypoints(monkeypatch):
    monkeypatch.setattr(ia, 'run_net_keypoint_model', lambda frame: {
        'net_top_left': (0.7, 0.40), 'net_top_right': (0.2, 0.44),  # deliberately x-swapped
    })
    left_x, right_x, net_y = detect_net_endpoints_keypoints(None)
    assert left_x == 0.2 and right_x == 0.7          # sorted
    assert abs(net_y - 0.42) < 1e-9                   # mean of the two ys

    monkeypatch.setattr(ia, 'run_net_keypoint_model', lambda frame: {'net_top_left': (0.2, 0.4)})
    assert detect_net_endpoints_keypoints(None) is None


# ---- detect_view_direction ----

class _LM:
    def __init__(self, x, y, vis=1.0):
        self.x, self.y, self.visibility = x, y, vis


def _pose(shoulder_y, ankle_y):
    lms = [_LM(0.5, 0.5) for _ in range(33)]
    for k in ('left_shoulder', 'right_shoulder'):
        lms[IDX[k]] = _LM(0.5, shoulder_y)
    for k in ('left_ankle', 'right_ankle'):
        lms[IDX[k]] = _LM(0.5, ankle_y)
    return lms


def test_detect_view_direction_back(monkeypatch):
    # net_y inside the shoulder..ankle span -> back
    monkeypatch.setattr(ia, 'run_net_keypoint_model',
                        lambda f: {'net_top_left': (0.1, 0.55), 'net_top_right': (0.9, 0.55)})
    monkeypatch.setattr(ia, 'detect_pose', lambda f: _pose(shoulder_y=0.3, ankle_y=0.9))
    assert detect_view_direction(None) == 'back'


def test_detect_view_direction_front(monkeypatch):
    # net_y well below ankles + margin -> front
    monkeypatch.setattr(ia, 'run_net_keypoint_model',
                        lambda f: {'net_top_left': (0.1, 0.98), 'net_top_right': (0.9, 0.98)})
    monkeypatch.setattr(ia, 'detect_pose', lambda f: _pose(shoulder_y=0.3, ankle_y=0.7))
    assert detect_view_direction(None) == 'front'


def test_detect_view_direction_unknown(monkeypatch):
    # no net
    monkeypatch.setattr(ia, 'run_net_keypoint_model', lambda f: {})
    monkeypatch.setattr(ia, 'detect_net_endpoints', lambda f: None)
    assert detect_view_direction(None) == 'unknown'
    # net but degenerate span
    monkeypatch.setattr(ia, 'run_net_keypoint_model',
                        lambda f: {'net_top_left': (0.1, 0.5), 'net_top_right': (0.9, 0.5)})
    monkeypatch.setattr(ia, 'detect_pose', lambda f: _pose(shoulder_y=0.5, ankle_y=0.505))
    assert detect_view_direction(None) == 'unknown'


# ---- angle_from_sideline_symmetry ----

def test_angle_from_sideline_symmetry():
    assert angle_from_sideline_symmetry(0, 0) is None
    assert angle_from_sideline_symmetry(10, 10) == 0.0          # symmetric -> front
    assert angle_from_sideline_symmetry(20, 0) == 90.0          # maximally asymmetric
    v = angle_from_sideline_symmetry(15, 5)
    assert 0 < v < 90


# ---- evaluate_view_usable (behind-the-baseline view gate, roadmap 1a) ----

def test_view_gate_front_view_fails():
    r = evaluate_view_usable('front', 30.0, 0.8)
    assert r['usable'] is False and r['reason'] == 'front_view'
    assert r['severity'] == 'warn' and r['message']


def test_view_gate_side_on_fails():
    r = evaluate_view_usable('back', VIEW_GATE_SIDE_ON_ANGLE_DEG, 0.8)
    assert r['usable'] is False and r['reason'] == 'side_on'


def test_view_gate_low_confidence_fails():
    r = evaluate_view_usable('back', 45.0, VIEW_GATE_MIN_ANGLE_CONF - 0.01)
    assert r['usable'] is False and r['reason'] == 'angle_unreliable'


def test_view_gate_front_beats_other_rules():
    # front view wins even when the angle/conf would also trip
    r = evaluate_view_usable('front', 89.0, 0.0)
    assert r['reason'] == 'front_view'


def test_view_gate_passes_good_back_view():
    r = evaluate_view_usable('back', 45.0, 0.6)
    assert r['usable'] is True and r['reason'] is None and r['message'] is None


def test_view_gate_unknown_view_alone_passes():
    # 'unknown' is not a failure on its own -- detection is unreliable, the
    # record-time picker hint is the tie-breaker
    r = evaluate_view_usable('unknown', 45.0, 0.6)
    assert r['usable'] is True


def test_view_gate_missing_angle_passes():
    r = evaluate_view_usable('back', None, None)
    assert r['usable'] is True
