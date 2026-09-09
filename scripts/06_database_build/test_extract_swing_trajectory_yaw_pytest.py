"""Tests for extract_swing_trajectory's optional pro-side yaw normalization
(Phase 0). Default / no-world-landmarks must be byte-identical to the old
2D-only builder; with world landmarks + yaw_enabled it rotates the swing to a
canonical facing, same as the user side. Synthetic pose data, no MediaPipe."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trajectory_extraction import (  # noqa: E402
    build_pose_index, build_world_pose_index, extract_swing_trajectory,
)
from viewpoint_normalization import facing_azimuth  # noqa: E402

FPS = 20
PEAK = 200
_NAMES = ['nose', 'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
          'left_wrist', 'right_wrist', 'left_hip', 'right_hip']


def _yaw_xz(x, z, deg):
    a = math.radians(deg)
    return x * math.cos(a) - z * math.sin(a), x * math.sin(a) + z * math.cos(a)


def _frame(fnum, yaw_deg=0.0, with_world=False):
    # canonical stick figure (shoulders wider than hips, square to the camera),
    # optionally yawed about vertical; a slight per-frame wrist wobble so the
    # trajectory isn't degenerate.
    wob = 0.02 * math.sin(fnum / 3.0)
    base = {
        'nose': (0.0, -0.6, 0.0), 'left_shoulder': (-0.20, -0.45, 0.0),
        'right_shoulder': (0.20, -0.45, 0.0), 'left_elbow': (-0.30, -0.2, 0.0),
        'right_elbow': (0.30, -0.2, 0.0), 'left_wrist': (-0.35 + wob, 0.0, 0.0),
        'right_wrist': (0.35 + wob, 0.0, 0.0), 'left_hip': (-0.12, 0.0, 0.0),
        'right_hip': (0.12, 0.0, 0.0),
    }
    img = []
    world = []
    for name, (x, y, z) in base.items():
        rx, rz = _yaw_xz(x, z, yaw_deg)
        img.append({'name': name, 'x': rx + 0.5, 'y': y + 0.5, 'z': rz, 'visibility': 1.0})
        world.append({'name': name, 'x': rx, 'y': y, 'z': rz, 'visibility': 1.0})
    f = {'frame': fnum, 'timestamp': fnum / FPS, 'landmarks': img}
    if with_world:
        f['world_landmarks'] = world
    return f


def _frames(yaw_deg=0.0, with_world=False, lo=170, hi=230):
    return [_frame(f, yaw_deg, with_world) for f in range(lo, hi + 1)]


def test_default_and_no_world_are_identical():
    idx = build_pose_index(_frames(yaw_deg=25.0))
    sw = {'peak_frame': PEAK}
    base = extract_swing_trajectory(sw, idx, FPS)
    assert base and len(base) >= 5
    # yaw_enabled but no world index -> identity
    assert extract_swing_trajectory(sw, idx, FPS, yaw_enabled=True) == base
    # yaw_enabled with an empty world index -> identity
    assert extract_swing_trajectory(sw, idx, FPS, world_pose_index={}, yaw_enabled=True) == base
    # yaw_enabled=False with a world index present -> still identity
    widx = build_world_pose_index(_frames(yaw_deg=25.0, with_world=True))
    assert extract_swing_trajectory(sw, idx, FPS, world_pose_index=widx) == base


def test_return_yaw_reports_applied_rotation():
    idx = build_pose_index(_frames(yaw_deg=25.0))
    sw = {'peak_frame': PEAK}
    traj, applied = extract_swing_trajectory(sw, idx, FPS, return_yaw=True)
    assert traj and applied is None  # no world index -> nothing applied
    frames = _frames(yaw_deg=30.0, with_world=True)
    traj, applied = extract_swing_trajectory(
        {'peak_frame': PEAK}, build_pose_index(frames), FPS,
        world_pose_index=build_world_pose_index(frames), yaw_enabled=True, return_yaw=True)
    assert traj and applied is not None and abs(applied - 30.0) < 8.0


def test_yaw_enabled_rotates_swing_to_canonical():
    frames = _frames(yaw_deg=30.0, with_world=True)
    idx = build_pose_index(frames)
    widx = build_world_pose_index(frames)
    sw = {'peak_frame': PEAK}

    raw = extract_swing_trajectory(sw, idx, FPS)
    corrected = extract_swing_trajectory(sw, idx, FPS, world_pose_index=widx, yaw_enabled=True)
    assert corrected and corrected != raw

    # the corrected contact-frame landmarks should read near-canonical (azimuth ~0)
    contact = min(corrected, key=lambda p: abs(p['t']))['landmarks']
    assert abs(facing_azimuth(contact)) < 6.0
    # the uncorrected one still carries the 30 deg camera yaw
    raw_contact = min(raw, key=lambda p: abs(p['t']))['landmarks']
    assert abs(facing_azimuth(raw_contact)) > 15.0
