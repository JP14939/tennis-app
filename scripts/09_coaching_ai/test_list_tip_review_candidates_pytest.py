"""Coverage for _user_clip_path() -- the one pure, easily-testable unit in
list_tip_review_candidates.py (the rest is DB/pose-extraction I/O, verified
via a real smoke test against actual saved analyses instead)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from list_tip_review_candidates import _user_clip_path, USER_CLIPS_DIR  # noqa: E402


def test_resolves_a_real_user_clip_url_to_a_filesystem_path():
    result = _user_clip_path('/user-clips/upload_123_456/original.mp4')
    expected = os.path.join(USER_CLIPS_DIR, 'upload_123_456', 'original.mp4')
    assert result == expected


def test_none_url_returns_none():
    assert _user_clip_path(None) is None


def test_unrelated_url_returns_none():
    assert _user_clip_path('/pro-clips/forehand/some_clip.mp4') is None


def test_empty_string_returns_none():
    assert _user_clip_path('') is None
