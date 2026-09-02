"""
Regression coverage for split_pro_clip.py -- the riskiest new script this
sprint (real pose-data math, id allocation, two file writes). ffmpeg calls
(trim_to_file/trim_in_place) are monkeypatched to recording spies rather
than run for real, same spirit as correct_shot_type.py's tests avoiding
anything filesystem-heavy beyond what's needed to prove the logic.
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import split_pro_clip as spc  # noqa: E402
import clip_review_log  # noqa: E402

FPS = 20


def _landmark(x, y=0.0, z=0.0, visibility=1.0):
    return {'x': x, 'y': y, 'z': z, 'visibility': visibility}


def _pose_frame(frame_num, right_wrist_x):
    """A minimal frame with stable shoulders/hips (for normalisation) and a
    right wrist whose x jumps at exactly one frame -- gives
    compute_wrist_velocity() a single, unambiguous peak."""
    landmarks = [
        {'name': 'nose', **_landmark(0.0, -0.3)},
        {'name': 'left_shoulder', **_landmark(-0.1)},
        {'name': 'right_shoulder', **_landmark(0.1)},
        {'name': 'left_elbow', **_landmark(-0.2, 0.3)},
        {'name': 'right_elbow', **_landmark(0.2, 0.3)},
        {'name': 'left_wrist', **_landmark(-0.3, 0.5, visibility=0.9)},
        {'name': 'right_wrist', **_landmark(right_wrist_x, 0.5, visibility=0.9)},
        {'name': 'left_hip', **_landmark(-0.1, 1.0)},
        {'name': 'right_hip', **_landmark(0.1, 1.0)},
    ]
    return {'frame': frame_num, 'timestamp': frame_num / FPS, 'landmarks': landmarks}


def _make_pose_data(jump_frame, lo=150, hi=270):
    """right_wrist.x is 0.5 up to (not including) jump_frame, then 0.9 from
    jump_frame onward -- one clean velocity spike, attributed to jump_frame."""
    frames = []
    for f in range(lo, hi + 1):
        x = 0.9 if f >= jump_frame else 0.5
        frames.append(_pose_frame(f, x))
    return {'fps': FPS, 'frames': frames}


def _entry(swing_id=4, peak_time=10.0, clip_contact_time_sec=1.0, confidence=0.75):
    return {
        'id': 'forehand_0004', 'shot_type': 'forehand', 'swing_id': swing_id,
        'confidence': confidence, 'peak_time': peak_time,
        'clip_contact_time_sec': clip_contact_time_sec,
        'clip_path': 'forehand/forehand_swing_0004_conf75.mp4',
        'camera_angle': 12.3, 'angle_confidence': 0.8,
        'trajectory': [{'t': 0.0, 'landmarks': {'nose': {'x': 0, 'y': 0, 'z': 0}}}],
    }


def _make_env(tmp_path, monkeypatch, entry, pose_data, extra_entries=None):
    db = {'total': 1, 'shots': {'forehand': 1, 'backhand': 0, 'serve': 0},
          'entries': [entry] + (extra_entries or [])}
    db_path = tmp_path / 'pro_database.json'
    db_path.write_text(json.dumps(db))

    clips_dir = tmp_path / 'clips'
    cropped_dir = tmp_path / 'clips_cropped'
    (clips_dir / 'forehand').mkdir(parents=True)
    (clips_dir / entry['clip_path']).write_bytes(b'video bytes')

    poses_path = tmp_path / 'poses.json'
    poses_path.write_text(json.dumps(pose_data))

    monkeypatch.setattr(spc, 'PRO_DB_PATH', str(db_path))
    monkeypatch.setattr(spc, 'PRO_CLIPS_DIR', str(clips_dir))
    monkeypatch.setattr(spc, 'PRO_CLIPS_CROPPED_DIR', str(cropped_dir))
    monkeypatch.setattr(spc, 'poses_path_for', lambda shot_type, swing_id: str(poses_path))
    monkeypatch.setattr(spc, 'get_duration_sec', lambda path: 4.0)

    trim_calls = []
    monkeypatch.setattr(spc, 'trim_to_file', lambda src, dest, s, e: trim_calls.append(('to_file', src, dest, s, e)))
    monkeypatch.setattr(spc, 'trim_in_place', lambda path, s, e: trim_calls.append(('in_place', path, s, e)))

    monkeypatch.setattr(clip_review_log, 'LOG_PATH', str(tmp_path / 'clip_review_log.jsonl'))

    return db_path, trim_calls


def test_rejects_out_of_order_points(tmp_path, monkeypatch):
    entry = _entry()
    db_path, trim_calls = _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240))
    original_db = db_path.read_text()

    try:
        spc.split_pro_clip('forehand_0004', 2.0, 1.0, 3.0)
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'in order' in str(e)

    assert db_path.read_text() == original_db
    assert trim_calls == []


def test_rejects_half_under_min_clip_sec(tmp_path, monkeypatch):
    entry = _entry()
    db_path, trim_calls = _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240))

    try:
        spc.split_pro_clip('forehand_0004', 0.0, 0.05, 4.0)
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'at least' in str(e)
    assert trim_calls == []


def test_argmax_lands_on_known_peak_frame_and_computes_correct_timing(tmp_path, monkeypatch):
    entry = _entry()
    _make_env(tmp_path, monkeypatch, entry, _make_pose_data(jump_frame=240))

    result = spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0)

    # start_frame_in_source = round(10.0*20) - round(1.0*20) = 200-20 = 180
    # new_half = (1.6, 4.0) -> new_half_start_frame = 180 + round(1.6*20) = 212
    # new_peak_frame = 240 (the synthetic jump) -> contact = (240-212)/20 = 1.4s
    assert result['new_id'] == 'forehand_0900'
    assert result['new_swing_id'] == 900


def test_return_payload_carries_candidate_fields_for_the_review_ui(tmp_path, monkeypatch):
    # DevProClipReviewScreen.js splices result['new_entry'] straight into its
    # in-memory review queue and reads result['original_new_contact_time_sec']
    # for the re-trimmed first half -- both must be present and shaped right.
    entry = _entry(clip_contact_time_sec=1.0, confidence=0.75)
    db_path, _ = _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240))

    result = spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0)

    db = json.loads(db_path.read_text())
    original = next(e for e in db['entries'] if e['id'] == 'forehand_0004')
    assert result['original_new_contact_time_sec'] == original['clip_contact_time_sec']

    new_entry = result['new_entry']
    assert new_entry['id'] == 'forehand_0900'
    assert new_entry['shot_type'] == 'forehand'
    assert new_entry['clip_url'] == '/pro-clips/forehand/forehand_swing_0900_conf75.mp4'
    assert new_entry['confidence'] == 0.75
    assert new_entry['camera_angle'] == 12.3
    assert 'fps' in new_entry
    assert new_entry['clip_contact_time_sec'] == next(
        e for e in db['entries'] if e['id'] == 'forehand_0900'
    )['clip_contact_time_sec']


def test_which_half_keeps_original_contact_first_half(tmp_path, monkeypatch):
    entry = _entry(clip_contact_time_sec=1.0)  # falls in [0, 1.6]
    db_path, trim_calls = _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240))

    spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0)

    db = json.loads(db_path.read_text())
    original = next(e for e in db['entries'] if e['id'] == 'forehand_0004')
    new = next(e for e in db['entries'] if e['id'] == 'forehand_0900')
    # original kept the SAME trajectory object's contents (untouched)
    assert original['trajectory'] == entry['trajectory']
    assert new['trajectory'] != entry['trajectory']


def test_which_half_keeps_original_contact_second_half(tmp_path, monkeypatch):
    entry = _entry(clip_contact_time_sec=3.5)  # falls in [1.6, 4.0]
    # New half here is [0.0, 1.6] of the clip. start_frame_in_source =
    # round(10.0*20) - round(3.5*20) = 130, so the new half's window is
    # source frames [130, 162] -- the synthetic wrist-motion jump has to
    # actually sit inside that range for this scenario (unlike the other
    # tests, where the new half is [1.6, 4.0] -> frames [212, 260]).
    pose_data = _make_pose_data(jump_frame=150, lo=100, hi=200)
    db_path, trim_calls = _make_env(tmp_path, monkeypatch, entry, pose_data)

    result = spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0)

    db = json.loads(db_path.read_text())
    original = next(e for e in db['entries'] if e['id'] == 'forehand_0004')
    # original half is now [1.6, 4.0], contact shifts by -1.6
    assert original['clip_contact_time_sec'] == 1.9
    assert original['trajectory'] == entry['trajectory']
    assert result['new_id'] == 'forehand_0900'


def test_original_entry_id_and_swing_id_never_change(tmp_path, monkeypatch):
    entry = _entry()
    db_path, _ = _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240))

    spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0)

    db = json.loads(db_path.read_text())
    original = next(e for e in db['entries'] if e['id'] == 'forehand_0004')
    assert original['id'] == 'forehand_0004'
    assert original['swing_id'] == 4


def test_new_entry_inherits_camera_angle_and_confidence(tmp_path, monkeypatch):
    entry = _entry(confidence=0.75)
    db_path, _ = _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240))

    spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0)

    db = json.loads(db_path.read_text())
    new = next(e for e in db['entries'] if e['id'] == 'forehand_0900')
    assert new['camera_angle'] == entry['camera_angle']
    assert new['angle_confidence'] == entry['angle_confidence']
    assert new['confidence'] == 0.75


def test_swing_id_allocation_skips_used_ids_in_band(tmp_path, monkeypatch):
    entry = _entry()
    pre_existing = {**_entry(swing_id=900), 'id': 'forehand_0900'}
    db_path, _ = _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240), extra_entries=[pre_existing])

    result = spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0)

    assert result['new_swing_id'] == 901


def test_swing_id_band_exhausted_raises(tmp_path, monkeypatch):
    entry = _entry()
    used_up = [{**_entry(swing_id=sid), 'id': f'forehand_{sid:04d}'} for sid in range(900, 1000)]
    db_path, trim_calls = _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240), extra_entries=used_up)

    try:
        spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0)
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'No free split swing_id' in str(e)
    assert trim_calls == []


def test_trajectory_extraction_failure_raises_before_any_file_mutation(tmp_path, monkeypatch):
    entry = _entry()
    db_path, trim_calls = _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240))
    original_db = db_path.read_text()
    monkeypatch.setattr(spc, 'extract_swing_trajectory', lambda swing, pose_index, fps: None)

    try:
        spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0)
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'trajectory' in str(e)

    assert db_path.read_text() == original_db
    assert trim_calls == []


def test_logs_split_verdict_against_original_id_only(tmp_path, monkeypatch):
    entry = _entry()
    _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240))

    spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0, name='Federer FH')

    verdicts = clip_review_log.get_latest_verdicts()
    assert verdicts == {'forehand_0004': 'split'}


def test_trims_call_correct_ranges(tmp_path, monkeypatch):
    entry = _entry()
    db_path, trim_calls = _make_env(tmp_path, monkeypatch, entry, _make_pose_data(240))

    spc.split_pro_clip('forehand_0004', 0.0, 1.6, 4.0)

    kinds = {c[0] for c in trim_calls}
    assert 'to_file' in kinds and 'in_place' in kinds
    to_file_call = next(c for c in trim_calls if c[0] == 'to_file')
    assert to_file_call[3:] == (1.6, 4.0)  # new half range
    in_place_call = next(c for c in trim_calls if c[0] == 'in_place')
    assert in_place_call[2:] == (0.0, 1.6)  # original half range
