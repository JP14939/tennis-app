"""
Coverage for extract_training_features_from_pro_verdicts.py -- verdict
filtering + row shaping. MediaPipe (get_poses) and extract_for_clip are
stubbed; the real pose math is covered by test_extract_training_features_pytest.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_training_features_from_pro_verdicts as ex  # noqa: E402
import clip_review_log  # noqa: E402

FEATS = {n: 0.1 for n in ('rw_y_rel_shoulder',)}


def _env(tmp_path, monkeypatch, entries, verdicts, feats_for=None):
    db_path = tmp_path / 'pro_database.json'
    db_path.write_text(json.dumps({'entries': entries}))
    log_path = tmp_path / 'clip_review_log.jsonl'
    with open(log_path, 'w') as f:
        for eid, v in verdicts.items():
            f.write(json.dumps({'entry_id': eid, 'verdict': v, 'note': None,
                                'name': None, 'timestamp': 0}) + '\n')
    out_path = tmp_path / 'training_features_from_pro.json'
    clips_dir = tmp_path / 'clips'
    (clips_dir / 'forehand').mkdir(parents=True)
    (clips_dir / 'backhand').mkdir(parents=True)

    for e in entries:
        (clips_dir / e['clip_path']).write_bytes(b'v')

    monkeypatch.setattr(ex, 'PRO_DB_PATH', str(db_path))
    monkeypatch.setattr(ex, 'PRO_CLIPS_DIR', str(clips_dir))
    monkeypatch.setattr(ex, 'OUTPUT_PATH', str(out_path))
    monkeypatch.setattr(clip_review_log, 'LOG_PATH', str(log_path))
    monkeypatch.setattr(ex, '_probe_fps', lambda p: 30.0)
    monkeypatch.setattr(ex, 'get_poses', lambda p, cf, cache_dir=None: {'fps': 30.0})
    monkeypatch.setattr(ex, '_cache_key', lambda p, cf: 'k')
    feats_for = feats_for or {}
    monkeypatch.setattr(ex, 'extract_for_clip', lambda cp, cf, fps: feats_for.get('__all__', FEATS))

    return db_path, out_path


def _entry(eid, shot_type, cc=1.0):
    return {'id': eid, 'shot_type': shot_type, 'swing_id': int(eid.split('_')[1]),
            'clip_path': f'{shot_type}/{eid}.mp4', 'clip_contact_time_sec': cc}


def test_keeps_only_label_review_verdicts(tmp_path, monkeypatch):
    _, out_path = _env(
        tmp_path, monkeypatch,
        [_entry('forehand_0001', 'forehand'), _entry('backhand_0002', 'backhand'),
         _entry('forehand_0003', 'forehand')],
        {'forehand_0001': 'shot_type_corrected', 'backhand_0002': 'contact_time_corrected',
         'forehand_0003': 'excluded'},
    )
    ex.extract()
    rows = json.loads(out_path.read_text())
    ids = {r['id'] for r in rows}
    assert ids == {'forehand_0001', 'backhand_0002'}  # 'excluded' dropped
    assert all(r['source'] == 'pro_review' for r in rows)
    assert next(r for r in rows if r['id'] == 'backhand_0002')['label'] == 'backhand'
    assert next(r for r in rows if r['id'] == 'forehand_0001')['verdict'] == 'shot_type_corrected'


def test_verdict_filter_restricts(tmp_path, monkeypatch):
    _, out_path = _env(
        tmp_path, monkeypatch,
        [_entry('forehand_0001', 'forehand'), _entry('backhand_0002', 'backhand')],
        {'forehand_0001': 'shot_type_corrected', 'backhand_0002': 'contact_time_corrected'},
    )
    ex.extract(verdict_filter=['shot_type_corrected'])
    rows = json.loads(out_path.read_text())
    assert {r['id'] for r in rows} == {'forehand_0001'}


def test_contact_frame_from_clip_contact_time(tmp_path, monkeypatch):
    seen = {}
    _, out_path = _env(tmp_path, monkeypatch, [_entry('forehand_0001', 'forehand', cc=1.4)],
                       {'forehand_0001': 'contact_time_corrected'})

    def _spy(cache_path, contact_frame, fps):
        seen['cf'] = contact_frame
        return FEATS

    monkeypatch.setattr(ex, 'extract_for_clip', _spy)
    ex.extract()
    rows = json.loads(out_path.read_text())
    assert rows[0]['contact_frame'] == round(1.4 * 30.0)  # 42
    assert seen['cf'] == 42


def test_skips_when_no_pose_near_contact(tmp_path, monkeypatch):
    _, out_path = _env(tmp_path, monkeypatch, [_entry('forehand_0001', 'forehand')],
                       {'forehand_0001': 'contact_time_corrected'})
    monkeypatch.setattr(ex, 'extract_for_clip', lambda cp, cf, fps: None)
    ex.extract()
    assert json.loads(out_path.read_text()) == []


def test_skips_entry_not_in_db(tmp_path, monkeypatch):
    _, out_path = _env(tmp_path, monkeypatch, [_entry('forehand_0001', 'forehand')],
                       {'forehand_0001': 'contact_time_corrected', 'backhand_0099': 'shot_type_corrected'})
    ex.extract()
    assert {r['id'] for r in json.loads(out_path.read_text())} == {'forehand_0001'}
