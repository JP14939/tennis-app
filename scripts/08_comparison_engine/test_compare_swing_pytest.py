"""Regression test: find_peak_wrist_frame() used to trust a wrist's x/y
regardless of MediaPipe's visibility score for that landmark. MediaPipe
always returns an x/y for every landmark even at near-zero confidence
(motion blur is common right at contact, on fast swings), so a spuriously
large frame-to-frame jump from a low-confidence wrist detection could be
mistaken for the real contact-frame velocity peak -- silently shifting the
whole comparison window and corrupting the DTW score with no error
surfacing anywhere. Same 0.5 visibility threshold as detect_swings.py's
compute_wrist_velocity(), the pro-database side's equivalent function.

Not runnable in every environment: compare_swing.py imports cv2/mediapipe
at module level, so this needs the real scripts/venv (see CLAUDE.md) --
same situation test_build_pro_database_pytest.py is already in.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_swing as cs  # noqa: E402 -- module ref, so monkeypatching cs.X affects cs's own callers
from compare_swing import (  # noqa: E402
    find_peak_wrist_frame, eligible_match_candidates, build_user_trajectory,
    groundstroke_contact_anchor_frame,
)
import contact_evidence  # noqa: E402 -- for monkeypatching wrist_kinematics below


def _landmark(x, y, visibility):
    return {'x': x, 'y': y, 'z': 0.0, 'visibility': visibility}


def _frame(idx, right_wrist_xy, visibility):
    x, y = right_wrist_xy
    return {
        'frame': idx,
        'timestamp': idx / 30.0,
        'landmarks': {
            'right_wrist': _landmark(x, y, visibility),
            'left_wrist': _landmark(0.5, 0.5, 1.0),  # stationary, irrelevant
        },
    }


def test_low_visibility_wrist_jump_is_not_mistaken_for_contact():
    frames = [
        _frame(0, (0.50, 0.50), 1.0),
        _frame(1, (0.50, 0.50), 1.0),
        # Motion-blurred frame: a huge apparent jump, but low confidence --
        # must not be picked as the velocity peak.
        _frame(2, (0.90, 0.90), 0.1),
        _frame(3, (0.90, 0.90), 1.0),
        # A smaller, but high-confidence, real velocity peak.
        _frame(4, (0.95, 0.90), 1.0),
        _frame(5, (0.95, 0.90), 1.0),
    ]
    peak_idx = find_peak_wrist_frame(frames, fps=30)
    assert peak_idx == 4


def test_missing_landmarks_frame_is_skipped_not_crashed():
    frames = [
        _frame(0, (0.50, 0.50), 1.0),
        {'frame': 1, 'timestamp': 1 / 30.0, 'landmarks': None},
        _frame(2, (0.60, 0.50), 1.0),
    ]
    # Should not raise, and should still find the real movement at frame 2.
    assert find_peak_wrist_frame(frames, fps=30) == 2


# ── groundstroke_contact_anchor_frame: peak-speed anchor recentred toward the
# peak-deceleration frame (Phase 2a, 2026-09-11) ─────────────────────────────
#
# find_peak_wrist_frame and wrist_kinematics are both monkeypatched to fixed
# values in these tests -- their own arithmetic is covered by
# test_low_visibility_wrist_jump_is_not_mistaken_for_contact (above) and
# contact_evidence.py's own test suite respectively. These tests are purely
# about groundstroke_contact_anchor_frame's OWN guard logic: does it shift by
# the reported offset, and does it correctly refuse to when the guards fail.

def _anchor_frames(peak_idx, peak_visibility=1.0):
    frames = [_frame(i, (0.5, 0.5), 1.0) for i in range(peak_idx + 1)]
    # _frame() always gives left_wrist visibility 1.0 -- lower both wrists at
    # the peak frame so the "not visible" test actually exercises the guard
    # (groundstroke_contact_anchor_frame accepts EITHER wrist being visible).
    frames[peak_idx]['landmarks']['right_wrist']['visibility'] = peak_visibility
    frames[peak_idx]['landmarks']['left_wrist']['visibility'] = peak_visibility
    return frames


def test_shifts_anchor_by_measured_decel_offset_within_guard(monkeypatch):
    monkeypatch.setattr(cs, 'find_peak_wrist_frame', lambda frames, fps: 4)
    monkeypatch.setattr(contact_evidence, 'wrist_kinematics',
                        lambda frames, idx, fps: {'wrist_decel_offset_f': 3,
                                                  'wrist_halfspeed_offset_f': None})
    frames = _anchor_frames(4)
    assert groundstroke_contact_anchor_frame(frames, fps=30) == frames[4]['frame'] + 3


def test_falls_back_to_halfspeed_offset_when_decel_missing(monkeypatch):
    monkeypatch.setattr(cs, 'find_peak_wrist_frame', lambda frames, fps: 4)
    monkeypatch.setattr(contact_evidence, 'wrist_kinematics',
                        lambda frames, idx, fps: {'wrist_decel_offset_f': None,
                                                  'wrist_halfspeed_offset_f': 2})
    frames = _anchor_frames(4)
    assert groundstroke_contact_anchor_frame(frames, fps=30) == frames[4]['frame'] + 2


def test_anchor_unshifted_when_offset_exceeds_guard(monkeypatch):
    # A big offset means the decel signal found something else entirely (e.g.
    # a second braking event well into the follow-through) -- not trustworthy,
    # so the raw peak wins rather than moving somewhere wild.
    monkeypatch.setattr(cs, 'find_peak_wrist_frame', lambda frames, fps: 4)
    monkeypatch.setattr(contact_evidence, 'wrist_kinematics',
                        lambda frames, idx, fps: {'wrist_decel_offset_f': 20,
                                                  'wrist_halfspeed_offset_f': None})
    frames = _anchor_frames(4)
    assert groundstroke_contact_anchor_frame(frames, fps=30) == frames[4]['frame']


def test_anchor_unshifted_when_wrist_not_visible_at_peak(monkeypatch):
    # Motion blur right at the speed peak makes even the decel measurement
    # unreliable -- never trust it, regardless of what wrist_kinematics says.
    called = []
    monkeypatch.setattr(cs, 'find_peak_wrist_frame', lambda frames, fps: 4)
    monkeypatch.setattr(contact_evidence, 'wrist_kinematics',
                        lambda frames, idx, fps: called.append(1) or
                        {'wrist_decel_offset_f': 1})
    frames = _anchor_frames(4, peak_visibility=0.2)
    assert groundstroke_contact_anchor_frame(frames, fps=30) == frames[4]['frame']
    assert not called  # short-circuited before ever consulting wrist_kinematics


def test_low_visibility_PREVIOUS_frame_is_not_mistaken_for_contact():
    # The gate used to only check the CURRENT frame's visibility, so a
    # garbage low-confidence PREVIOUS position paired with a confident
    # current one still produced a spurious large jump that got accepted.
    frames = [
        _frame(0, (0.50, 0.50), 1.0),
        # Motion-blurred frame landing at a garbage position -- its own
        # visibility is low, so no jump *into* this frame should ever be
        # trusted, including the jump *out of* it on the next frame.
        _frame(1, (0.10, 0.10), 0.1),
        # High-confidence frame, but the apparent jump from frame 1's
        # garbage position is spurious and must not be picked as the peak.
        _frame(2, (0.55, 0.50), 1.0),
        _frame(3, (0.56, 0.50), 1.0),
        # The real (smaller, but genuine) velocity peak.
        _frame(4, (0.62, 0.50), 1.0),
    ]
    peak_idx = find_peak_wrist_frame(frames, fps=30)
    assert peak_idx == 4


# ── eligible_match_candidates ───────────────────────────────────────────────
# Regression: the court-level practice-footage ingest (entry['ingest'] ==
# 'practice_mvp') was a live match candidate the moment it landed in
# pro_database.json, unreviewed shot type / contact frame and all -- a bad
# auto-label could be served to a real user as their "closest pro match".

def _entry(id_, shot_type, ingest=None):
    e = {'id': id_, 'shot_type': shot_type}
    if ingest:
        e['ingest'] = ingest
    return e


def test_unreviewed_practice_entry_is_excluded():
    entries = [_entry('practice_1', 'forehand', ingest='practice_mvp')]
    assert eligible_match_candidates(entries, 'forehand', reviewed_practice_ids=set()) == []


def test_reviewed_practice_entry_is_included():
    entries = [_entry('practice_1', 'forehand', ingest='practice_mvp')]
    result = eligible_match_candidates(entries, 'forehand', reviewed_practice_ids={'practice_1'})
    assert result == entries


def test_non_practice_entry_is_unaffected_by_review_status():
    entries = [_entry('forehand_0004', 'forehand')]
    assert eligible_match_candidates(entries, 'forehand', reviewed_practice_ids=set()) == entries


def test_filters_to_requested_shot_type():
    entries = [_entry('forehand_0001', 'forehand'), _entry('backhand_0001', 'backhand')]
    result = eligible_match_candidates(entries, 'forehand', reviewed_practice_ids=set())
    assert [e['id'] for e in result] == ['forehand_0001']


# ── yaw normalization: back-compat (Phase 1, flag OFF) ──────────────────────

def _swing_frames(n=40, fps=30):
    """A crude synthetic swing: shoulders/hips/wrist drifting frame to frame,
    every 3rd frame kept (matching extract_user_poses). No world_landmarks."""
    frames = []
    for i in range(0, n * 3, 3):
        p = i / (n * 3)
        lm = {
            'left_shoulder':  _landmark(0.45, 0.40, 1.0),
            'right_shoulder': _landmark(0.55, 0.40, 1.0),
            'left_hip':       _landmark(0.46, 0.55, 1.0),
            'right_hip':      _landmark(0.54, 0.55, 1.0),
            'right_wrist':    _landmark(0.50 + 0.25 * p, 0.45 - 0.1 * p, 1.0),
            'left_wrist':     _landmark(0.48, 0.52, 1.0),
            'nose':           _landmark(0.50, 0.30, 1.0),
            'left_elbow':     _landmark(0.47, 0.48, 1.0),
            'right_elbow':    _landmark(0.53, 0.48, 1.0),
        }
        frames.append({'frame': i, 'timestamp': i / fps, 'landmarks': lm})
    return frames


def test_yaw_off_is_unchanged_and_meta_none():
    frames = _swing_frames()
    traj_a, cf_a = build_user_trajectory(frames, 30, contact_time_sec=0.6, shot_type='forehand')
    traj_b, cf_b, meta = build_user_trajectory(
        frames, 30, contact_time_sec=0.6, shot_type='forehand',
        yaw_enabled=False, return_meta=True)
    assert traj_a == traj_b and cf_a == cf_b
    assert meta['yaw_deg'] is None


def test_yaw_on_without_world_landmarks_is_identity():
    frames = _swing_frames()  # no 'world_landmarks' key at all
    off, _ = build_user_trajectory(frames, 30, contact_time_sec=0.6, shot_type='forehand', yaw_enabled=False)
    on, _, meta = build_user_trajectory(
        frames, 30, contact_time_sec=0.6, shot_type='forehand',
        yaw_enabled=True, return_meta=True)
    assert on == off
    assert meta['yaw_deg'] is None
