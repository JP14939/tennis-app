"""
Regression tests for ball_speed.py's net-crossing speed estimate. Synthetic
data only (no real video/model loading) -- these check the pure math (crossing
detection, velocity fit, plausibility clamp, the angle reliability gate)
independently of the ML/video plumbing that composes them.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ball_speed  # noqa: E402
from ball_speed import (  # noqa: E402
    _find_net_crossing,
    _ball_speed_px_per_frame_at,
    estimate_net_crossing_ball_speed_kmh,
)


def test_finds_crossing_within_net_bounds():
    # Ball descends from y=100 to y=0 over 10 frames, x steady at 50, net
    # sits at y=40 spanning x in [0, 100] -- should cross around frame 6.
    track = [(f, (50.0, 100.0 - 10.0 * f)) for f in range(11)]
    frame = _find_net_crossing(track, net_y_px=40.0, left_x_px=0.0, right_x_px=100.0)
    assert frame is not None
    assert 5 <= frame <= 7


def test_no_crossing_when_track_never_reaches_net_height():
    track = [(f, (50.0, 100.0 - 1.0 * f)) for f in range(5)]  # only reaches y=96
    assert _find_net_crossing(track, net_y_px=40.0, left_x_px=0.0, right_x_px=100.0) is None


def test_no_crossing_when_ball_goes_wide_of_net_span():
    # Same vertical crossing as the first test, but x is outside [0, 100]
    # throughout -- the ball crossed that height out wide, not through the net.
    track = [(f, (500.0, 100.0 - 10.0 * f)) for f in range(11)]
    assert _find_net_crossing(track, net_y_px=40.0, left_x_px=0.0, right_x_px=100.0) is None


def test_velocity_fit_recovers_known_constant_speed():
    # Constant velocity (3, 4) px/frame -> speed 5 px/frame everywhere.
    track = [(f, (3.0 * f, 4.0 * f)) for f in range(10)]
    speed = _ball_speed_px_per_frame_at(track, frame=5, degree=1)
    assert speed is not None
    assert abs(speed - 5.0) < 1e-6


def test_velocity_fit_none_with_insufficient_data():
    track = [(5, (0.0, 0.0))]  # single point, nothing to fit
    assert _ball_speed_px_per_frame_at(track, frame=5) is None


def test_angle_below_threshold_short_circuits_without_touching_video(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError('should not be called when the angle gate fails')

    monkeypatch.setattr(ball_speed, '_net_scale_and_bounds', _boom)
    assert estimate_net_crossing_ball_speed_kmh('irrelevant.mp4', 10, 30.0, camera_angle_deg=10.0) is None
    assert estimate_net_crossing_ball_speed_kmh('irrelevant.mp4', 10, 30.0, camera_angle_deg=None) is None


def test_end_to_end_speed_within_plausible_range(monkeypatch):
    # 30 fps, net crossing at 12.8m real width mapped to 100px -> scale
    # 0.128 m/px. Ball moves 20 px/frame in a straight line -> speed =
    # 20 * 30 * 0.128 * 3.6 = 276.48 km/h... too fast, so use a slower rate
    # (5 px/frame) to land inside the plausible window:
    # 5 * 30 * 0.128 * 3.6 = 69.12 km/h.
    scale = 12.8 / 100.0  # meters per pixel
    net_y_px, left_x_px, right_x_px = 40.0, 0.0, 100.0
    track = [(f, (50.0, 100.0 - 5.0 * f)) for f in range(21)]  # reaches y=0 by frame 20, crossing ~frame 12

    monkeypatch.setattr(ball_speed, '_net_scale_and_bounds',
                         lambda video_path, frame: (scale, net_y_px, left_x_px, right_x_px))
    monkeypatch.setattr(ball_speed, 'track_racket_and_ball',
                         lambda video_path, frame_range: ([], 30.0))
    monkeypatch.setattr(ball_speed, '_interpolated_ball_track',
                         lambda detections, start, end: track)

    kmh = estimate_net_crossing_ball_speed_kmh('irrelevant.mp4', contact_frame=0, fps=30.0,
                                                camera_angle_deg=45.0)
    assert kmh is not None
    assert ball_speed.MIN_PLAUSIBLE_KMH <= kmh <= ball_speed.MAX_PLAUSIBLE_KMH
    assert abs(kmh - 69.12) < 1.0


def test_implausible_speed_is_discarded(monkeypatch):
    # Same track as above but with a deliberately absurd scale -> a speed
    # far outside [MIN_PLAUSIBLE_KMH, MAX_PLAUSIBLE_KMH] should come back None.
    net_y_px, left_x_px, right_x_px = 40.0, 0.0, 100.0
    track = [(f, (50.0, 100.0 - 5.0 * f)) for f in range(11)]

    monkeypatch.setattr(ball_speed, '_net_scale_and_bounds',
                         lambda video_path, frame: (100.0, net_y_px, left_x_px, right_x_px))
    monkeypatch.setattr(ball_speed, 'track_racket_and_ball',
                         lambda video_path, frame_range: ([], 30.0))
    monkeypatch.setattr(ball_speed, '_interpolated_ball_track',
                         lambda detections, start, end: track)

    assert estimate_net_crossing_ball_speed_kmh('irrelevant.mp4', contact_frame=0, fps=30.0,
                                                 camera_angle_deg=45.0) is None


def test_no_net_detected_returns_none(monkeypatch):
    monkeypatch.setattr(ball_speed, '_net_scale_and_bounds', lambda video_path, frame: None)
    assert estimate_net_crossing_ball_speed_kmh('irrelevant.mp4', 0, 30.0, camera_angle_deg=45.0) is None


def test_empty_ball_track_returns_none(monkeypatch):
    monkeypatch.setattr(ball_speed, '_net_scale_and_bounds',
                         lambda video_path, frame: (0.1, 40.0, 0.0, 100.0))
    monkeypatch.setattr(ball_speed, 'track_racket_and_ball',
                         lambda video_path, frame_range: ([], 30.0))
    monkeypatch.setattr(ball_speed, '_interpolated_ball_track',
                         lambda detections, start, end: [])
    assert estimate_net_crossing_ball_speed_kmh('irrelevant.mp4', 0, 30.0, camera_angle_deg=45.0) is None
