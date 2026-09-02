"""Regression test: find_peak_wrist_frame() used to trust a wrist's x/y
regardless of MediaPipe's visibility score for that landmark. MediaPipe
always returns an x/y for every landmark even at near-zero confidence
(motion blur is common right at contact, on fast swings), so a spuriously
large frame-to-frame jump from a low-confidence wrist detection could be
mistaken for the real contact-frame velocity peak -- silently shifting the
whole comparison window and corrupting the DTW score with no error
surfacing anywhere. Same 0.5 visibility threshold as detect_swings.py's
compute_wrist_velocity(), the pro-database side's equivalent function.

Not runnable in every environment: compare_swing.py imports cv2/mediapipe
at module level, so this needs the real scripts/venv (see CLAUDE.md) --
same situation test_build_pro_database_pytest.py is already in.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_swing import find_peak_wrist_frame  # noqa: E402


def _landmark(x, y, visibility):
    return {'x': x, 'y': y, 'z': 0.0, 'visibility': visibility}


def _frame(idx, right_wrist_xy, visibility):
    x, y = right_wrist_xy
    return {
        'frame': idx,
        'timestamp': idx / 30.0,
        'landmarks': {
            'right_wrist': _landmark(x, y, visibility),
            'left_wrist': _landmark(0.5, 0.5, 1.0),  # stationary, irrelevant
        },
    }


def test_low_visibility_wrist_jump_is_not_mistaken_for_contact():
    frames = [
        _frame(0, (0.50, 0.50), 1.0),
        _frame(1, (0.50, 0.50), 1.0),
        # Motion-blurred frame: a huge apparent jump, but low confidence --
        # must not be picked as the velocity peak.
        _frame(2, (0.90, 0.90), 0.1),
        _frame(3, (0.90, 0.90), 1.0),
        # A smaller, but high-confidence, real velocity peak.
        _frame(4, (0.95, 0.90), 1.0),
        _frame(5, (0.95, 0.90), 1.0),
    ]
    peak_idx = find_peak_wrist_frame(frames, fps=30)
    assert peak_idx == 4


def test_missing_landmarks_frame_is_skipped_not_crashed():
    frames = [
        _frame(0, (0.50, 0.50), 1.0),
        {'frame': 1, 'timestamp': 1 / 30.0, 'landmarks': None},
        _frame(2, (0.60, 0.50), 1.0),
    ]
    # Should not raise, and should still find the real movement at frame 2.
    assert find_peak_wrist_frame(frames, fps=30) == 2
