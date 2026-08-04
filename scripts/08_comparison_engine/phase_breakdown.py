"""
Split the single holistic DTW similarity score into 4 phases — backswing,
contact, follow-through (chronological, 0.5s/0s/1.0s relative to contact,
same convention as PHASE_TARGET_T in tip_selector.py), and body-rotation
(not a time slice — hip/shoulder rotation range + racket-to-body distance
across the whole swing window). Each phase is worth 25 points; their sum is
the new overall_score.

Rule-based only, same spirit as tip_selector.py: no ML, thresholds are a
first-pass calibration (like every other threshold in this rule-based
system) and expected to be tuned once real usage data exists.
"""
import math
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '09_coaching_ai'))
from trajectory_compare import dtw_distance  # noqa: E402
import tip_selector  # noqa: E402

KEY_LANDMARKS = [
    'nose',
    'left_shoulder', 'right_shoulder',
    'left_elbow',    'right_elbow',
    'left_wrist',    'right_wrist',
    'left_hip',      'right_hip',
]

PHASE_TARGET_T = {'backswing': -0.5, 'contact': 0.0, 'followthrough': 1.0}
PHASE_OUTPUT_KEY = {'backswing': 'backswing', 'contact': 'contact', 'followthrough': 'follow_through'}
PHASE_WINDOW = 0.15
# Same exp-decay shape as compare_swing.similarity_score, but that scale=0.4
# was calibrated for full-trajectory DTW distance (lots of alignment
# flexibility smooths distances down). A ~0.3s window has far less to align
# over, so raw distances run much higher -- empirically ~1.1-1.4 median
# between two different (but competent) pros on the same shot type, sampled
# from real pro_database.json pairs. 1.8 puts that median around 50-55/100
# scaled, with closer matches scoring noticeably higher -- a first-pass
# calibration, not a precise one; revisit once there's real usage data.
PHASE_SCALE = 1.8

ROTATION_SCALE_DEG = 30.0
ROTATION_SEVERITY_BANDS = [(45.0, 'severe'), (25.0, 'moderate'), (12.0, 'mild')]

RACKET_SCALE = 0.8  # shoulder-width units — first-pass estimate, not yet calibrated against real usage data
RACKET_SEVERITY_BANDS = [(1.2, 'severe'), (0.7, 'moderate'), (0.35, 'mild')]


def _severity(magnitude, bands):
    for threshold, label in bands:
        if magnitude >= threshold:
            return label
    return None


def _slice_window(trajectory, target_t, window):
    return [p for p in trajectory if abs(p['t'] - target_t) <= window]


def _nearest(trajectory, target_t):
    if not trajectory:
        return None
    return min(trajectory, key=lambda p: abs(p['t'] - target_t))


def score_phase(user_trajectory, pro_trajectory, target_t, window=PHASE_WINDOW, scale=PHASE_SCALE):
    """0-25 sub-score for one chronological phase, via DTW over the samples
    within `window` seconds of target_t (falls back to the single nearest
    snapshot on either side if the window is empty, so short trajectories
    near the clip edges still get a score rather than None)."""
    user_slice = _slice_window(user_trajectory, target_t, window)
    pro_slice = _slice_window(pro_trajectory, target_t, window)
    if not user_slice:
        n = _nearest(user_trajectory, target_t)
        user_slice = [n] if n else []
    if not pro_slice:
        n = _nearest(pro_trajectory, target_t)
        pro_slice = [n] if n else []
    if not user_slice or not pro_slice:
        return None

    dist = dtw_distance(user_slice, pro_slice, KEY_LANDMARKS)
    if dist == float('inf'):
        return None
    return round(max(0.0, min(25.0, 25 * math.exp(-dist / scale))), 1)


def _rotation_angle(lm, a_name, b_name):
    a, b = lm.get(a_name), lm.get(b_name)
    if not a or not b:
        return None
    return math.degrees(math.atan2(b['y'] - a['y'], b['x'] - a['x']))


def _shoulder_hip_separation(lm):
    """'X-factor'-style separation between shoulder-line and hip-line angle
    at one frame, in degrees. Larger swings in this value through a swing
    indicate more body rotation/coil."""
    shoulder_angle = _rotation_angle(lm, 'left_shoulder', 'right_shoulder')
    hip_angle = _rotation_angle(lm, 'left_hip', 'right_hip')
    if shoulder_angle is None or hip_angle is None:
        return None
    return shoulder_angle - hip_angle


def rotation_range(trajectory):
    """Range (max-min) of shoulder-hip separation across a trajectory —
    how much the body actually rotates through the swing. None if too few
    frames have both shoulders and hips visible."""
    vals = []
    for p in trajectory:
        v = _shoulder_hip_separation(p['landmarks'])
        if v is not None:
            vals.append(v)
    if len(vals) < 3:
        return None
    return max(vals) - min(vals)


def score_body_rotation(user_trajectory, pro_trajectory, user_racket_body_distance, pro_racket_body_distance):
    """
    0-25 score combining (a) hip/shoulder rotation-range deviation (always
    available from pose landmarks) and (b) racket-to-body distance deviation
    (only when both sides have a confident racket reading). If racket data
    is missing on either side, scores from rotation alone and says so.

    Returns {'score': float|None, 'has_racket_data': bool,
             'rotation_deviation': float|None, 'racket_deviation': float|None,
             'issues': [triggered issue dicts, most significant first]}
    """
    user_range = rotation_range(user_trajectory)
    pro_range = rotation_range(pro_trajectory)

    rotation_score = None
    rotation_deviation = None
    if user_range is not None and pro_range is not None:
        rotation_deviation = pro_range - user_range  # positive = user rotates less than the pro
        rotation_score = round(max(0.0, min(25.0, 25 * math.exp(-abs(rotation_deviation) / ROTATION_SCALE_DEG))), 1)

    has_racket_data = user_racket_body_distance is not None and pro_racket_body_distance is not None
    racket_score = None
    racket_deviation = None
    if has_racket_data:
        racket_deviation = pro_racket_body_distance - user_racket_body_distance  # positive = user's racket stays closer than the pro's
        racket_score = round(max(0.0, min(25.0, 25 * math.exp(-abs(racket_deviation) / RACKET_SCALE))), 1)

    if rotation_score is None and racket_score is None:
        combined = None
    elif racket_score is None:
        combined = rotation_score
    else:
        combined = round((rotation_score + racket_score) / 2, 1)

    issues = []
    if rotation_deviation is not None and rotation_deviation > 0:
        severity = _severity(rotation_deviation, ROTATION_SEVERITY_BANDS)
        if severity:
            issues.append({'issue_id': '_rotation_range', 'severity': severity, 'magnitude': round(rotation_deviation, 1)})
    if racket_deviation is not None and racket_deviation > 0:
        severity = _severity(racket_deviation, RACKET_SEVERITY_BANDS)
        if severity:
            issues.append({'issue_id': '_racket_distance', 'severity': severity, 'magnitude': round(racket_deviation, 3)})
    issues.sort(key=lambda i: -i['magnitude'])

    return {
        'score': combined,
        'has_racket_data': has_racket_data,
        'rotation_deviation': round(rotation_deviation, 1) if rotation_deviation is not None else None,
        'racket_deviation': round(racket_deviation, 3) if racket_deviation is not None else None,
        'issues': issues,
    }


def _body_rotation_tips(shot_type, issues, top_n=2):
    """Resolve body-rotation issue ids (suffix-matched against
    coaching_tips_database.json, e.g. 'fh' + '_rotation_range') to tip text."""
    db = tip_selector.load_tips_db()
    shot_prefix = {'forehand': 'fh', 'backhand': 'bh', 'serve': 'sv'}.get(shot_type)
    db_issues = {i['id']: i for i in db.get(shot_type, [])}

    tips = []
    for issue in issues[:top_n]:
        full_id = f"{shot_prefix}{issue['issue_id']}"
        db_issue = db_issues.get(full_id)
        if not db_issue:
            continue
        variants = db_issue['tips'][issue['severity']]
        tips.append(variants[0])
    if not tips:
        tips = ['Good body rotation and racket extension through this swing.']
    return tips


def select_phase_tips(user_trajectory, pro_trajectory, shot_type, phase, top_n=2):
    """Top tips for one chronological phase (backswing/contact/followthrough),
    via tip_selector.score_issues() filtered to that phase."""
    scored = tip_selector.score_issues(user_trajectory, pro_trajectory, shot_type)
    phase_scored = [s for s in scored if s['phase'] == phase][:top_n]
    if not phase_scored:
        return ['Good technique through this phase — closely matches the pro.']
    return [s['candidate_tips'][0] for s in phase_scored]


def compute_phase_breakdown(user_trajectory, pro_entry, shot_type, user_racket_body_distance):
    """
    Returns:
      {backswing: {score, tips}, contact: {...}, follow_through: {...},
       body_rotation: {score, tips, has_racket_data}, overall_score}
    overall_score is the sum of the 4 phase scores (0-100), or None for a
    phase that couldn't be scored (missing trajectory data on one side) —
    never fabricated.
    """
    pro_trajectory = pro_entry['trajectory']
    pro_racket_body_distance = pro_entry.get('racket_body_distance')

    phases = {}
    for phase_key, target_t in PHASE_TARGET_T.items():
        score = score_phase(user_trajectory, pro_trajectory, target_t)
        tips = select_phase_tips(user_trajectory, pro_trajectory, shot_type, phase_key)
        phases[PHASE_OUTPUT_KEY[phase_key]] = {'score': score, 'tips': tips}

    rotation_result = score_body_rotation(user_trajectory, pro_trajectory,
                                           user_racket_body_distance, pro_racket_body_distance)
    phases['body_rotation'] = {
        'score': rotation_result['score'],
        'tips': _body_rotation_tips(shot_type, rotation_result['issues']),
        'has_racket_data': rotation_result['has_racket_data'],
    }

    scores = [p['score'] for p in phases.values()]
    overall_score = round(sum(scores), 1) if all(s is not None for s in scores) else None

    return {**phases, 'overall_score': overall_score}
