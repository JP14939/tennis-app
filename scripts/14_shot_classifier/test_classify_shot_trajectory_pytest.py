"""Trajectory k-NN classifier: votes the majority shot type of its nearest
pro trajectories; degrades cleanly on empty / too-short input."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import classify_shot_trajectory as t  # noqa: E402


def test_empty_trajectory_returns_none():
    r = t.classify_by_trajectory([])
    assert r['shot_type'] is None


def test_too_short_trajectory_returns_none():
    stub = [{'t': 0.0, 'landmarks': {}}]
    assert t.classify_by_trajectory(stub)['shot_type'] is None


def test_practice_mvp_excluded_from_pool():
    ids = {pid for pid, _l, _tr in t._load_pool()}
    assert not any('practice' in pid for pid in ids)
    assert len(t._load_pool()) > 300  # the reviewed pro entries survive


def test_a_real_pro_trajectory_votes_its_own_class_leave_one_out():
    pool = t._load_pool()
    hits = 0
    for pid, label, traj in pool[:20]:
        if t.classify_by_trajectory(traj, exclude_id=pid, k=15)['shot_type'] == label:
            hits += 1
    assert hits >= 16   # ~85%+ on a clean in-domain sample


def test_result_has_margin_and_nearest_dist():
    pool = t._load_pool()
    r = t.classify_by_trajectory(pool[0][2], exclude_id=pool[0][0])
    assert 'margin' in r and 'nearest_dist' in r


def test_left_handed_frames_are_mirrored_before_voting(monkeypatch):
    """classify_from_frames(handedness='left') must mirror the user trajectory
    before voting against the all-right-handed pool. Assert mirror_trajectory
    is applied exactly once on the left path and not on the right path."""
    calls = {'n': 0}
    import trajectory_extraction as te
    real_mirror = te.mirror_trajectory
    monkeypatch.setattr(te, 'mirror_trajectory', lambda tr: (calls.__setitem__('n', calls['n'] + 1), real_mirror(tr))[1])
    fake_traj = [{'t': i * 0.1, 'landmarks': {}} for i in range(8)]
    monkeypatch.setattr('compare_swing.build_user_trajectory', lambda *a, **k: (fake_traj, 0))
    monkeypatch.setattr(t, 'classify_by_trajectory', lambda tr, **k: {'shot_type': 'forehand', 'scores': {}})

    t.classify_from_frames([], 30.0, 1.0, handedness='right')
    assert calls['n'] == 0
    t.classify_from_frames([], 30.0, 1.0, handedness='left')
    assert calls['n'] == 1
