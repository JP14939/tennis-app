"""
Coverage for rebuild_pro_database_from_verdicts.py -- applies Pro Clip
Review verdicts to pro_database.json + the overlay file. reextract_for_entry
and build_swing_lookup are stubbed (their math lives in
test_rebuild_helpers_pytest.py); this proves the drop / recount / backup /
idempotency plumbing.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rebuild_pro_database_from_verdicts as rpd  # noqa: E402
import clip_review_log  # noqa: E402


def _entry(eid, shot_type='forehand', swing_id=1):
    return {
        'id': eid, 'shot_type': shot_type, 'swing_id': swing_id,
        'peak_time': 10.0, 'clip_contact_time_sec': 1.0,
        'trajectory': [{'t': 0.0, 'landmarks': {}}],
    }


def _fresh_traj_stub(entry, lookup=None, original_shot_type=None):
    return {'status': 'ok',
            'trajectory': [{'t': -0.5, 'landmarks': {}}],
            'overlay': [{'t': 0.6, 'landmarks': {}}],
            'new_peak_frame': 210, 'new_peak_time': 10.5}


def _missing_stub(entry, lookup=None, original_shot_type=None):
    return {'status': 'missing_lookup', 'trajectory': None, 'overlay': None,
            'new_peak_frame': None, 'new_peak_time': None}


def _env(tmp_path, monkeypatch, entries, verdicts, overlays=None, reextract=_fresh_traj_stub):
    db = {'total': len(entries), 'shots': {'forehand': 0, 'backhand': 0, 'serve': 0},
          'entries': entries}
    for e in entries:
        db['shots'][e['shot_type']] = db['shots'].get(e['shot_type'], 0) + 1

    db_path = tmp_path / 'pro_database.json'
    db_path.write_text(json.dumps(db))
    overlay_path = tmp_path / 'overlay_trajectories.json'
    overlay_path.write_text(json.dumps(overlays if overlays is not None else
                                       {e['id']: [{'t': 0.0, 'landmarks': {}}] for e in entries}))
    log_path = tmp_path / 'clip_review_log.jsonl'
    with open(log_path, 'w') as f:
        for eid, v in verdicts.items():
            f.write(json.dumps({'entry_id': eid, 'verdict': v, 'note': None,
                                'name': None, 'timestamp': 0}) + '\n')

    monkeypatch.setattr(rpd, 'PRO_DB_PATH', str(db_path))
    monkeypatch.setattr(rpd, 'OVERLAY_DB_PATH', str(overlay_path))
    monkeypatch.setattr(rpd, 'build_swing_lookup', lambda: {})
    monkeypatch.setattr(rpd, 'reextract_for_entry', reextract)
    monkeypatch.setattr(clip_review_log, 'LOG_PATH', str(log_path))
    return db_path, overlay_path


def test_contact_correction_reextracts_trajectory_and_overlay(tmp_path, monkeypatch):
    db_path, overlay_path = _env(
        tmp_path, monkeypatch,
        [_entry('forehand_0001'), _entry('forehand_0002', swing_id=2)],
        {'forehand_0001': 'contact_time_corrected'},
    )
    rpd.rebuild()

    entries = {e['id']: e for e in json.loads(db_path.read_text())['entries']}
    assert entries['forehand_0001']['trajectory'] == [{'t': -0.5, 'landmarks': {}}]
    assert entries['forehand_0001']['peak_time'] == 10.5
    assert entries['forehand_0002']['trajectory'] == [{'t': 0.0, 'landmarks': {}}]  # untouched

    overlays = json.loads(overlay_path.read_text())
    assert overlays['forehand_0001'] == [{'t': 0.6, 'landmarks': {}}]


def test_excluded_entries_dropped_from_db_and_overlays(tmp_path, monkeypatch):
    db_path, overlay_path = _env(
        tmp_path, monkeypatch,
        [_entry('forehand_0001'), _entry('forehand_0002', swing_id=2),
         _entry('backhand_0001', shot_type='backhand')],
        {'forehand_0002': 'excluded', 'backhand_0001': 'mismatched'},
    )
    rpd.rebuild()

    db = json.loads(db_path.read_text())
    ids = {e['id'] for e in db['entries']}
    assert ids == {'forehand_0001'}
    assert db['total'] == 1
    assert db['shots'] == {'forehand': 1, 'backhand': 0, 'serve': 0}
    assert set(json.loads(overlay_path.read_text())) == {'forehand_0001'}


def test_missing_lookup_keeps_entry_untouched(tmp_path, monkeypatch):
    db_path, _ = _env(
        tmp_path, monkeypatch, [_entry('forehand_0001')],
        {'forehand_0001': 'contact_time_corrected'}, reextract=_missing_stub,
    )
    rpd.rebuild()

    entry = json.loads(db_path.read_text())['entries'][0]
    assert entry['id'] == 'forehand_0001'
    assert entry['trajectory'] == [{'t': 0.0, 'landmarks': {}}]
    assert entry['peak_time'] == 10.0


def test_ok_and_label_confirmed_verdicts_are_left_alone(tmp_path, monkeypatch):
    db_path, _ = _env(
        tmp_path, monkeypatch,
        [_entry('forehand_0001'), _entry('forehand_0002', swing_id=2)],
        {'forehand_0001': 'ok', 'forehand_0002': 'label_confirmed'},
    )
    rpd.rebuild()

    db = json.loads(db_path.read_text())
    assert {e['id'] for e in db['entries']} == {'forehand_0001', 'forehand_0002'}
    assert all(e['trajectory'] == [{'t': 0.0, 'landmarks': {}}] for e in db['entries'])


def test_writes_a_backup(tmp_path, monkeypatch):
    db_path, _ = _env(tmp_path, monkeypatch, [_entry('forehand_0001')],
                      {'forehand_0001': 'excluded'})
    rpd.rebuild()
    backups = [p for p in os.listdir(tmp_path)
               if p.startswith('pro_database_backup_pre_verdict_rebuild_')]
    assert len(backups) == 1


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    db_path, _ = _env(tmp_path, monkeypatch, [_entry('forehand_0001')],
                      {'forehand_0001': 'excluded'})
    before = db_path.read_text()
    rpd.rebuild(dry_run=True)
    assert db_path.read_text() == before
    assert not any(p.startswith('pro_database_backup') for p in os.listdir(tmp_path))


def test_idempotent(tmp_path, monkeypatch):
    db_path, _ = _env(
        tmp_path, monkeypatch,
        [_entry('forehand_0001'), _entry('forehand_0002', swing_id=2)],
        {'forehand_0001': 'contact_time_corrected', 'forehand_0002': 'excluded'},
    )
    rpd.rebuild()
    after_first = json.loads(db_path.read_text())
    rpd.rebuild()
    after_second = json.loads(db_path.read_text())
    assert after_first == after_second


def _preds_file(tmp_path, preds):
    p = tmp_path / 'preds.json'
    p.write_text(json.dumps(preds))
    return str(p)


def test_confident_audio_prediction_applied_and_logged(tmp_path, monkeypatch):
    db_path, overlay_path = _env(
        tmp_path, monkeypatch,
        [_entry('forehand_0001'), _entry('forehand_0002', swing_id=2)],
        {'forehand_0001': 'label_confirmed', 'forehand_0002': 'label_confirmed'},
    )
    preds = _preds_file(tmp_path, {
        'forehand_0001': {'status': 'ok', 'confident': True, 'contact_time_sec': 1.31},
        'forehand_0002': {'status': 'ok', 'confident': False, 'contact_time_sec': 0.4},
    })
    rpd.rebuild(contact_predictions_path=preds)

    entries = {e['id']: e for e in json.loads(db_path.read_text())['entries']}
    assert entries['forehand_0001']['clip_contact_time_sec'] == 1.31
    assert entries['forehand_0001']['trajectory'] == [{'t': -0.5, 'landmarks': {}}]
    assert entries['forehand_0002']['clip_contact_time_sec'] == 1.0  # flagged, untouched

    log = [json.loads(x) for x in open(clip_review_log.LOG_PATH) if x.strip()]
    audio_rows = [r for r in log if r['verdict'] == 'contact_time_corrected'
                  and (r.get('note') or '').endswith('(audio)')]
    assert [r['entry_id'] for r in audio_rows] == ['forehand_0001']


def test_audio_fill_is_idempotent(tmp_path, monkeypatch):
    db_path, _ = _env(
        tmp_path, monkeypatch, [_entry('forehand_0001')],
        {'forehand_0001': 'label_confirmed'},
    )
    preds = _preds_file(tmp_path, {
        'forehand_0001': {'status': 'ok', 'confident': True, 'contact_time_sec': 1.31},
    })
    rpd.rebuild(contact_predictions_path=preds)
    first = json.loads(db_path.read_text())
    rpd.rebuild(contact_predictions_path=preds)   # 2nd run sees the logged verdict
    assert json.loads(db_path.read_text()) == first


def test_hand_mark_wins_over_audio_prediction(tmp_path, monkeypatch):
    db_path, _ = _env(
        tmp_path, monkeypatch, [_entry('forehand_0001', swing_id=1)],
        {'forehand_0001': 'contact_time_corrected'},
    )
    preds = _preds_file(tmp_path, {
        'forehand_0001': {'status': 'ok', 'confident': True, 'contact_time_sec': 9.9},
    })
    rpd.rebuild(contact_predictions_path=preds)
    entry = json.loads(db_path.read_text())['entries'][0]
    assert entry['clip_contact_time_sec'] == 1.0  # audio 9.9 never applied


def test_apply_all_audio_applies_low_confidence_and_logs_nothing(tmp_path, monkeypatch):
    db_path, _ = _env(
        tmp_path, monkeypatch,
        [_entry('forehand_0001'), _entry('forehand_0002', swing_id=2)],
        {'forehand_0001': 'label_confirmed', 'forehand_0002': 'label_confirmed'},
    )
    preds = _preds_file(tmp_path, {
        'forehand_0001': {'status': 'ok', 'confident': True, 'contact_time_sec': 1.31},
        'forehand_0002': {'status': 'ok', 'confident': False, 'contact_time_sec': 0.9},
    })
    rpd.rebuild(contact_predictions_path=preds, apply_all_audio=True)

    entries = {e['id']: e for e in json.loads(db_path.read_text())['entries']}
    assert entries['forehand_0001']['clip_contact_time_sec'] == 1.31
    assert entries['forehand_0002']['clip_contact_time_sec'] == 0.9   # low-confidence applied too
    assert entries['forehand_0002']['trajectory'] == [{'t': -0.5, 'landmarks': {}}]

    # no verdict logged -> both stay reviewable
    log = [json.loads(x) for x in open(clip_review_log.LOG_PATH) if x.strip()]
    assert not [r for r in log if (r.get('note') or '').endswith('(audio)')]


def test_corrupt_overlay_file_leaves_it_untouched(tmp_path, monkeypatch):
    db_path, overlay_path = _env(tmp_path, monkeypatch, [_entry('forehand_0001')],
                                 {'forehand_0001': 'contact_time_corrected'})
    overlay_path.write_text('{"forehand_0001": [{"t": 0.0, ')  # truncated
    corrupt = overlay_path.read_text()
    rpd.rebuild()
    assert overlay_path.read_text() == corrupt  # not clobbered
    # db still rebuilt
    assert json.loads(db_path.read_text())['entries'][0]['trajectory'] == [{'t': -0.5, 'landmarks': {}}]
