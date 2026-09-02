"""
Regression coverage for correct_contact_time.py. clip_contact_time_sec is
the clip-playback seek target; entry['trajectory'] (re-extracted here around
the corrected contact frame) is what compare_swing.py's DTW distance is
computed against. The original value came from an automated wrist-velocity
peak detector (see backfill_clip_contact_time.py), never manually verified
at scale. No clip file ever moves here.

reextract_for_entry() (rebuild_helpers.py) needs real on-disk pose data, so
it's stubbed in these tests -- its own math is covered by
test_rebuild_helpers_pytest.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import correct_contact_time as cct  # noqa: E402
import clip_review_log  # noqa: E402


def _ok_stub(*a, **k):
    return {'status': 'ok', 'trajectory': [{'t': -0.5, 'landmarks': {}}],
            'overlay': [{'t': 0.6, 'landmarks': {}}],
            'new_peak_frame': 123, 'new_peak_time': 2.05}


def _missing_stub(*a, **k):
    return {'status': 'missing_lookup', 'trajectory': None, 'overlay': None,
            'new_peak_frame': None, 'new_peak_time': None}


def _make_db(tmp_path, entry, monkeypatch, reextract=_ok_stub):
    db_path = tmp_path / 'pro_database.json'
    db_path.write_text(json.dumps({'entries': [entry]}))
    overlay_path = tmp_path / 'overlay_trajectories.json'
    overlay_path.write_text(json.dumps({'forehand_0004': [{'t': 0.0, 'landmarks': {}}]}))

    monkeypatch.setattr(cct, 'PRO_DB_PATH', str(db_path))
    monkeypatch.setattr(cct, 'OVERLAY_DB_PATH', str(overlay_path))
    monkeypatch.setattr(cct, 'reextract_for_entry', reextract)
    monkeypatch.setattr(clip_review_log, 'LOG_PATH', str(tmp_path / 'clip_review_log.jsonl'))

    return db_path, overlay_path


def _entry(clip_contact_time_sec=1.001):
    return {
        'id': 'forehand_0004', 'shot_type': 'forehand', 'swing_id': 4,
        'clip_path': 'forehand/swing_0004.mp4', 'peak_time': 6.9,
        'clip_contact_time_sec': clip_contact_time_sec,
        'trajectory': [{'t': -0.3, 'landmarks': {}}],
    }


def test_updates_contact_time_trajectory_and_rewrites_db(tmp_path, monkeypatch):
    db_path, overlay_path = _make_db(tmp_path, _entry(), monkeypatch)

    result = cct.correct_contact_time('forehand_0004', 1.24)

    assert result['old_contact_time_sec'] == 1.001
    assert result['new_contact_time_sec'] == 1.24
    assert result['trajectory_updated'] is True
    assert 'warning' not in result

    entry = json.loads(db_path.read_text())['entries'][0]
    assert entry['clip_contact_time_sec'] == 1.24
    assert entry['trajectory'] == [{'t': -0.5, 'landmarks': {}}]
    assert entry['peak_time'] == 2.05
    assert entry['shot_type'] == 'forehand'  # untouched
    assert entry['clip_path'] == 'forehand/swing_0004.mp4'  # untouched

    overlays = json.loads(overlay_path.read_text())
    assert overlays['forehand_0004'] == [{'t': 0.6, 'landmarks': {}}]


def test_missing_pose_data_still_corrects_scalar_and_logs(tmp_path, monkeypatch):
    db_path, overlay_path = _make_db(tmp_path, _entry(), monkeypatch, reextract=_missing_stub)

    result = cct.correct_contact_time('forehand_0004', 1.24)

    assert result['trajectory_updated'] is False
    assert result['warning'] == 'missing_lookup'

    entry = json.loads(db_path.read_text())['entries'][0]
    assert entry['clip_contact_time_sec'] == 1.24
    assert entry['trajectory'] == [{'t': -0.3, 'landmarks': {}}]  # left as-is
    assert entry['peak_time'] == 6.9  # left as-is
    # overlay untouched
    assert json.loads(overlay_path.read_text())['forehand_0004'] == [{'t': 0.0, 'landmarks': {}}]

    assert clip_review_log.get_latest_verdicts() == {'forehand_0004': 'contact_time_corrected'}


def test_non_numeric_input_is_rejected_without_touching_the_file(tmp_path, monkeypatch):
    db_path, _ = _make_db(tmp_path, _entry(), monkeypatch)
    original_db = db_path.read_text()

    try:
        cct.correct_contact_time('forehand_0004', 'not a number')
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'must be a number' in str(e)

    assert db_path.read_text() == original_db


def test_out_of_range_input_is_rejected(tmp_path, monkeypatch):
    _make_db(tmp_path, _entry(), monkeypatch)

    for bad in (999.0, -5.0):
        try:
            cct.correct_contact_time('forehand_0004', bad)
            assert False, 'expected ValueError'
        except ValueError as e:
            assert 'out of expected range' in str(e)


def test_correcting_to_the_same_value_is_rejected(tmp_path, monkeypatch):
    _make_db(tmp_path, _entry(clip_contact_time_sec=1.001), monkeypatch)

    try:
        cct.correct_contact_time('forehand_0004', 1.001)
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'already has contact time' in str(e)


def test_unknown_id_is_rejected(tmp_path, monkeypatch):
    _make_db(tmp_path, _entry(), monkeypatch)

    try:
        cct.correct_contact_time('does_not_exist', 1.24)
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'No pro database entry' in str(e)


def test_logs_a_contact_time_corrected_verdict_with_old_and_new(tmp_path, monkeypatch):
    _make_db(tmp_path, _entry(clip_contact_time_sec=1.001), monkeypatch)
    cct.correct_contact_time('forehand_0004', 1.24, name='Federer FH')

    verdicts = clip_review_log.get_latest_verdicts()
    assert verdicts == {'forehand_0004': 'contact_time_corrected'}

    with open(clip_review_log.LOG_PATH) as f:
        record = json.loads(f.readline())
    assert record['note'] == '1.001 -> 1.24'
    assert record['name'] == 'Federer FH'
