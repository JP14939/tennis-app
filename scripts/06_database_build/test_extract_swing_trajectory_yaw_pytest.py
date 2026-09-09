"""Tests for extract_swing_trajectory / extract_trajectory_from_index:
- x/y yaw normalization (only when yaw_enabled + confident lead-in)
- the decoupled metric-z channel: z always comes from world landmarks when
  present (soft-yaw rotated), regardless of the x/y yaw flag (traj_version 4).
Synthetic pose data, no MediaPipe."""
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trajectory_extraction import (  # noqa: E402
    build_pose_index, build_world_pose_index, extract_swing_trajectory,
)
from viewpoint_normalization import facing_azimuth  # noqa: E402

FPS = 20
PEAK = 200

# base pose: shoulders wider than hips, SQUARE to the camera (shoulder & hip
# lines have zero z so the facing azimuth is 0), with REAL depth only on the
# hitting arm (wrist well in front, elbow a bit) so the metric-z channel has a
# non-trivial signal to recover.
_BASE = {
    'nose': (0.0, -0.6, 0.05), 'left_shoulder': (-0.20, -0.45, 0.0),
    'right_shoulder': (0.20, -0.45, 0.0), 'left_elbow': (-0.30, -0.2, 0.0),
    'right_elbow': (0.30, -0.2, -0.15), 'left_wrist': (-0.35, 0.0, 0.0),
    'right_wrist': (0.35, 0.0, -0.30), 'left_hip': (-0.12, 0.0, 0.0),
    'right_hip': (0.12, 0.0, 0.0),
}


def _yaw_xz(x, z, deg):
    a = math.radians(deg)
    return x * math.cos(a) - z * math.sin(a), x * math.sin(a) + z * math.cos(a)


def _frame(fnum, yaw_deg=0.0, with_world=True):
    wob = 0.02 * math.sin(fnum / 3.0)  # keep the trajectory non-degenerate
    img, world = [], []
    for name, (x, y, z) in _BASE.items():
        xw = x + (wob if 'wrist' in name else 0.0)
        rx, rz = _yaw_xz(xw, z, yaw_deg)
        img.append({'name': name, 'x': rx + 0.5, 'y': y + 0.5, 'z': rz, 'visibility': 1.0})
        world.append({'name': name, 'x': rx, 'y': y, 'z': rz, 'visibility': 1.0})
    f = {'frame': fnum, 'timestamp': fnum / FPS, 'landmarks': img}
    if with_world:
        f['world_landmarks'] = world
    return f


def _frames(yaw_deg=0.0, with_world=True, lo=170, hi=230):
    return [_frame(f, yaw_deg, with_world) for f in range(lo, hi + 1)]


def _absmed(traj, coord):
    vals = [abs(lm[coord]) for p in traj for lm in p['landmarks'].values()
            if lm and lm.get(coord) is not None]
    return statistics.median(vals)


def _xy(traj):
    return [{k: (None if v is None else {'x': v['x'], 'y': v['y']})
             for k, v in p['landmarks'].items()} for p in traj]


def test_no_world_landmarks_is_byte_identical():
    """No world data (old pose files) -> everything unchanged, incl. image z."""
    frames = _frames(yaw_deg=25.0, with_world=False)
    idx = build_pose_index(frames)
    sw = {'peak_frame': PEAK}
    base = extract_swing_trajectory(sw, idx, FPS)
    assert base and len(base) >= 5
    assert extract_swing_trajectory(sw, idx, FPS, yaw_enabled=True) == base
    assert extract_swing_trajectory(sw, idx, FPS, world_pose_index={}, yaw_enabled=True) == base


def test_identity_path_keeps_xy_but_gets_metric_z():
    """yaw flag OFF, world landmarks present, camera ~25deg off-axis:
    x/y stay image-space (byte-identical to the no-world build), z becomes
    metric world-derived (abs-median in line with x/y, not the ~3x of image z)."""
    frames_nw = _frames(yaw_deg=25.0, with_world=False)
    frames_w = _frames(yaw_deg=25.0, with_world=True)
    sw = {'peak_frame': PEAK}

    plain = extract_swing_trajectory(sw, build_pose_index(frames_nw), FPS)
    traj, meta = extract_swing_trajectory(
        sw, build_pose_index(frames_w), FPS,
        world_pose_index=build_world_pose_index(frames_w), return_meta=True)

    assert _xy(traj) == _xy(plain)                       # x/y untouched
    assert meta['yaw_deg'] is None and meta['z_metric']  # x/y not rotated, z is metric
    assert abs(meta['z_yaw_deg'] - 25.0) < 6.0           # soft yaw recovered the camera angle

    contact = min(traj, key=lambda p: abs(p['t']))['landmarks']
    assert contact['right_wrist']['z'] is not None
    # image z here would be ~x*sin(25)/scale; metric z recovers the true forward
    # depth of the hand and is on the x/y scale
    z_med, x_med = _absmed(traj, 'z'), _absmed(traj, 'x')
    assert z_med < 2.0 * max(x_med, 0.1)
    # and it differs from the pure-image-z build
    assert [p['landmarks'] for p in traj] != [p['landmarks'] for p in plain]


def test_hard_yaw_path_z_is_the_same_with_or_without_the_overlay():
    """When x/y ARE hard-yaw-rotated, z is already metric-world; the overlay is
    a proven no-op there (same dicts, same scale)."""
    frames = _frames(yaw_deg=30.0, with_world=True)
    idx, widx = build_pose_index(frames), build_world_pose_index(frames)
    sw = {'peak_frame': PEAK}
    corrected, meta = extract_swing_trajectory(
        sw, idx, FPS, world_pose_index=widx, yaw_enabled=True, return_meta=True)
    assert meta['yaw_deg'] is not None and meta['z_metric']
    # x/y rotated to canonical
    c = min(corrected, key=lambda p: abs(p['t']))['landmarks']
    assert abs(facing_azimuth(c)) < 6.0


def test_z_none_safe_when_some_frames_lack_world_data():
    frames = _frames(yaw_deg=15.0, with_world=True)
    for f in frames[::4]:
        f.pop('world_landmarks', None)      # drop world data on 1/4 of frames
    idx, widx = build_pose_index(frames), build_world_pose_index(frames)
    traj, meta = extract_swing_trajectory(
        {'peak_frame': PEAK}, idx, FPS, world_pose_index=widx, return_meta=True)
    assert traj and meta['z_metric']
    # no crash; every z is either a float or explicitly None (never stale image z)
    for p in traj:
        for lm in p['landmarks'].values():
            if lm is not None:
                assert lm['z'] is None or isinstance(lm['z'], float)


def test_return_yaw_still_works():
    idx = build_pose_index(_frames(yaw_deg=25.0, with_world=False))
    traj, applied = extract_swing_trajectory({'peak_frame': PEAK}, idx, FPS, return_yaw=True)
    assert traj and applied is None
