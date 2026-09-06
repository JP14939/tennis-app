"""Coverage for build_contact_student_dataset.py's practice-footage sweep
(--practice): _practice_teacher_times() and _already_done_practice() are pure
identity/verdict logic, no MediaPipe -- the actual pose-extraction student
evidence path (_student_evidence) is exercised live by run_practice() and is
out of scope for a fast unit test (same reasoning test_compare_swing_pytest.py
gives for needing the real venv, just not re-run here).

Not runnable in every environment: this module imports cv2/mediapipe
transitively (via compare_swing/audio_contact) at import time, same as
test_compare_swing_pytest.py -- needs the real scripts/venv.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '00_utils'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '06_database_build'))

import build_contact_student_dataset as bcsd  # noqa: E402
import clip_review_log  # noqa: E402


def _entry(eid, contact_sec):
    return {'id': eid, 'ingest': 'practice_mvp', 'clip_contact_time_sec': contact_sec,
            'clip_path': f'practice/{eid}.mp4'}


def _write_db(tmp_path, entries, monkeypatch):
    db_path = tmp_path / 'pro_database.json'
    db_path.write_text(json.dumps({'entries': entries}))
    monkeypatch.setattr(bcsd, 'PRO_DB_PATH', str(db_path))


def _write_log(tmp_path, records, monkeypatch):
    log_path = tmp_path / 'clip_review_log.jsonl'
    with open(log_path, 'w') as f:
        for r in records:
            f.write(json.dumps({'note': None, 'name': None, 'timestamp': 0, **r}) + '\n')
    monkeypatch.setattr(clip_review_log, 'LOG_PATH', str(log_path))


def test_contact_time_corrected_uses_note_value(tmp_path, monkeypatch):
    _write_db(tmp_path, [_entry('practice_1', 0.95)], monkeypatch)
    _write_log(tmp_path, [
        {'entry_id': 'practice_1', 'verdict': 'contact_time_corrected', 'note': '0.95 -> 1.73'},
    ], monkeypatch)
    times = bcsd._practice_teacher_times()
    assert times == {'practice_1': 1.73}


def test_label_confirmed_uses_entrys_current_contact_time(tmp_path, monkeypatch):
    """'label_confirmed' means Jack looked and the shown contact time was
    already right -- there's no 'a -> b' note, the entry's own
    clip_contact_time_sec IS the human-verified value."""
    _write_db(tmp_path, [_entry('practice_1', 1.10)], monkeypatch)
    _write_log(tmp_path, [{'entry_id': 'practice_1', 'verdict': 'label_confirmed'}], monkeypatch)
    times = bcsd._practice_teacher_times()
    assert times == {'practice_1': 1.10}


def test_non_practice_id_is_ignored(tmp_path, monkeypatch):
    _write_db(tmp_path, [_entry('practice_1', 1.0)], monkeypatch)
    _write_log(tmp_path, [
        {'entry_id': 'forehand_0004', 'verdict': 'contact_time_corrected', 'note': '1.0 -> 1.2'},
    ], monkeypatch)
    assert bcsd._practice_teacher_times() == {}


def test_boundary_only_verdict_is_not_a_label_review(tmp_path, monkeypatch):
    """'ok'/'mismatched'/etc. never checked label accuracy -- must not be
    treated as a teacher label (mirrors LABEL_REVIEW_VERDICTS elsewhere)."""
    _write_db(tmp_path, [_entry('practice_1', 1.0)], monkeypatch)
    _write_log(tmp_path, [{'entry_id': 'practice_1', 'verdict': 'ok'}], monkeypatch)
    assert bcsd._practice_teacher_times() == {}


def test_entry_removed_from_db_is_excluded_even_with_a_verdict(tmp_path, monkeypatch):
    _write_db(tmp_path, [], monkeypatch)  # entry no longer in the db (e.g. split/removed)
    _write_log(tmp_path, [{'entry_id': 'practice_1', 'verdict': 'label_confirmed'}], monkeypatch)
    assert bcsd._practice_teacher_times() == {}


def test_already_done_practice_scoped_to_practice_ids_and_human_source(tmp_path, monkeypatch):
    log_path = tmp_path / 'contact_frame_training_log.jsonl'
    rows = [
        {'source': 'human', 'student_meta': {'swing_key': 'practice_1'}},
        {'source': 'audio_teacher', 'student_meta': {'swing_key': 'practice_2'}},  # wrong source
        {'source': 'human', 'student_meta': {'swing_key': 'forehand_4'}},  # not a practice id
        {'source': 'human', 'student_meta': {'swing_key': 'practice_3'}},
    ]
    with open(log_path, 'w') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    monkeypatch.setattr(bcsd.cflog, 'LOG_PATH', str(log_path))
    assert bcsd._already_done_practice() == {'practice_1', 'practice_3'}
