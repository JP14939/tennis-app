"""Tests for viewpoint_normalization (yaw / camera-azimuth correction)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viewpoint_normalization import (  # noqa: E402
    facing_azimuth, usable_yaw, rotate_world_landmarks, project_canonical_2d,
    yaw_normalise_window, YAW_MIN_FRAMES, YAW_DEADBAND_DEG, YAW_MAX_STDEV_DEG,
    YAW_MAX_CORRECTION_DEG,
)


def _canonical_frame(yaw_deg=0.0, lean=0.0):
    """A stick figure squared to a camera behind it (canonical), then yawed by
    yaw_deg about vertical. Shoulders wider than hips; `lean` adds a common
    z-offset (body lean / camera pitch) that facing_azimuth should ignore."""
    a = math.radians(yaw_deg)
    ca, sa = math.cos(a), math.sin(a)

    def rot(x, z):
        return x * ca - z * sa, x * sa + z * ca  # +yaw rotation

    base = {
        'left_shoulder':  (-0.20, -0.45, 0.0),
        'right_shoulder': (0.20, -0.45, 0.0),
        'left_hip':       (-0.12, 0.0, 0.0),
        'right_hip':      (0.12, 0.0, 0.0),
    }
    out = {}
    for name, (x, y, z) in base.items():
        rx, rz = rot(x, z)
        out[name] = {'x': rx, 'y': y, 'z': rz + lean, 'visibility': 1.0}
    return out


def test_canonical_is_zero_azimuth():
    assert abs(facing_azimuth(_canonical_frame(0.0))) < 1e-6


def test_azimuth_recovers_known_yaw():
    for yaw in (-50, -25, -10, 15, 30, 55):
        got = facing_azimuth(_canonical_frame(yaw))
        assert abs(got - yaw) < 1.0, (yaw, got)


def test_azimuth_ignores_common_z_lean():
    assert abs(facing_azimuth(_canonical_frame(20.0, lean=0.3)) - 20.0) < 1.0


def test_front_vs_back_differ_by_180():
    back = facing_azimuth(_canonical_frame(0.0))
    # front view = swap left/right landmarks (mirror the person)
    f = _canonical_frame(0.0)
    front = {
        'left_shoulder': f['right_shoulder'], 'right_shoulder': f['left_shoulder'],
        'left_hip': f['right_hip'], 'right_hip': f['left_hip'],
    }
    assert abs(abs(facing_azimuth(front) - back) - 180.0) < 1.0


def test_missing_one_pair_falls_back_to_the_other():
    # hips gone -> still readable from shoulders
    f = _canonical_frame(20.0)
    del f['left_hip']
    assert abs(facing_azimuth(f) - 20.0) < 1.0
    # both pairs gone -> None
    f2 = _canonical_frame(20.0)
    del f2['left_hip']
    f2['right_shoulder']['visibility'] = 0.1
    assert facing_azimuth(f2) is None


def test_rotate_world_landmarks_cancels_yaw():
    yaw = 35.0
    f = _canonical_frame(yaw)
    corrected = rotate_world_landmarks(f, yaw)
    assert abs(facing_azimuth(corrected)) < 1e-6
    # y untouched
    assert corrected['left_shoulder']['y'] == f['left_shoulder']['y']


def test_rotate_world_landmarks_identity():
    f = _canonical_frame(20.0)
    assert rotate_world_landmarks(f, 0) is f
    assert rotate_world_landmarks(f, None) is f


def test_usable_yaw_accepts_clean_signal():
    samples = [30.0, 31.0, 29.0, 30.5, 29.5, 30.0]
    assert usable_yaw(samples) == 30.0


def test_usable_yaw_too_few_frames():
    assert usable_yaw([30.0] * (YAW_MIN_FRAMES - 1)) is None


def test_usable_yaw_deadband():
    assert usable_yaw([YAW_DEADBAND_DEG - 2] * 8) is None


def test_usable_yaw_too_noisy():
    samples = [-40, 50, -30, 45, -20, 60]  # stdev >> YAW_MAX_STDEV_DEG
    assert _stdev_gt(samples, YAW_MAX_STDEV_DEG)
    assert usable_yaw(samples) is None


def test_usable_yaw_side_on_cap():
    assert usable_yaw([YAW_MAX_CORRECTION_DEG + 5] * 8) is None


def _stdev_gt(xs, thr):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) > thr


def test_yaw_normalise_window_uses_only_pre_contact():
    # pre-contact frames sit at ~28 deg; post-contact frames are garbage that
    # should be ignored entirely.
    pre = [(-0.5 + 0.05 * i, _canonical_frame(28.0 + (i % 3 - 1))) for i in range(6)]
    post = [(0.1 + 0.05 * i, _canonical_frame(-80.0)) for i in range(6)]
    yaw, samples = yaw_normalise_window(pre + post)
    assert yaw is not None and abs(yaw - 28.0) < 2.0
    assert len(samples) == 6  # only the pre-contact ones
    for _, f in pre:
        assert abs(facing_azimuth(rotate_world_landmarks(f, yaw))) < 3.0


def test_yaw_normalise_window_no_pre_contact_frames():
    # clip cut too tight -- nothing before contact -> no estimate
    frames = [(0.05 * i, _canonical_frame(30.0)) for i in range(8)]
    yaw, samples = yaw_normalise_window(frames)
    assert yaw is None and samples == []


def test_project_canonical_2d_shape_and_visibility():
    world = _canonical_frame(15.0)
    world['nose'] = None
    image = {'left_shoulder': {'x': 0.4, 'y': 0.3, 'visibility': 0.9}}
    proj = project_canonical_2d(world, image)
    assert proj['nose'] is None
    assert proj['left_shoulder']['visibility'] == 0.9
    assert proj['right_shoulder']['visibility'] == 0.0  # absent from image dict
    assert set(proj['left_shoulder']) == {'x', 'y', 'z', 'visibility'}
