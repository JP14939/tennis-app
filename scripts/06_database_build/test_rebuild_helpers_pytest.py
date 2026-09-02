"""
Coverage for rebuild_helpers.reextract_for_entry() -- the frame math that
re-anchors a pro entry's trajectory + overlay to a corrected contact time.
Pose data is synthetic; no real files, no MediaPipe.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rebuild_helpers as rh  # noqa: E402
from trajectory_extraction import build_pose_index, PRE_SEC  # noqa: E402

FPS = 20


def _landmark(x, y=0.0, z=0.0, visibility=1.0):
    return {'x': x, 'y': y, 'z': z, 'visibility': visibility}


def _pose_frame(frame_num):
    landmarks = [
        {'name': 'nose', **_landmark(0.0, -0.3)},
        {'name': 'left_shoulder', **_landmark(-0.1)},
        {'name': 'right_shoulder', **_landmark(0.1)},
        {'name': 'left_elbow', **_landmark(-0.2, 0.3)},
        {'name': 'right_elbow', **_landmark(0.2, 0.3)},
        {'name': 'left_wrist', **_landmark(-0.3, 0.5, visibility=0.9)},
        {'name': 'right_wrist', **_landmark(0.4, 0.5, visibility=0.9)},
        {'name': 'left_hip', **_landmark(-0.1, 1.0)},
        {'name': 'right_hip', **_landmark(0.1, 1.0)},
    ]
    return {'frame': frame_num, 'timestamp': frame_num / FPS, 'landmarks': landmarks}


def _pose_index(lo=100, hi=400):
    return build_pose_index([_pose_frame(f) for f in range(lo, hi + 1)])


def _entry(shot_type='forehand', swing_id=4, peak_time=10.0, clip_contact_time_sec=1.4):
    return {
        'id': f'{shot_type}_{swing_id:04d}', 'shot_type': shot_type, 'swing_id': swing_id,
        'peak_time': peak_time, 'clip_contact_time_sec': clip_contact_time_sec,
        'trajectory': [{'t': 0.0, 'landmarks': {}}],
    }


def test_batch_reextract_anchors_on_start_frame_plus_contact(monkeypatch):
    monkeypatch.setattr(rh, '_load_pose_index', lambda path: (FPS, _pose_index()))
    lookup = {('forehand', 4): {'poses_path': 'x', 'fps': FPS,
                                'orig_peak_frame': 200, 'start_frame': 180}}
    entry = _entry(clip_contact_time_sec=1.4)

    res = rh.reextract_for_entry(entry, lookup=lookup)

    assert res['status'] == 'ok'
    # new_peak_frame = start_frame(180) + round(1.4 * 20) = 208
    assert res['new_peak_frame'] == 208
    assert res['new_peak_time'] == round(208 / FPS, 3)
    # trajectory t is contact-relative -> starts ~ -PRE_SEC
    assert abs(res['trajectory'][0]['t'] + PRE_SEC) < 0.11
    # overlay t is clip-relative (origin = start_frame) -> first sample well positive
    assert res['overlay'][0]['t'] > 0
    assert entry['trajectory'] == [{'t': 0.0, 'landmarks': {}}]  # not mutated


def test_single_reextract_uses_peak_time_minus_prior_contact(monkeypatch, tmp_path):
    poses_file = tmp_path / 'poses.json'
    poses_file.write_text('{}')
    monkeypatch.setattr(rh, 'poses_path_for', lambda st, sid: str(poses_file))
    monkeypatch.setattr(rh, '_load_pose_index', lambda path: (FPS, _pose_index()))
    entry = _entry(peak_time=10.0, clip_contact_time_sec=1.4)

    res = rh.reextract_for_entry(entry, single=True, prior_contact_time_sec=1.0)

    # clip_start = round(10*20) - round(1.0*20) = 180 ; new_peak = 180 + round(1.4*20) = 208
    assert res['status'] == 'ok'
    assert res['new_peak_frame'] == 208


def test_missing_lookup_batch(monkeypatch):
    monkeypatch.setattr(rh, '_load_pose_index', lambda path: (FPS, _pose_index()))
    res = rh.reextract_for_entry(_entry(), lookup={})
    assert res['status'] == 'missing_lookup'
    assert res['trajectory'] is None


def test_missing_lookup_single_when_no_pose_file(monkeypatch):
    monkeypatch.setattr(rh, 'poses_path_for', lambda st, sid: None)
    res = rh.reextract_for_entry(_entry(), single=True, prior_contact_time_sec=1.0)
    assert res['status'] == 'missing_lookup'


def test_too_few_points(monkeypatch):
    monkeypatch.setattr(rh, '_load_pose_index', lambda path: (FPS, _pose_index()))
    monkeypatch.setattr(rh, 'extract_swing_trajectory', lambda swing, idx, fps: None)
    lookup = {('forehand', 4): {'poses_path': 'x', 'fps': FPS,
                                'orig_peak_frame': 200, 'start_frame': 180}}
    res = rh.reextract_for_entry(_entry(), lookup=lookup)
    assert res['status'] == 'too_few_points'
    assert res['new_peak_frame'] == 208  # still reported
    assert res['overlay'] is None
