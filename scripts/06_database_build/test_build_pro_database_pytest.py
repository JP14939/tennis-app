"""Regression test: normalise_landmarks() used `if not mid_x or width < 0.01`
to detect a missing shoulder reference, but mid_x=0.0 is a legitimate
coordinate (shoulder midpoint sitting exactly at the frame's left edge),
not a missing value -- `not 0.0` is True, so a valid frame was incorrectly
dropped as if the reference were missing."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_pro_database import normalise_landmarks, KEY_LANDMARKS  # noqa: E402


def _landmark(x, y, z=0.0):
    return {'x': x, 'y': y, 'z': z, 'visibility': 1.0}


def _lm_dict_with_shoulders(left_x, right_x, y=0.5):
    d = {name: _landmark(0.5, 0.5) for name in KEY_LANDMARKS}
    d['left_shoulder'] = _landmark(left_x, y)
    d['right_shoulder'] = _landmark(right_x, y)
    return d


def test_normalise_landmarks_accepts_zero_shoulder_midpoint():
    # left/right shoulders straddle x=0.0 exactly, so mid_x == 0.0 --
    # a real, valid frame, not a missing reference.
    lm_dict = _lm_dict_with_shoulders(left_x=-0.05, right_x=0.05)
    result = normalise_landmarks(lm_dict)
    assert result is not None


def test_normalise_landmarks_rejects_missing_shoulders():
    lm_dict = {name: _landmark(0.5, 0.5) for name in KEY_LANDMARKS}
    del lm_dict['left_shoulder']
    del lm_dict['right_shoulder']
    assert normalise_landmarks(lm_dict) is None


def test_normalise_landmarks_rejects_degenerate_zero_width():
    # left/right shoulders at the exact same point -- width ~ 0, still
    # correctly rejected (this is the case the width<0.01 check guards).
    lm_dict = _lm_dict_with_shoulders(left_x=0.3, right_x=0.3)
    assert normalise_landmarks(lm_dict) is None
