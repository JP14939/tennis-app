"""Tests for eval_stamp.py (shared eval-result provenance stamping)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_stamp import git_sha, file_fingerprint, provenance, check_single_version  # noqa: E402


def test_git_sha_returns_nonempty_string():
    sha = git_sha()
    assert isinstance(sha, str) and len(sha) > 0
    assert git_sha() == sha  # cached, stable across calls


def test_file_fingerprint_missing_file_returns_none():
    assert file_fingerprint('/no/such/path/at/all.pt') is None


def test_file_fingerprint_existing_file(tmp_path):
    f = tmp_path / 'weights' / 'best.pt'
    f.parent.mkdir()
    f.write_text('fake weights')
    fp = file_fingerprint(str(f))
    assert fp is not None
    assert fp.startswith('weights:')


def test_file_fingerprint_changes_when_file_changes(tmp_path):
    f = tmp_path / 'best.pt'
    f.write_text('v1')
    fp1 = file_fingerprint(str(f))
    f.write_text('v2 but much longer content so size differs')
    fp2 = file_fingerprint(str(f))
    assert fp1 != fp2


def test_provenance_includes_git_sha_and_model_stamps(tmp_path):
    f = tmp_path / 'ball' / 'best.pt'
    f.parent.mkdir()
    f.write_text('weights')
    prov = provenance(ball=str(f), onset=None)
    assert 'git_sha' in prov
    assert prov['ball_model'] is not None
    assert prov['onset_model'] is None


def test_check_single_version_ok_when_uniform():
    records = [{'git_sha': 'abc123'}, {'git_sha': 'abc123'}]
    ok, versions = check_single_version(records, 'git_sha')
    assert ok is True
    assert versions['git_sha'] == {'abc123'}


def test_check_single_version_flags_mixed_versions():
    records = [{'git_sha': 'abc123'}, {'git_sha': 'def456'}]
    ok, versions = check_single_version(records, 'git_sha')
    assert ok is False
    assert versions['git_sha'] == {'abc123', 'def456'}


def test_check_single_version_treats_missing_key_as_unstamped():
    records = [{'git_sha': 'abc123'}, {}]
    ok, versions = check_single_version(records, 'git_sha')
    assert ok is False
    assert 'unstamped' in versions['git_sha']
