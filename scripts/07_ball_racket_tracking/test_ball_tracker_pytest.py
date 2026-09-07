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
from ball_tracker import BallTracker, track_ball, track_ball_states  # noqa: E402


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


def test_default_max_gap_bridges_four_frames_but_not_six():
    # Default max_gap_frames is 4 -- a 4-frame occlusion at contact is still
    # bridged; a 6-frame one is too long to keep predicting through.
    true_path = {f: (2.0 * f, 1.0 * f) for f in range(20)}
    four = [_det(f, c) for f, c in true_path.items() if f not in range(5, 9)]
    six = [_det(f, c) for f, c in true_path.items() if f not in range(5, 11)]

    bridged = dict(track_ball(four, 0, 19, _center_fn))
    assert all(f in bridged for f in range(5, 9))

    dropped = dict(track_ball(six, 0, 19, _center_fn))
    assert 5 in dropped  # within the streak cap
    assert 9 not in dropped  # past it


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


def test_track_ball_states_reports_converging_velocity_and_covariance():
    # Constant-velocity path (2, 1) per frame -- the filter's velocity
    # estimate should converge on the true motion and its position
    # covariance should shrink from the large initial uncertainty.
    true_path = {f: (2.0 * f, 1.0 * f) for f in range(12)}
    detections = [_det(f, c) for f, c in true_path.items()]

    states = track_ball_states(detections, 0, 11, _center_fn)
    assert [s['frame'] for s in states] == list(range(12))

    last = states[-1]
    assert abs(last['vel'][0] - 2.0) < 0.3
    assert abs(last['vel'][1] - 1.0) < 0.3
    # covariance trace collapses once real measurements keep arriving
    early_trace = states[1]['cov'][0][0] + states[1]['cov'][1][1]
    late_trace = last['cov'][0][0] + last['cov'][1][1]
    assert late_trace < early_trace
    assert last['accepted'] and not last['predicted']
    assert last['mahalanobis_d2'] is not None


def test_track_ball_states_predict_only_frames_ignores_the_measurement():
    true_path = {f: (2.0 * f, 1.0 * f) for f in range(12)}
    detections = [_det(f, c) for f, c in true_path.items()]

    states = {s['frame']: s for s in track_ball_states(
        detections, 0, 11, _center_fn, predict_only_frames=(6,))}

    assert states[6]['measurement'] is None
    assert states[6]['predicted'] is True
    assert states[6]['mahalanobis_d2'] is None
    # still close to the true position -- coasted, not snapped
    assert abs(states[6]['pos'][0] - 12.0) < 1.5


def test_track_ball_states_extrapolate_frames_emits_past_last_detection():
    true_path = {f: (2.0 * f, 1.0 * f) for f in range(10)}
    detections = [_det(f, c) for f, c in true_path.items()]

    states = track_ball_states(detections, 0, 9, _center_fn, extrapolate_frames=3)
    frames = [s['frame'] for s in states]
    assert frames[-3:] == [10, 11, 12]
    for s in states[-3:]:
        assert s['predicted'] and s['measurement'] is None
    # constant-velocity projection stays on the line
    assert abs(states[-1]['pos'][0] - 24.0) < 2.0


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
