"""
Student v0: rule-based coaching tip selector.

Scores every issue in coaching_tips_database.json against real deviation
data (user trajectory vs matched pro trajectory), ranks by magnitude, and
picks the top N. This is the starting policy for the teacher-student loop —
Claude (see tip_verifier.py) checks/corrects its picks while it's learning;
once accuracy is high enough a trained model can replace this rule-based
version without changing the interface.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

TIPS_DB_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'coaching_tips_database.json')

# Phase -> offset from contact (seconds), matching PRE_SEC/POST_SEC in
# build_pro_database.py and the 'backswing'/'contact'/'followthrough' split
PHASE_TARGET_T = {'backswing': -0.5, 'contact': 0.0, 'followthrough': 1.0}

SEVERITY_BANDS = [  # (min_abs_deviation, severity_label), checked high to low
    (0.40, 'severe'),
    (0.25, 'moderate'),
    (0.12, 'mild'),
]

_tips_db = None


def load_tips_db():
    global _tips_db
    if _tips_db is None:
        with open(TIPS_DB_PATH, encoding='utf-8') as f:
            _tips_db = json.load(f)
    return _tips_db


def _nearest_snapshot(trajectory, target_t):
    """Trajectory snapshot whose 't' is closest to target_t."""
    if not trajectory:
        return None
    return min(trajectory, key=lambda p: abs(p['t'] - target_t))


def _severity(magnitude):
    for threshold, label in SEVERITY_BANDS:
        if magnitude >= threshold:
            return label
    return None  # below mild threshold — not worth flagging


def score_issues(user_trajectory, pro_trajectory, shot_type):
    """
    Score every issue for this shot type against the real deviation between
    user and pro trajectories. Returns a list of dicts (one per issue that
    actually triggers — i.e. deviates in the fault's direction, above the
    mild threshold), each with the signed deviation, severity, and a chosen
    tip phrasing, sorted by magnitude descending (most significant first).
    """
    db = load_tips_db()
    issues = db.get(shot_type, [])

    scored = []
    for issue in issues:
        phase = issue['phase']
        if phase not in PHASE_TARGET_T:
            continue  # e.g. 'body_rotation' issues -- scored separately by phase_breakdown.py, not a time-snapshot comparison
        landmark = issue['landmark']
        axis = issue['axis']
        expected_direction = issue['direction']

        target_t = PHASE_TARGET_T[phase]
        user_snap = _nearest_snapshot(user_trajectory, target_t)
        pro_snap = _nearest_snapshot(pro_trajectory, target_t)
        if not user_snap or not pro_snap:
            continue

        u = user_snap['landmarks'].get(landmark)
        p = pro_snap['landmarks'].get(landmark)
        if u is None or p is None:
            continue

        diff = u[axis] - p[axis]
        actual_direction = 'high' if diff > 0 else 'low'
        if actual_direction != expected_direction:
            continue  # deviates the "good" way, not a fault

        magnitude = abs(diff)
        severity = _severity(magnitude)
        if severity is None:
            continue  # too small to be worth flagging

        scored.append({
            'issue_id': issue['id'],
            'landmark': landmark, 'phase': phase, 'axis': axis,
            'description': issue['description'],
            'deviation': round(diff, 4),
            'magnitude': round(magnitude, 4),
            'severity': severity,
            'candidate_tips': issue['tips'][severity],
            'drill': issue.get('drill'),
        })

    scored.sort(key=lambda s: -s['magnitude'])
    return scored


def select_top_tips(user_trajectory, pro_trajectory, shot_type, top_n=3, phrasing_index=0):
    """
    The student's actual pick: top_n triggered issues by magnitude, each
    resolved to one concrete tip string (phrasing_index picks which variant;
    default is deterministic so repeated calls on the same data agree, which
    matters for logging/verification).
    """
    scored = score_issues(user_trajectory, pro_trajectory, shot_type)
    top = scored[:top_n]

    for item in top:
        variants = item['candidate_tips']
        item['tip_text'] = variants[phrasing_index % len(variants)]

    if not top:
        return [{
            'issue_id': None, 'severity': None,
            'tip_text': 'Great technique! Your form closely matches the pro.',
        }]
    return top


if __name__ == '__main__':
    # Quick smoke test with a fabricated deviation to sanity-check the logic
    user_traj = [{'t': 0.0, 'landmarks': {'right_elbow': {'x': 0.5, 'y': 0.1}}}]
    pro_traj = [{'t': 0.0, 'landmarks': {'right_elbow': {'x': 0.1, 'y': 0.1}}}]
    result = select_top_tips(user_traj, pro_traj, 'forehand')
    for r in result:
        print(r.get('severity'), '-', r.get('tip_text'))
