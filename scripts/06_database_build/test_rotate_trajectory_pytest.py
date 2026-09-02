"""Tests for trajectory_extraction.rotate_landmarks / rotate_trajectory
(in-plane camera-roll correction)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trajectory_extraction import rotate_landmarks, rotate_trajectory  # noqa: E402


def _pt(t, **landmarks):
    return {'t': t, 'landmarks': landmarks}


def test_zero_and_none_roll_are_identity():
    lm = {'nose': {'x': 0.3, 'y': -0.7, 'z': 0.1}, 'left_hip': None}
    assert rotate_landmarks(lm, 0) is lm
    assert rotate_landmarks(lm, None) is lm
    traj = [_pt(0.0, **lm)]
    assert rotate_trajectory(traj, 0) is traj
    assert rotate_trajectory(traj, None) is traj


def test_known_rotation_sign():
    # roll_deg = +90 -> rotate landmarks by -90deg about the origin.
    # A point on +x axis (1, 0) goes to (0, -1) under a -90deg rotation
    # (image coords, y down).
    out = rotate_landmarks({'right_wrist': {'x': 1.0, 'y': 0.0, 'z': 0.5}}, 90)
    assert out['right_wrist']['x'] == 0.0
    assert out['right_wrist']['y'] == -1.0
    assert out['right_wrist']['z'] == 0.5  # z rides along untouched


def test_none_and_missing_z_survive():
    out = rotate_landmarks({'left_hip': None, 'nose': {'x': 0.2, 'y': 0.1}}, 12)
    assert out['left_hip'] is None
    assert out['nose']['z'] is None
    assert set(out) == {'left_hip', 'nose'}


def test_round_trip():
    lm = {'left_shoulder': {'x': 0.41, 'y': -0.33, 'z': 0.0},
          'right_wrist': {'x': -0.9, 'y': 0.72, 'z': None}}
    back = rotate_landmarks(rotate_landmarks(lm, 17.5), -17.5)
    for name in lm:
        assert math.isclose(back[name]['x'], lm[name]['x'], abs_tol=1e-3)
        assert math.isclose(back[name]['y'], lm[name]['y'], abs_tol=1e-3)


def test_rotate_trajectory_preserves_t_and_length():
    traj = [_pt(-0.5, nose={'x': 0.1, 'y': 0.2, 'z': 0.0}),
            _pt(0.0, nose={'x': 0.0, 'y': 0.0, 'z': 0.0}),
            _pt(0.4, nose=None)]
    out = rotate_trajectory(traj, 8.0)
    assert [p['t'] for p in out] == [-0.5, 0.0, 0.4]
    assert len(out) == 3
    assert out[2]['landmarks']['nose'] is None


def test_rotation_preserves_distance_from_origin():
    p = {'x': 0.6, 'y': -0.8, 'z': 0.0}  # radius 1.0
    out = rotate_landmarks({'k': p}, 21.0)['k']
    assert math.isclose(math.hypot(out['x'], out['y']), 1.0, abs_tol=1e-3)
