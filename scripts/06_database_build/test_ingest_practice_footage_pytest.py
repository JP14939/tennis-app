"""Coverage for ingest_practice_footage.py's pure helpers -- id math, the
single-person quality gate, and the append-into-live-DB merge (skip existing,
recount, backup). The heavy detect/verify/classify path is not unit-tested
(it drives MediaPipe + Claude); it's exercised by the real yield-probe run."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_practice_footage as ing  # noqa: E402


def test_video_index():
    assert ing._video_index('practice_02') == 2
    assert ing._video_index('practice_14') == 14
    assert ing._video_index('practice') == 0


def test_quality_gate():
    ok, why = ing._passes_quality_gate({'contact_method': 'ball_occlusion_gap(3f)'}, [1, 2, 3, 4, 5])
    assert ok and why is None

    ok, why = ing._passes_quality_gate({'contact_method': 'ball_occlusion_gap(3f)'}, None)
    assert not ok and why == 'sparse_trajectory'

    ok, why = ing._passes_quality_gate(
        {'contact_method': 'wrist_velocity_fallback', 'contact_confidence': 0.3}, [1, 2, 3, 4, 5])
    assert not ok and why == 'no_contact_evidence'

    # fallback method but audio rescued the contact frame -> keep
    ok, _ = ing._passes_quality_gate(
        {'contact_method': 'wrist_velocity_fallback', 'contact_confidence': 0.3,
         'contact_time_sec_audio': 1.2}, [1, 2, 3, 4, 5])
    assert ok


def _entry(eid, shot_type='forehand'):
    return {'id': eid, 'shot_type': shot_type, 'swing_id': int(eid.split('_')[-1]),
            'trajectory': [{'t': 0.0, 'landmarks': {}}]}


def test_merge_into_db_appends_skips_existing_recounts_and_backs_up(tmp_path, monkeypatch):
    db_path = tmp_path / 'pro_database.json'
    db_path.write_text(json.dumps({
        'total': 2, 'shots': {'forehand': 2, 'backhand': 0, 'serve': 0},
        'entries': [_entry('forehand_0001'), _entry('practice_100001')],
    }))
    ov_path = tmp_path / 'overlay_trajectories.json'
    ov_path.write_text(json.dumps({'forehand_0001': [], 'practice_100001': []}))
    monkeypatch.setattr(ing, 'PRO_DB_PATH', str(db_path))
    monkeypatch.setattr(ing, 'OVERLAY_DB_PATH', str(ov_path))

    n = ing._merge_into_db(
        [_entry('practice_100001', 'forehand'),         # already present -> skipped
         _entry('practice_100002', 'backhand'),
         _entry('practice_100003', 'serve')],
        {'practice_100002': [{'t': 0}], 'practice_100003': [{'t': 0}]},
    )

    assert n == 2
    db = json.loads(db_path.read_text())
    assert db['total'] == 4
    assert db['shots'] == {'forehand': 2, 'backhand': 1, 'serve': 1}
    assert {e['id'] for e in db['entries']} == {
        'forehand_0001', 'practice_100001', 'practice_100002', 'practice_100003'}
    assert set(json.loads(ov_path.read_text())) == {
        'forehand_0001', 'practice_100001', 'practice_100002', 'practice_100003'}
    assert any(p.startswith('pro_database_backup_pre_practice_') for p in os.listdir(tmp_path))
