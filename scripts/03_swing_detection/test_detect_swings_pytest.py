"""Regression test: compute_wrist_velocity() used to gate a frame-to-frame
jump on the CURRENT frame's visibility only. MediaPipe always returns an
x/y for every landmark regardless of confidence (motion blur is common
right around a swing's contact point), so a garbage low-confidence
PREVIOUS position paired with a confident current one still produced a
spuriously large jump that got accepted as real wrist velocity -- silently
shifting swing-peak detection during pro-database building. Same bug/fix
as compare_swing.py's find_peak_wrist_frame() on the live comparison side.

No cv2/mediapipe import here, unlike the comparison-engine test -- this
file runs in any environment.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_swings import compute_wrist_velocity  # noqa: E402


def _landmark(name, x, y, visibility):
    return {'name': name, 'x': x, 'y': y, 'z': 0.0, 'visibility': visibility}


def _frame(right_wrist_xy, visibility):
    x, y = right_wrist_xy
    return {
        'landmarks': [
            _landmark('right_wrist', x, y, visibility),
            _landmark('left_wrist', 0.5, 0.5, 1.0),  # stationary, irrelevant
        ],
    }


def test_low_visibility_previous_frame_does_not_inflate_velocity():
    frames = [
        _frame((0.50, 0.50), 1.0),
        # Motion-blurred frame at a garbage position -- its own low
        # visibility must also block the jump OUT of it on the next frame,
        # not just the jump into it.
        _frame((0.10, 0.10), 0.1),
        # High-confidence frame; the apparent jump from frame 1's garbage
        # position is spurious and must read as zero, not a real peak.
        _frame((0.55, 0.50), 1.0),
        _frame((0.56, 0.50), 1.0),
    ]
    velocities = compute_wrist_velocity(frames)
    # Frame index 2's velocity is the (previously spurious) jump from the
    # garbage frame 1 position -- must be suppressed to 0.
    assert velocities[2] == 0
    # Frame index 3's genuine small movement is unaffected.
    assert velocities[3] > 0


def test_low_visibility_current_frame_still_suppressed():
    frames = [
        _frame((0.50, 0.50), 1.0),
        _frame((0.90, 0.90), 0.1),  # own visibility low -- already gated
        _frame((0.90, 0.90), 1.0),
    ]
    velocities = compute_wrist_velocity(frames)
    assert velocities[1] == 0
