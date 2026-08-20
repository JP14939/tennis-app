"""Regression coverage for the Swing Review re-review bug: reopening the
Dev Page's Swing Review tool for a job used to re-serve every candidate
every time, including ones already given a verdict, because nothing
recorded which candidates had been reviewed. reviewed_candidates_log.py
fixes that; this covers its filtering contract directly."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reviewed_candidates_log as rcl  # noqa: E402


def test_reviewed_candidate_is_excluded_from_the_set_only_after_logging(tmp_path, monkeypatch):
    monkeypatch.setattr(rcl, 'LOG_PATH', str(tmp_path / 'reviewed.jsonl'))

    assert rcl.get_reviewed_set('job1') == set()

    rcl.log_reviewed('job1', rally_id=3, swing_index=2)
    assert rcl.get_reviewed_set('job1') == {(3, 2)}


def test_unrelated_job_id_does_not_cross_contaminate(tmp_path, monkeypatch):
    monkeypatch.setattr(rcl, 'LOG_PATH', str(tmp_path / 'reviewed.jsonl'))

    rcl.log_reviewed('job1', rally_id=1, swing_index=1)
    rcl.log_reviewed('job2', rally_id=1, swing_index=1)

    assert rcl.get_reviewed_set('job1') == {(1, 1)}
    assert rcl.get_reviewed_set('job2') == {(1, 1)}
    assert rcl.get_reviewed_set('job3') == set()


def test_job_id_types_are_normalized(tmp_path, monkeypatch):
    # job_id arrives as a string URL param in list_swing_candidates.py but
    # could be logged as a number by a caller -- both must resolve the same.
    monkeypatch.setattr(rcl, 'LOG_PATH', str(tmp_path / 'reviewed.jsonl'))

    rcl.log_reviewed(42, rally_id=1, swing_index=1)
    assert rcl.get_reviewed_set('42') == {(1, 1)}
    assert rcl.get_reviewed_set(42) == {(1, 1)}


def test_get_reviewed_set_with_no_log_file_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(rcl, 'LOG_PATH', str(tmp_path / 'does_not_exist.jsonl'))
    assert rcl.get_reviewed_set('job1') == set()
