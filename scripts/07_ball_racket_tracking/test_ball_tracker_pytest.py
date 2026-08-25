"""
Regression tests for ball_tracker.py's constant-velocity Kalman filter.
Synthetic trajectories only (no real footage/ground truth needed) -- these
check the tracker's own math does what it claims: predicts through a gap
close to the true position, and rejects a detection that doesn't fit the
established motion instead of snapping to it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ball_tracker import BallTracker, track_ball  # noqa: E402


def _center_fn(box, det):
    # Test doubles hand back an already-resolved (x, y) tuple as the "box".
    return box


def _det(frame, center):
    return {'frame': frame, 'ball_box': center}


def test_predicts_through_gap_close_to_true_position():
    # Straight-line constant-velocity path: (0,0) drifting by (2,1) per
    # frame. Drop frames 3-5 to simulate an occlusion gap.
    true_path = {f: (2.0 * f, 1.0 * f) for f in range(8)}
    detections = [_det(f, c) for f, c in true_path.items() if f not in (3, 4, 5)]

    track = track_ball(detections, 0, 7, _center_fn, max_gap_frames=3)
    track_by_frame = dict(track)

    assert 3 in track_by_frame and 4 in track_by_frame and 5 in track_by_frame
    for f in (3, 4, 5):
        tx, ty = track_by_frame[f]
        true_x, true_y = true_path[f]
        assert abs(tx - true_x) < 1.0
        assert abs(ty - true_y) < 1.0


def test_gap_much_longer_than_max_eventually_stops_being_bridged():
    true_path = {f: (2.0 * f, 1.0 * f) for f in range(16)}
    # 10-frame gap (3..12), far longer than max_gap_frames=3 -- the tracker
    # predicts on faith for the first 3 consecutive misses (frames 3-5) then
    # gives up; frames deep inside the gap must not be fabricated.
    detections = [_det(f, c) for f, c in true_path.items() if f not in range(3, 13)]

    track = track_ball(detections, 0, 15, _center_fn, max_gap_frames=3)
    track_by_frame = dict(track)

    assert 3 in track_by_frame  # within the streak cap, still bridged
    assert 8 not in track_by_frame  # deep inside the gap, must not be fabricated


def test_outlier_measurement_is_rejected_not_snapped_to():
    tracker = BallTracker(0.0, 0.0)
    # Establish a clear rightward trend so the filter has real velocity
    # evidence before the outlier arrives.
    for i in range(1, 6):
        tracker.update((10.0 * i, 0.0))

    predicted_x = tracker.x[0]
    # A wildly inconsistent measurement (stray ball-shaped object far off
    # the established path) should be rejected...
    x, y, accepted = tracker.update((predicted_x + 500, 300.0))
    assert not accepted
    # ...and the tracked state should stay near its prediction, not jump
    # to the outlier.
    assert abs(x - predicted_x) < 20.0


def test_consistent_measurement_is_accepted():
    tracker = BallTracker(0.0, 0.0)
    for i in range(1, 6):
        tracker.update((10.0 * i, 0.0))

    predicted_x = tracker.x[0]
    # A measurement close to where the established trend predicts should
    # be accepted.
    x, y, accepted = tracker.update((predicted_x + 2, 0.5))
    assert accepted


def test_empty_detections_returns_empty_track():
    assert track_ball([], 0, 10, _center_fn) == []


def test_single_detection_predicts_a_stationary_track_then_stops():
    # One real detection gives no velocity evidence, so the tracker
    # predicts a stationary ball for up to max_gap_frames frames on faith,
    # then stops -- not an error, and not fabricating motion it has no
    # evidence for.
    detections = [_det(0, (0.0, 0.0))]
    track = track_ball(detections, 0, 10, _center_fn, max_gap_frames=3)
    track_by_frame = dict(track)

    assert track_by_frame[0] == (0.0, 0.0)
    assert 3 in track_by_frame  # within the streak cap
    assert 8 not in track_by_frame  # long past it, must not be fabricated
