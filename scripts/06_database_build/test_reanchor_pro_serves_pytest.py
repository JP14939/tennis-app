"""
Coverage for reanchor_pro_serves.py -- re-anchors serve entries to the
overhead apex. serve_contact_anchor_frame / _pose_context / reextract_for_entry
are stubbed (their math lives in test_serve_anchor_pytest.py and
test_rebuild_helpers_pytest.py); this proves the skip / move / backup /
verdict-log / idempotency plumbing.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reanchor_pro_serves as rps  # noqa: E402
import clip_review_log  # noqa: E402

FPS = 30.0


def _entry(eid, shot_type='serve', swing_id=1):
    return {'id': eid, 'shot_type': shot_type, 'swing_id': swing_id,
            'peak_time': 10.0, 'clip_contact_time_sec': 1.0,
            'trajectory': [{'t': 0.0, 'landmarks': {}}]}


def _ok_reextract(entry, lookup=None, original_shot_type=None):
    return {'status': 'ok', 'trajectory': [{'t': -0.5, 'landmarks': {}}],
            'overlay': [{'t': 0.6, 'landmarks': {}}],
            'new_peak_frame': 300, 'new_peak_time': 10.5}


def _env(tmp_path, monkeypatch, entries, verdicts=(), *, apex_frame=345,
         reextract=_ok_reextract):
    """apex_frame: what serve_contact_anchor_frame returns (clip_start is 300,
    so 345 => new contact 1.5s => +15f from the stubbed 1.0s)."""
    db = {'total': len(entries), 'shots': {'forehand': 0, 'backhand': 0, 'serve': 0}, 'entries': entries}
    for e in entries:
        db['shots'][e['shot_type']] = db['shots'].get(e['shot_type'], 0) + 1
    db_path = tmp_path / 'pro_database.json'
    db_path.write_text(json.dumps(db))
    overlay_path = tmp_path / 'overlay_trajectories.json'
    overlay_path.write_text(json.dumps({e['id']: [{'t': 0.0, 'landmarks': {}}] for e in entries}))
    log_path = tmp_path / 'clip_review_log.jsonl'
    with open(log_path, 'w') as f:
        for rec in verdicts:
            f.write(json.dumps({'entry_id': rec[0], 'verdict': rec[1],
                                'note': rec[2] if len(rec) > 2 else None,
                                'name': None, 'timestamp': 0}) + '\n')

    monkeypatch.setattr(rps, 'PRO_DB_PATH', str(db_path))
    monkeypatch.setattr(rps, 'OVERLAY_DB_PATH', str(overlay_path))
    monkeypatch.setattr(rps, 'build_swing_lookup', lambda: {})
    monkeypatch.setattr(rps, 'reextract_for_entry', reextract)
    monkeypatch.setattr(rps, '_pose_context',
                        lambda entry, orig_st, lookup: (FPS, {1: {}}, 300, 300))
    monkeypatch.setattr(rps, 'serve_contact_anchor_frame',
                        lambda *a, **k: apex_frame)
    monkeypatch.setattr(clip_review_log, 'LOG_PATH', str(log_path))
    return db_path, overlay_path, log_path


def test_audio_marked_serve_is_reanchored(tmp_path, monkeypatch):
    db_path, _, log_path = _env(
        tmp_path, monkeypatch, [_entry('serve_0001')],
        verdicts=[('serve_0001', 'contact_time_corrected', '0.9 -> 1.0 (audio)')])
    rps.reanchor()
    e = json.loads(db_path.read_text())['entries'][0]
    assert e['clip_contact_time_sec'] == 1.5
    assert e['trajectory'] == [{'t': -0.5, 'landmarks': {}}]
    lines = [json.loads(x) for x in log_path.read_text().splitlines() if x.strip()]
    assert lines[-1]['verdict'] == 'contact_time_corrected'
    assert lines[-1]['note'].endswith('(serve apex reanchor)')


def test_human_marked_serve_is_left_untouched(tmp_path, monkeypatch):
    db_path, _, _ = _env(
        tmp_path, monkeypatch, [_entry('serve_0001')],
        verdicts=[('serve_0001', 'contact_time_corrected', '0.9 -> 1.1')])
    rps.reanchor()
    e = json.loads(db_path.read_text())['entries'][0]
    assert e['clip_contact_time_sec'] == 1.0  # unchanged


def test_label_confirmed_serve_is_left_untouched(tmp_path, monkeypatch):
    db_path, _, _ = _env(
        tmp_path, monkeypatch, [_entry('serve_0001')],
        verdicts=[('serve_0001', 'label_confirmed')])
    rps.reanchor()
    assert json.loads(db_path.read_text())['entries'][0]['clip_contact_time_sec'] == 1.0


def test_forehand_entry_is_never_touched(tmp_path, monkeypatch):
    db_path, _, _ = _env(tmp_path, monkeypatch,
                         [_entry('forehand_0001', shot_type='forehand'), _entry('serve_0001')])
    rps.reanchor()
    entries = {e['id']: e for e in json.loads(db_path.read_text())['entries']}
    assert entries['forehand_0001']['clip_contact_time_sec'] == 1.0
    assert entries['serve_0001']['clip_contact_time_sec'] == 1.5


def test_apex_unmeasurable_leaves_entry_byte_identical(tmp_path, monkeypatch):
    db_path, _, _ = _env(tmp_path, monkeypatch, [_entry('serve_0001')], apex_frame=None)
    before = db_path.read_text()
    rps.reanchor()
    assert db_path.read_text() == before


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    db_path, overlay_path, log_path = _env(tmp_path, monkeypatch, [_entry('serve_0001')])
    before = (db_path.read_text(), overlay_path.read_text(), log_path.read_text())
    rps.reanchor(dry_run=True)
    assert (db_path.read_text(), overlay_path.read_text(), log_path.read_text()) == before


def test_rerun_is_idempotent(tmp_path, monkeypatch):
    db_path, _, log_path = _env(tmp_path, monkeypatch, [_entry('serve_0001')])
    rps.reanchor()
    after_first = json.loads(db_path.read_text())['entries'][0]['clip_contact_time_sec']
    n_verdicts_1 = len([x for x in log_path.read_text().splitlines() if x.strip()])
    # second pass: apex still 345 -> new contact still 1.5 -> 0-frame move
    rps.reanchor()
    after_second = json.loads(db_path.read_text())['entries'][0]['clip_contact_time_sec']
    n_verdicts_2 = len([x for x in log_path.read_text().splitlines() if x.strip()])
    assert after_first == after_second == 1.5
    assert n_verdicts_2 == n_verdicts_1  # nothing moved, no new verdict
