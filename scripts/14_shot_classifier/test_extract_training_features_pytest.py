"""Coverage for extract_features(): the raw pose-derived quantities
score_forehand/score_backhand/score_serve already compute internally but
never expose individually. Same landmark reads, kept as separate numbers
instead of being collapsed into one blended score."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_training_features import extract_features, FEATURE_NAMES  # noqa: E402


def _lm(name, x, y, z=0.0, visibility=0.9):
    return {'name': name, 'x': x, 'y': y, 'z': z, 'visibility': visibility}


def _frame(**overrides):
    """A frame with sane default landmark positions for a standing player
    facing the camera; override specific joints per test."""
    defaults = {
        'nose': _lm('nose', 0.5, 0.2),
        'right_shoulder': _lm('right_shoulder', 0.45, 0.3),
        'left_shoulder': _lm('left_shoulder', 0.55, 0.3),
        'right_elbow': _lm('right_elbow', 0.45, 0.45),
        'left_elbow': _lm('left_elbow', 0.55, 0.45),
        'right_wrist': _lm('right_wrist', 0.45, 0.5),
        'left_wrist': _lm('left_wrist', 0.55, 0.5),
        'right_hip': _lm('right_hip', 0.46, 0.6),
        'left_hip': _lm('left_hip', 0.54, 0.6),
    }
    defaults.update(overrides)
    return list(defaults.values())


def test_returns_every_declared_feature_name():
    peak = _frame()
    features = extract_features(peak, peak, [peak])
    assert set(features.keys()) == set(FEATURE_NAMES)


def test_wrist_below_shoulder_gives_positive_margin_sign_matches_scorer():
    # rs.y=0.3, rw.y=0.5 -> rs.y - rw.y = -0.2 (negative: wrist BELOW shoulder,
    # matching score_forehand's "wrist not overhead" convention: y smaller = higher).
    peak = _frame()
    features = extract_features(peak, peak, [peak])
    assert features['rw_y_rel_shoulder'] == -0.2


def test_missing_landmark_gives_none_not_zero():
    peak = _frame(right_wrist=_lm('right_wrist', 0.45, 0.5, visibility=0.1))  # below visibility threshold
    features = extract_features(peak, peak, [peak])
    assert features['rw_y_rel_shoulder'] is None
    assert features['rw_x_rel_midline'] is None
    assert features['wrist_separation'] is None
    assert features['rw_velocity'] is None


def test_wrist_velocity_from_prev_frame():
    prev = _frame(right_wrist=_lm('right_wrist', 0.40, 0.5))
    peak = _frame(right_wrist=_lm('right_wrist', 0.45, 0.5))
    features = extract_features(peak, prev, [peak])
    assert features['rw_velocity'] == 0.05


def test_no_prev_frame_gives_none_velocity_not_a_crash():
    peak = _frame()
    features = extract_features(peak, None, [peak])
    assert features['rw_velocity'] is None
    assert features['lw_velocity'] is None


def test_overhead_serve_window_detects_wrist_above_shoulder():
    # An overhead moment appears in the WINDOW even though the peak frame
    # itself has the wrist back down -- mirrors score_serve()'s "downswing
    # by the velocity peak" scan-the-whole-window behavior.
    overhead_frame = _frame(right_wrist=_lm('right_wrist', 0.45, 0.1))  # above shoulder (y=0.3)
    peak = _frame()  # wrist back down at contact
    features = extract_features(peak, peak, [overhead_frame, peak])
    assert features['best_overhead_margin'] is not None
    assert features['best_overhead_margin'] > 0
    assert features['elbow_elevated'] is False  # elbow never went above shoulder in this test data


def test_wrist_above_nose_flag():
    high_wrist_frame = _frame(right_wrist=_lm('right_wrist', 0.45, 0.05))  # well above nose (y=0.2)
    peak = _frame()
    features = extract_features(peak, peak, [high_wrist_frame, peak])
    assert features['wrist_above_nose'] is True


def test_empty_window_falls_back_to_peak_frame_only():
    peak = _frame()
    features = extract_features(peak, peak, [])
    assert features['best_overhead_margin'] is not None  # peak frame itself still scanned
