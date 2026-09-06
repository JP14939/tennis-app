"""
Trajectory-shape shot classifier -- a distance-weighted k-NN vote over the
labelled pro swing trajectories, using the same DTW the pro-match ranking uses.

Full 1.5s swing shape, not a single contact frame. Used as a TIEBREAKER when
classify_shot_geom's confidence is low -- NOT as a primary classifier: the pro
pool is ~all right-handed, so it silently mislabels a left-hander's forehand as
a backhand.
"""
import argparse
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '08_comparison_engine'))

from paths import DATA_DIR  # noqa: E402
from trajectory_compare import dtw_distance  # noqa: E402
from compare_swing import KEY_LANDMARKS  # noqa: E402
from build_pro_database import MIN_TRAJECTORY_POINTS  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
CLASSES = ('forehand', 'backhand', 'serve')
DEFAULT_K = 15
_pool = None


def _load_pool():
    """Vote only with trajectories whose shot-type label is trustworthy.
    Excludes `ingest == 'practice_mvp'` entries: the court-level practice
    footage ingest (2026-09) tags nearly every swing 'forehand' (audio
    contact detection fails on broadcast audio -> frame ~13f late -> Claude
    sees a follow-through and defaults to forehand). Left in the pool they
    pull every k-NN vote toward forehand (measured: backhand recall 84% ->
    74%). Re-include once those entries are shot-type-reviewed."""
    global _pool
    if _pool is None:
        with open(PRO_DB_PATH, encoding='utf-8') as f:
            db = json.load(f)
        _pool = [(e['id'], e['shot_type'], e['trajectory'])
                 for e in db['entries']
                 if e.get('shot_type') in CLASSES
                 and e.get('ingest') != 'practice_mvp'
                 and len(e.get('trajectory') or []) >= MIN_TRAJECTORY_POINTS]
    return _pool


def classify_by_trajectory(user_trajectory, *, k=DEFAULT_K, exclude_id=None):
    """user_trajectory: list of {t, landmarks} (compare_swing.build_user_trajectory
    output / a pro entry's `trajectory`). Returns
    {shot_type, scores:{...}, neighbours:[(id,label,dist),...]} or shot_type=None
    when there's nothing usable to compare against."""
    if not user_trajectory or len(user_trajectory) < MIN_TRAJECTORY_POINTS:
        return {'shot_type': None, 'scores': {c: 1 / 3 for c in CLASSES}, 'neighbours': []}
    dists = []
    for pid, label, traj in _load_pool():
        if pid == exclude_id:
            continue
        d = dtw_distance(user_trajectory, traj, KEY_LANDMARKS)
        if d != float('inf'):
            dists.append((d, pid, label))
    if not dists:
        return {'shot_type': None, 'scores': {c: 1 / 3 for c in CLASSES}, 'neighbours': []}
    dists.sort()
    near = dists[:k]
    weights = {c: 0.0 for c in CLASSES}
    for d, _pid, label in near:
        weights[label] += 1.0 / (d + 1e-6)
    total = sum(weights.values()) or 1.0
    scores = {c: round(weights[c] / total, 3) for c in CLASSES}
    ranked = sorted(scores.values(), reverse=True)
    return {
        'shot_type': max(scores, key=scores.get),
        'scores': scores,
        'margin': round(ranked[0] - ranked[1], 3),   # vote decisiveness
        'nearest_dist': round(near[0][0], 4),
        'neighbours': [(pid, label, round(d, 4)) for d, pid, label in near],
    }


def classify_from_frames(frames, fps, contact_time_sec, *, k=DEFAULT_K, handedness='right'):
    """frames/fps as compare_swing.extract_user_poses returns them.

    The pool is all right-handed, so a left-hander's swing must be mirrored
    before voting (same reflection compare_swing.compare() applies) -- without
    it a lefty forehand votes backhand every time.
    """
    from compare_swing import build_user_trajectory
    traj, _contact_frame = build_user_trajectory(frames, fps, contact_time_sec)
    if handedness == 'left' and traj:
        from trajectory_extraction import mirror_trajectory  # noqa: PLC0415
        traj = mirror_trajectory(traj)
    return classify_by_trajectory(traj, k=k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video')
    ap.add_argument('contact_time', type=float)
    ap.add_argument('-k', type=int, default=DEFAULT_K)
    args = ap.parse_args()
    from compare_swing import extract_user_poses
    frames, fps = extract_user_poses(args.video)
    print(json.dumps(classify_from_frames(frames, fps, args.contact_time, k=args.k), indent=2))


if __name__ == '__main__':
    main()
