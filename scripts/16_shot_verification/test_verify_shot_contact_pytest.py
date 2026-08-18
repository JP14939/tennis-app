"""Regression test: filter_verified_swings() used to only exclude
contact_method == 'wrist_velocity_fallback' or a 'static_hold(...)' prefix.
When verify_swings()'s tracking raised an exception, it set contact_method
to an 'error: ...' string with contact_confidence forced to 0.0 -- neither
exclusion matched that shape, so a tracking FAILURE was kept as if it had
real racket/ball corroboration."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_shot_contact import filter_verified_swings  # noqa: E402


def _swing(method, confidence=0.0):
    return {'contact_method': method, 'contact_confidence': confidence}


def test_filter_verified_swings_drops_error_method():
    swings = [_swing('error: model OOM'), _swing('error: bad crop dimensions')]
    assert filter_verified_swings(swings) == []


def test_filter_verified_swings_keeps_real_evidence():
    swings = [_swing('ball_racket_proximity', 0.8), _swing('ball_occlusion_gap(3f)', 0.6)]
    assert filter_verified_swings(swings) == swings


def test_filter_verified_swings_drops_wrist_velocity_fallback_at_low_confidence():
    swings = [_swing('wrist_velocity_fallback', 0.1)]
    assert filter_verified_swings(swings) == []


def test_filter_verified_swings_drops_legacy_static_hold():
    swings = [_swing('static_hold(ball_racket_proximity)', 0.2)]
    assert filter_verified_swings(swings) == []


def test_filter_verified_swings_mixed_batch():
    good = _swing('ball_racket_proximity', 0.8)
    swings = [good, _swing('error: timeout'), _swing('wrist_velocity_fallback', 0.0)]
    assert filter_verified_swings(swings) == [good]
