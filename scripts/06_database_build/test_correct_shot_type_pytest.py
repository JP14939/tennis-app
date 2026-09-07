"""
Regression coverage for correct_shot_type.py -- fixing a mislabeled
pro-database entry's shot type has to move the actual clip file(s), not
just relabel JSON: entry['shot_type'] is authoritative for DTW matching
(compare_swing.py filters its whole candidate pool by it), and two live
code paths (cut_pro_clip.py, clip_urls.py's attach_clip_urls()) reconstruct
the cropped-clip path by joining entry['shot_type'] with the clip's
basename rather than parsing clip_path -- so leaving the file in its old
shot-type folder would silently break the cropped-clip lookup.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import correct_shot_type as cst  # noqa: E402
import clip_review_log  # noqa: E402


def _make_db(tmp_path, entry, monkeypatch):
    pro_clips_dir = tmp_path / 'clips'
    pro_clips_cropped_dir = tmp_path / 'clips_cropped'
    db_path = tmp_path / 'pro_database.json'

    (pro_clips_dir / entry['shot_type']).mkdir(parents=True)
    (pro_clips_dir / entry['clip_path']).write_bytes(b'video bytes')

    db_path.write_text(json.dumps({'entries': [entry]}))

    monkeypatch.setattr(cst, 'PRO_DB_PATH', str(db_path))
    monkeypatch.setattr(cst, 'PRO_CLIPS_DIR', str(pro_clips_dir))
    monkeypatch.setattr(cst, 'PRO_CLIPS_CROPPED_DIR', str(pro_clips_cropped_dir))
    monkeypatch.setattr(clip_review_log, 'LOG_PATH', str(tmp_path / 'clip_review_log.jsonl'))

    return db_path, pro_clips_dir, pro_clips_cropped_dir


def _entry(shot_type='forehand', clip_name='swing_0004.mp4'):
    return {
        'id': 'forehand_0004', 'shot_type': shot_type, 'swing_id': 4,
        'clip_path': f'{shot_type}/{clip_name}',
    }


def test_moves_main_clip_and_updates_shot_type_and_clip_path(tmp_path, monkeypatch):
    db_path, pro_clips_dir, _ = _make_db(tmp_path, _entry(), monkeypatch)

    result = cst.correct_shot_type('forehand_0004', 'backhand')

    assert result == {
        'old_shot_type': 'forehand', 'new_shot_type': 'backhand',
        'clip_path': 'backhand/swing_0004.mp4',
    }
    assert not (pro_clips_dir / 'forehand' / 'swing_0004.mp4').exists()
    assert (pro_clips_dir / 'backhand' / 'swing_0004.mp4').exists()

    db = json.loads(db_path.read_text())
    entry = db['entries'][0]
    assert entry['shot_type'] == 'backhand'
    assert entry['clip_path'] == 'backhand/swing_0004.mp4'
    assert entry['id'] == 'forehand_0004'  # id is deliberately left untouched


def test_also_moves_cropped_clip_when_one_exists(tmp_path, monkeypatch):
    _, pro_clips_dir, pro_clips_cropped_dir = _make_db(tmp_path, _entry(), monkeypatch)
    (pro_clips_cropped_dir / 'forehand').mkdir(parents=True)
    (pro_clips_cropped_dir / 'forehand' / 'swing_0004.mp4').write_bytes(b'cropped bytes')

    cst.correct_shot_type('forehand_0004', 'serve')

    assert not (pro_clips_cropped_dir / 'forehand' / 'swing_0004.mp4').exists()
    assert (pro_clips_cropped_dir / 'serve' / 'swing_0004.mp4').exists()


def test_no_crash_when_no_cropped_clip_exists(tmp_path, monkeypatch):
    _make_db(tmp_path, _entry(), monkeypatch)
    result = cst.correct_shot_type('forehand_0004', 'serve')
    assert result['new_shot_type'] == 'serve'


def test_unknown_shot_type_is_rejected_without_touching_anything(tmp_path, monkeypatch):
    db_path, pro_clips_dir, _ = _make_db(tmp_path, _entry(), monkeypatch)
    original_db = db_path.read_text()

    try:
        cst.correct_shot_type('forehand_0004', 'smash')
        assert False, 'expected ValueError'
    except ValueError:
        pass

    assert db_path.read_text() == original_db
    assert (pro_clips_dir / 'forehand' / 'swing_0004.mp4').exists()


def test_correcting_to_the_same_shot_type_is_rejected(tmp_path, monkeypatch):
    _make_db(tmp_path, _entry(), monkeypatch)
    try:
        cst.correct_shot_type('forehand_0004', 'forehand')
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'already labeled' in str(e)


def test_logs_a_shot_type_corrected_verdict(tmp_path, monkeypatch):
    _make_db(tmp_path, _entry(), monkeypatch)
    cst.correct_shot_type('forehand_0004', 'backhand', name='Federer FH')

    verdicts = clip_review_log.get_latest_verdicts()
    assert verdicts == {'forehand_0004': 'shot_type_corrected'}
