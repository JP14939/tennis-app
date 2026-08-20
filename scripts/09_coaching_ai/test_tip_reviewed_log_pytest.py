"""Mirrors scripts/16_shot_verification/test_reviewed_candidates_log_pytest.py's
conventions for the same log shape, keyed by analysis_id instead of
(job_id, rally_id, swing_index)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tip_reviewed_log as trl  # noqa: E402


def test_reviewed_analysis_is_excluded_from_the_set_only_after_logging(tmp_path, monkeypatch):
    monkeypatch.setattr(trl, 'LOG_PATH', str(tmp_path / 'reviewed.jsonl'))

    assert trl.get_reviewed_set() == set()

    trl.log_reviewed(42)
    assert trl.get_reviewed_set() == {42}


def test_multiple_reviewed_analyses_accumulate(tmp_path, monkeypatch):
    monkeypatch.setattr(trl, 'LOG_PATH', str(tmp_path / 'reviewed.jsonl'))

    trl.log_reviewed(1)
    trl.log_reviewed(2)
    trl.log_reviewed(3)

    assert trl.get_reviewed_set() == {1, 2, 3}


def test_get_reviewed_set_with_no_log_file_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(trl, 'LOG_PATH', str(tmp_path / 'does_not_exist.jsonl'))
    assert trl.get_reviewed_set() == set()
