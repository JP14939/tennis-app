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

# z-based rotation signal (see build_pro_database.py's normalise_landmarks()
# docstring for what z is/isn't). Real shoulder/hip coil is chiefly rotation
# around the vertical axis, toward/away from the camera -- the existing
# angle-based metric above only sees that indirectly via on-screen
# foreshortening; z sees it directly. Blended as a MINORITY contribution
# (Z_ROTATION_BLEND) alongside the existing, already-tuned angle metric,
# not a replacement -- z is noisier than x/y, and the angle metric's scale/
# severity bands above were calibrated without it.
#
# First attempt at this (Z_TO_DEG_SCALE=90, an anatomical guess) measured
# the wrong quantity to validate it -- pooled raw per-landmark z *values*
# (abs-median ~1.83, outliers to +-17) -- and wrongly concluded z was
# unusable. What this blend actually uses is the per-trajectory RANGE of
# shoulder/hip z-SEPARATION, a different and much better-behaved quantity:
# measured directly against 914 real pro-database entries (post item 31's
# angle-unwrap fix, so the angle side of the comparison is trustworthy),
# median z-range 2.02, p99 5.9, no +-17-style outliers. Pairing each
# entry's z-range against its unwrapped angle-range (filtered to the
# 697/914 entries where the angle range itself looks reliable, <150deg)
# gives a measured median ratio of ~28.6 degrees per z-unit -- Z_TO_DEG_SCALE
# below is THAT number, not a guess -- with a real, if moderate, positive
# correlation (0.35) between the two signals, i.e. z carries genuine
# rotation information, just noisier than the angle metric. Z_ROTATION_BLEND
# stays a clear minority weight given that moderate (not strong) correlation.
# Re-derive both constants the same way (see this session's z-depth-retry-2
# plan) if the underlying pose data or database composition changes
# meaningfully -- these are fit to today's real data, not universal constants.
Z_ROTATION_BLEND = 0.2
Z_TO_DEG_SCALE = 28.6

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


def _z_line_separation(lm, a_name, b_name):
    """Depth (z) difference between two landmarks -- a direct proxy for how
    rotated that body line is away from facing the camera (larger absolute
    difference = more turned), complementing _rotation_angle() above, which
    only sees rotation indirectly via on-screen foreshortening."""
    a, b = lm.get(a_name), lm.get(b_name)
    if not a or not b or a.get('z') is None or b.get('z') is None:
        return None
    return a['z'] - b['z']


def _shoulder_hip_z_separation(lm):
    """z-based analog of _shoulder_hip_separation() -- 'X-factor'-style
    separation using depth instead of on-screen angle."""
    shoulder_z = _z_line_separation(lm, 'left_shoulder', 'right_shoulder')
    hip_z = _z_line_separation(lm, 'left_hip', 'right_hip')
    if shoulder_z is None or hip_z is None:
        return None
    return shoulder_z - hip_z


def _unwrap_degrees(values):
    """Removes artificial jumps from a CHRONOLOGICAL sequence of degree
    values caused by atan2's wraparound at +-180 -- without this, a
    continuous real rotation that crosses the wrap boundary (e.g. 178 ->
    -179 between two frames, an actual ~3 degree turn) reads as a ~357
    degree jump to a naive max-min range calculation. Confirmed live: 136
    of 200 real pro-database entries had a raw rotation "range" over 180
    degrees -- physically impossible for one swing -- purely from this
    artifact, not real rotation.

    Standard unwrap technique: walk the sequence in order, and whenever
    consecutive values differ by more than 180 degrees, add/subtract 360 to
    keep the sequence continuous (same idea as numpy.unwrap, implemented
    directly since this module has no numpy dependency)."""
    if not values:
        return values
    unwrapped = [values[0]]
    offset = 0.0
    for prev, cur in zip(values, values[1:]):
        diff = cur - prev
        if diff > 180:
            offset -= 360
        elif diff < -180:
            offset += 360
        unwrapped.append(cur + offset)
    return unwrapped


def rotation_range(trajectory):
    """Range (max-min) of shoulder-hip separation across a trajectory —
    how much the body actually rotates through the swing. Blends the
    existing on-screen-angle metric with a z-depth-based one when enough
    frames have z (down-weighted per Z_ROTATION_BLEND -- see that constant's
    comment). Falls back to the angle-only metric when z isn't available
    (e.g. an older cached trajectory built before z was carried through).
    None if too few frames have both shoulders and hips visible."""
    angle_vals = []
    z_vals = []
    for p in trajectory:
        v = _shoulder_hip_separation(p['landmarks'])
        if v is not None:
            angle_vals.append(v)
        zv = _shoulder_hip_z_separation(p['landmarks'])
        if zv is not None:
            z_vals.append(zv)
    if len(angle_vals) < 3:
        return None
    unwrapped = _unwrap_degrees(angle_vals)
    angle_range = max(unwrapped) - min(unwrapped)
    if len(z_vals) < 3:
        return angle_range
    z_range_deg = (max(z_vals) - min(z_vals)) * Z_TO_DEG_SCALE
    return (1 - Z_ROTATION_BLEND) * angle_range + Z_ROTATION_BLEND * z_range_deg


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

    # score_body_rotation() above scores both directions of deviation
    # symmetrically (abs(deviation) in the exp() falloff) -- a user who
    # over-rotates or over-extends relative to the pro scores just as low as
    # one who under-rotates/under-extends by the same amount. These triggers
    # used to only fire on a positive deviation (under-rotation / racket
    # closer than the pro's), so an over-rotating swing with a low score
    # produced an empty `issues` list and _body_rotation_tips() fell through
    # to its "Good body rotation and racket extension" fallback text --
    # a low score paired with a positive-sounding tip. Using abs() here
    # matches the scoring direction so both cases surface an issue.
    issues = []
    if rotation_deviation is not None:
        severity = _severity(abs(rotation_deviation), ROTATION_SEVERITY_BANDS)
        if severity:
            issues.append({'issue_id': '_rotation_range', 'severity': severity, 'magnitude': round(abs(rotation_deviation), 1)})
    if racket_deviation is not None:
        severity = _severity(abs(racket_deviation), RACKET_SEVERITY_BANDS)
        if severity:
            issues.append({'issue_id': '_racket_distance', 'severity': severity, 'magnitude': round(abs(racket_deviation), 3)})
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

    # Literal restatement of PHASE_TARGET_T for consumers (SyncCompareScreen's
    # timeline markers) that want the same fixed relative-to-contact offsets
    # this scoring already uses, without duplicating the constants client-side.
    phase_markers = [
        {'label': 'Backswing', 't': PHASE_TARGET_T['backswing']},
        {'label': 'Contact', 't': PHASE_TARGET_T['contact']},
        {'label': 'Follow-through', 't': PHASE_TARGET_T['followthrough']},
    ]

    return {**phases, 'overall_score': overall_score, 'phase_markers': phase_markers}
