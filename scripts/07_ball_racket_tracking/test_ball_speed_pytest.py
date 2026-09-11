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
    _ball_diameter_track,
    _diameter_fit_at,
    _radial_speed_m_per_s,
    _device_model_from_video,
    _focal_px_for_video,
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


def test_none_angle_short_circuits_without_touching_video(monkeypatch):
    # Only a genuinely unknown angle (None) short-circuits now -- a known but
    # low angle (dead-centre behind-the-baseline framing) must NOT, since v2
    # still needs the net scale/bounds for the radial term. See
    # test_low_angle_no_longer_rejected_outright for the case this replaces.
    def _boom(*args, **kwargs):
        raise AssertionError('should not be called when the angle is None')

    monkeypatch.setattr(ball_speed, '_net_scale_and_bounds', _boom)
    assert estimate_net_crossing_ball_speed_kmh('irrelevant.mp4', 10, 30.0, camera_angle_deg=None) is None


def test_low_angle_no_longer_rejected_outright(monkeypatch):
    # v1 hard-rejected any camera_angle_deg below 30 -- exactly the dead-centre
    # behind-the-baseline framing the view gate encourages. v2 drops that
    # threshold: a low angle now still reaches the lateral/radial estimate
    # instead of short-circuiting to None.
    scale = 12.8 / 100.0
    net_y_px, left_x_px, right_x_px = 40.0, 0.0, 100.0
    track = [(f, (50.0, 100.0 - 5.0 * f)) for f in range(21)]

    monkeypatch.setattr(ball_speed, '_net_scale_and_bounds',
                         lambda video_path, frame: (scale, net_y_px, left_x_px, right_x_px))
    monkeypatch.setattr(ball_speed, 'track_racket_and_ball',
                         lambda video_path, frame_range: ([], 30.0))
    monkeypatch.setattr(ball_speed, '_interpolated_ball_track',
                         lambda detections, start, end: track)

    kmh = estimate_net_crossing_ball_speed_kmh('irrelevant.mp4', contact_frame=0, fps=30.0,
                                                camera_angle_deg=10.0)
    assert kmh is not None


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


def test_roi_tracker_recovers_a_crossing_the_plain_track_misses(monkeypatch):
    # Pass-1 detections have a mid-flight gap right where the ball crosses the
    # net, so the plain Kalman track (default max_gap) breaks before the
    # crossing and _find_net_crossing returns None. The ROI-refined track
    # (stubbed here) bridges it -> a real speed comes back.
    scale = 12.8 / 100.0
    net_y_px, left_x_px, right_x_px = 40.0, 0.0, 100.0
    full = [(f, (50.0, 100.0 - 5.0 * f)) for f in range(21)]
    broken = [p for p in full if p[0] <= 6]  # track lost on the approach, never reaches the net

    monkeypatch.setattr(ball_speed, '_net_scale_and_bounds',
                        lambda video_path, frame: (scale, net_y_px, left_x_px, right_x_px))
    monkeypatch.setattr(ball_speed, 'track_racket_and_ball',
                        lambda video_path, frame_range: ([{'frame': f} for f, _ in full], 30.0))

    class _Refined:
        filled_track = full

    monkeypatch.setattr(ball_speed, 'refine_ball_track', lambda *a, **k: _Refined())
    monkeypatch.setattr(ball_speed, '_interpolated_ball_track',
                        lambda detections, start, end: broken)

    with_roi = estimate_net_crossing_ball_speed_kmh(
        'irrelevant.mp4', 0, 30.0, camera_angle_deg=45.0, use_roi_tracker=True)
    without_roi = estimate_net_crossing_ball_speed_kmh(
        'irrelevant.mp4', 0, 30.0, camera_angle_deg=45.0, use_roi_tracker=False)
    assert with_roi is not None
    assert without_roi is None


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


# --- Radial (ball-size) estimator -----------------------------------------

def test_diameter_track_filters_low_confidence_and_missing_boxes():
    detections = [
        {'frame': 0, 'ball_box': [0.0, 0.0, 10.0, 10.0], 'ball_conf': 0.9},   # kept: diameter 10
        {'frame': 1, 'ball_box': [0.0, 0.0, 8.0, 8.0], 'ball_conf': 0.10},    # dropped: low conf
        {'frame': 2, 'ball_box': None, 'ball_conf': 0.9},                    # dropped: no box
        {'frame': 3, 'ball_box': [0.0, 0.0, 20.0, 5.0], 'ball_conf': 0.9},   # kept: sqrt(20*5)=10
    ]
    track = _ball_diameter_track(detections)
    assert track == [(0, 10.0), (3, 10.0)]


def test_diameter_fit_recovers_known_shrink_rate():
    # Diameter shrinking linearly at -2 px/frame -> derivative should be -2
    # everywhere, value at frame=5 should be 100 - 2*5 = 90.
    diam_track = [(f, 100.0 - 2.0 * f) for f in range(11)]
    fit = _diameter_fit_at(diam_track, frame=5, degree=1)
    assert fit is not None
    diameter_at_frame, d_diameter = fit
    assert abs(diameter_at_frame - 90.0) < 1e-6
    assert abs(d_diameter - (-2.0)) < 1e-6


def test_radial_speed_recovers_known_closing_speed():
    # A ball closing on the camera at a known real speed produces a
    # diameter-vs-distance curve via similar triangles; fit a local track of
    # it and confirm the radial estimator recovers something close to the
    # real speed used to generate it (independent physical construction, not
    # just re-deriving the implementation's own formula).
    fps = 30.0
    focal_px = 1000.0
    true_speed_m_s = 10.0
    distance0_m = 10.0

    def distance_at(frame):
        return distance0_m - true_speed_m_s * (frame / fps)

    diam_track = [(f, focal_px * ball_speed.BALL_DIAMETER_M / distance_at(f))
                  for f in range(0, 17)]

    radial = _radial_speed_m_per_s(diam_track, frame=8, focal_px=focal_px, fps=fps)
    assert radial is not None
    assert abs(radial - true_speed_m_s) < 1.0  # within 10% of the real 10 m/s used to build it


def test_radial_speed_none_without_enough_diameter_data():
    assert _radial_speed_m_per_s([(5, 10.0)], frame=5, focal_px=1000.0, fps=30.0) is None
    assert _radial_speed_m_per_s([], frame=5, focal_px=1000.0, fps=30.0) is None


def test_combined_speed_is_pythagorean_of_lateral_and_radial(monkeypatch):
    # camera_angle_deg=8 is well below v1's old 30deg MIN_RELIABLE_ANGLE_DEG --
    # exactly the dead-centre behind-the-baseline framing v1 always returned
    # None for, regardless of what the track looked like. v2 must instead
    # combine the lateral pixel-velocity term with the new radial
    # (ball-size-derivative) term and return their Pythagorean sum.
    fps = 30.0
    net_width_px = 100.0
    scale = 12.8 / net_width_px  # ball_speed derives focal_px back out from this
    net_y_px, left_x_px, right_x_px = 40.0, 0.0, 100.0
    focal_px = net_width_px * ball_speed.ASSUMED_CAMERA_TO_NET_M / ball_speed.NET_WIDTH_M

    n_frames = 25
    track = [(f, (50.0, 100.0 - 3.5 * f)) for f in range(n_frames)]  # crosses y=40 around frame 17

    true_radial_speed_m_s = 10.0
    distance0_m = 15.0

    def distance_at(frame):
        return distance0_m - true_radial_speed_m_s * (frame / fps)

    detections = [
        {'frame': f,
         'ball_box': [0.0, 0.0,
                      focal_px * ball_speed.BALL_DIAMETER_M / distance_at(f),
                      focal_px * ball_speed.BALL_DIAMETER_M / distance_at(f)],
         'ball_conf': 0.9}
        for f in range(n_frames)
    ]

    monkeypatch.setattr(ball_speed, '_net_scale_and_bounds',
                         lambda video_path, frame: (scale, net_y_px, left_x_px, right_x_px))
    monkeypatch.setattr(ball_speed, 'track_racket_and_ball',
                         lambda video_path, frame_range: (detections, fps))
    monkeypatch.setattr(ball_speed, '_interpolated_ball_track',
                         lambda detections, start, end: track)

    kmh = estimate_net_crossing_ball_speed_kmh('irrelevant.mp4', contact_frame=0, fps=fps,
                                                camera_angle_deg=8.0)
    assert kmh is not None
    assert ball_speed.MIN_PLAUSIBLE_KMH <= kmh <= ball_speed.MAX_PLAUSIBLE_KMH

    lateral_m_s = 3.5 * fps * scale
    expected_total_kmh = (lateral_m_s ** 2 + true_radial_speed_m_s ** 2) ** 0.5 * 3.6
    assert abs(kmh - expected_total_kmh) < 10.0


# --- Device-model calibration ----------------------------------------------

class _FakeCompletedProcess:
    def __init__(self, stdout):
        self.stdout = stdout


def test_device_model_from_video_parses_quicktime_tag(monkeypatch):
    fake_stdout = (
        ';FFMETADATA1\n'
        'com.apple.quicktime.creationdate=2026-08-09T19:25:41+0100\n'
        'com.apple.quicktime.make=Apple\n'
        'com.apple.quicktime.model=iPhone 13\n'
        'com.apple.quicktime.software=26.5\n'
    )
    monkeypatch.setattr(ball_speed.subprocess, 'run',
                        lambda *a, **k: _FakeCompletedProcess(fake_stdout))
    assert _device_model_from_video('some_video.mp4') == 'iPhone 13'


def test_device_model_from_video_none_when_tag_absent(monkeypatch):
    fake_stdout = ';FFMETADATA1\nmajor_brand=qt\n'
    monkeypatch.setattr(ball_speed.subprocess, 'run',
                        lambda *a, **k: _FakeCompletedProcess(fake_stdout))
    assert _device_model_from_video('some_video.mp4') is None


def test_device_model_from_video_none_when_ffmpeg_fails(monkeypatch):
    def _boom(*a, **k):
        raise OSError('ffmpeg not found')
    monkeypatch.setattr(ball_speed, 'imageio_ffmpeg', type('M', (), {
        'get_ffmpeg_exe': staticmethod(_boom)})())
    assert _device_model_from_video('some_video.mp4') is None


def test_focal_px_uses_calibrated_device_ratio(monkeypatch):
    monkeypatch.setattr(ball_speed, '_focal_px_from_court_geometry', lambda *a, **k: None)
    monkeypatch.setattr(ball_speed, '_device_model_from_video', lambda video_path: 'iPhone 13')
    monkeypatch.setattr(ball_speed, 'DEVICE_FOCAL_PX_PER_WIDTH', {'iPhone 13': 1.5})
    focal_px = _focal_px_for_video('irrelevant.mp4', frame_number=0, net_y_px=500.0,
                                   net_width_px=999.0, frame_width_px=1000.0, frame_height_px=1080.0)
    assert focal_px == 1500.0  # calibrated ratio * frame width, net_width_px ignored


def test_focal_px_falls_back_when_device_unknown(monkeypatch):
    monkeypatch.setattr(ball_speed, '_focal_px_from_court_geometry', lambda *a, **k: None)
    monkeypatch.setattr(ball_speed, '_device_model_from_video', lambda video_path: 'Some Unknown Phone')
    monkeypatch.setattr(ball_speed, 'DEVICE_FOCAL_PX_PER_WIDTH', {'iPhone 13': 1.5})
    focal_px = _focal_px_for_video('irrelevant.mp4', frame_number=0, net_y_px=500.0,
                                   net_width_px=100.0, frame_width_px=1000.0, frame_height_px=1080.0)
    expected = 100.0 * ball_speed.ASSUMED_CAMERA_TO_NET_M / ball_speed.NET_WIDTH_M
    assert abs(focal_px - expected) < 1e-9


def test_focal_px_falls_back_when_no_device_identified(monkeypatch):
    monkeypatch.setattr(ball_speed, '_focal_px_from_court_geometry', lambda *a, **k: None)
    monkeypatch.setattr(ball_speed, '_device_model_from_video', lambda video_path: None)
    focal_px = _focal_px_for_video('irrelevant.mp4', frame_number=0, net_y_px=500.0,
                                   net_width_px=100.0, frame_width_px=1000.0, frame_height_px=1080.0)
    expected = 100.0 * ball_speed.ASSUMED_CAMERA_TO_NET_M / ball_speed.NET_WIDTH_M
    assert abs(focal_px - expected) < 1e-9


def test_focal_px_prefers_court_geometry_self_calibration(monkeypatch):
    monkeypatch.setattr(ball_speed, '_focal_px_from_court_geometry', lambda *a, **k: 1234.5)
    monkeypatch.setattr(ball_speed, '_device_model_from_video', lambda video_path: 'iPhone 13')
    monkeypatch.setattr(ball_speed, 'DEVICE_FOCAL_PX_PER_WIDTH', {'iPhone 13': 1.5})
    focal_px = _focal_px_for_video('irrelevant.mp4', frame_number=0, net_y_px=500.0,
                                   net_width_px=100.0, frame_width_px=1000.0, frame_height_px=1080.0)
    assert focal_px == 1234.5
