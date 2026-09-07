"""Regression test for the user-correction training flywheel: History's
"Wrong shot type?" correction only ever logs clip_path + contact_time_sec
(no contact_frame -- see backend/src/routes/history.js's
logShotTypeCorrection), unlike the Claude-verifier rows this file was
originally written for. _latest_by_identity() must dedupe both shapes
correctly without confusing a time-keyed row for a frame-keyed one that
happens to share a numeric value, and without ever silently dropping a
contact_time_sec-only row the way the old (clip_path, contact_frame)-only
dedupe used to (frame was always None for these rows -> filtered out before
dedup even ran).

Pure-logic test, no MediaPipe / pose extraction involved.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_training_features_from_log import _latest_by_identity  # noqa: E402


def _row(clip_path, claude_pick='forehand', **kw):
    return {'clip_path': clip_path, 'claude_pick': claude_pick, **kw}


def test_contact_time_sec_only_row_is_kept():
    """The bug this fixes: a user-correction row has no contact_frame at
    all -- it must not be dropped just because that field is missing."""
    rows = [_row('clip.mp4', contact_time_sec=1.234)]
    kept = _latest_by_identity(rows)
    assert len(kept) == 1
    (clip_path, identity), r = next(iter(kept.items()))
    assert clip_path == os.path.normpath('clip.mp4')
    assert identity == ('time', 1.234)
    assert r['contact_time_sec'] == 1.234


def test_contact_frame_row_still_takes_priority_identity():
    rows = [_row('clip.mp4', contact_frame=42)]
    kept = _latest_by_identity(rows)
    (clip_path, identity), r = next(iter(kept.items()))
    assert identity == 42


def test_repeated_time_correction_dedupes_to_latest():
    rows = [
        _row('clip.mp4', claude_pick='forehand', contact_time_sec=1.0),
        _row('clip.mp4', claude_pick='backhand', contact_time_sec=1.0),  # re-corrected
    ]
    kept = _latest_by_identity(rows)
    assert len(kept) == 1
    r = next(iter(kept.values()))
    assert r['claude_pick'] == 'backhand'


def test_time_and_frame_rows_on_same_clip_do_not_collide():
    """A Claude-verifier row and a later user correction on the same clip
    file must both survive -- different identity keys even if the numbers
    happen to coincide (frame 1 vs time 1.0s are unrelated units)."""
    rows = [
        _row('clip.mp4', contact_frame=1),
        _row('clip.mp4', contact_time_sec=1.0),
    ]
    kept = _latest_by_identity(rows)
    assert len(kept) == 2


def test_row_missing_both_frame_and_time_is_dropped():
    rows = [_row('clip.mp4')]
    assert _latest_by_identity(rows) == {}


def test_row_with_invalid_label_is_dropped():
    rows = [_row('clip.mp4', claude_pick='not_a_shot_type', contact_time_sec=1.0)]
    assert _latest_by_identity(rows) == {}


def test_row_missing_clip_path_is_dropped():
    rows = [{'claude_pick': 'forehand', 'contact_time_sec': 1.0}]
    assert _latest_by_identity(rows) == {}


def test_clip_path_separators_normalise_to_same_identity():
    rows = [
        _row('C:\\clips\\a.mp4', contact_frame=5),
        _row('C:/clips/a.mp4', contact_frame=5),
    ]
    kept = _latest_by_identity(rows)
    assert len(kept) == 1
