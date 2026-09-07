"""Tests for trajectory_extraction.mirror_trajectory (left-handed support)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trajectory_extraction import mirror_trajectory  # noqa: E402


def _pt(t, **landmarks):
    return {'t': t, 'landmarks': landmarks}


def test_swaps_left_right_and_negates_x():
    traj = [_pt(0.0,
                left_wrist={'x': 0.5, 'y': 0.2, 'z': 0.1},
                right_wrist={'x': -0.4, 'y': 0.3, 'z': -0.2},
                nose={'x': 0.05, 'y': -0.6, 'z': 0.0})]
    out = mirror_trajectory(traj)
    lm = out[0]['landmarks']
    # the lefty's hitting hand (left_wrist) is now under right_wrist, x negated
    assert lm['right_wrist'] == {'x': -0.5, 'y': 0.2, 'z': 0.1}
    assert lm['left_wrist'] == {'x': 0.4, 'y': 0.3, 'z': -0.2}
    # nose has no pair: same key, x negated, y unchanged
    assert lm['nose'] == {'x': -0.05, 'y': -0.6, 'z': 0.0}
    assert out[0]['t'] == 0.0


def test_mirror_twice_is_identity():
    traj = [
        _pt(-0.1, left_elbow={'x': 0.33, 'y': 0.1, 'z': None}, right_hip=None),
        _pt(0.2, right_shoulder={'x': -0.9, 'y': 0.0, 'z': 0.4}, nose={'x': 0.0, 'y': 0.1, 'z': 0.0}),
    ]
    assert mirror_trajectory(mirror_trajectory(traj)) == traj


def test_none_landmarks_survive_the_swap():
    traj = [_pt(0.0, left_hip=None, right_hip={'x': 0.2, 'y': 0.5, 'z': 0.0})]
    lm = mirror_trajectory(traj)[0]['landmarks']
    assert lm['right_hip'] is None            # was left_hip
    assert lm['left_hip'] == {'x': -0.2, 'y': 0.5, 'z': 0.0}


def test_missing_z_is_preserved_as_absent():
    traj = [_pt(0.0, left_wrist={'x': 0.5, 'y': 0.2})]
    lm = mirror_trajectory(traj)[0]['landmarks']
    assert lm['right_wrist'] == {'x': -0.5, 'y': 0.2, 'z': None}
