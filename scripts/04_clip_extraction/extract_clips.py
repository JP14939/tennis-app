import json
import os
import cv2
import math

# Confidence threshold — swings below this are skipped
MIN_CONFIDENCE = 0.5

JOBS = [
    {
        'shot_type': 'forehand',
        'video':  r'C:\Users\jackp\tennis_app\data\01_source_videos\forehand\forehand_compilation_1.mp4',
        'poses':  r'C:\Users\jackp\tennis_app\data\02_pose_extraction\forehand_poses.json',
        'swings': r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings.json',
        'out_dir': r'C:\Users\jackp\tennis_app\data\04_clips\forehand',
    },
    {
        'shot_type': 'backhand',
        'video':  r'C:\Users\jackp\tennis_app\data\01_source_videos\backhand\backhand_compilation_1.mp4',
        'poses':  r'C:\Users\jackp\tennis_app\data\02_pose_extraction\backhand_poses.json',
        'swings': r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings.json',
        'out_dir': r'C:\Users\jackp\tennis_app\data\04_clips\backhand',
    },
    {
        'shot_type': 'serve',
        'video':  r'C:\Users\jackp\tennis_app\data\01_source_videos\serve\serve_compilation_1.mp4',
        'poses':  r'C:\Users\jackp\tennis_app\data\02_pose_extraction\serve_poses.json',
        'swings': r'C:\Users\jackp\tennis_app\data\03_swing_detection\serve_swings.json',
        'out_dir': r'C:\Users\jackp\tennis_app\data\04_clips\serve',
    },
]


# ── Pose helpers ──────────────────────────────────────────────────────────────

def get_lm(landmarks, name):
    for lm in landmarks:
        if lm['name'] == name:
            return lm
    return None


def visible(lm, threshold=0.4):
    return lm is not None and lm['visibility'] >= threshold


def dist2d(a, b):
    return math.sqrt((a['x'] - b['x']) ** 2 + (a['y'] - b['y']) ** 2)


# ── Confidence scorers ────────────────────────────────────────────────────────

def score_forehand(peak_lm, prev_lm):
    """
    Forehand signals:
    - Dominant wrist (faster one) crosses body midline toward opposite side
    - Wrist is at roughly mid-body height (not overhead like serve)
    - Dominant wrist velocity > non-dominant
    """
    score = 0.0
    reasons = []

    rw = get_lm(peak_lm, 'right_wrist')
    lw = get_lm(peak_lm, 'left_wrist')
    rs = get_lm(peak_lm, 'right_shoulder')
    ls = get_lm(peak_lm, 'left_shoulder')
    rh = get_lm(peak_lm, 'right_hip')
    lh = get_lm(peak_lm, 'left_hip')

    if not all(visible(x) for x in [rw, lw, rs, ls]):
        return 0.3, ['insufficient landmarks']

    # Body midline x
    mid_x = (rs['x'] + ls['x']) / 2
    mid_y = (rh['y'] + lh['y']) / 2 if visible(rh) and visible(lh) else (rs['y'] + ls['y']) / 2 + 0.3

    # Wrist height — should NOT be overhead (serve territory)
    if rw['y'] > (rs['y'] - 0.05):  # wrist below or near shoulder level
        score += 0.25
        reasons.append('wrist not overhead')

    # Dominant wrist crosses midline — for forehand the right wrist moves left of center
    rw_prev = get_lm(prev_lm, 'right_wrist') if prev_lm else None
    lw_prev = get_lm(prev_lm, 'left_wrist') if prev_lm else None

    rw_vel = dist2d(rw, rw_prev) if rw_prev else 0
    lw_vel = dist2d(lw, lw_prev) if lw_prev else 0

    if rw_vel > lw_vel:
        score += 0.25
        reasons.append('right wrist dominant')
        # Right wrist crossing toward left side = forehand follow-through
        if rw['x'] < mid_x + 0.1:
            score += 0.3
            reasons.append('right wrist crossed midline')
    else:
        score += 0.1
        reasons.append('left wrist dominant (may be left-handed forehand)')
        if lw['x'] > mid_x - 0.1:
            score += 0.2
            reasons.append('left wrist crossed midline')

    # Body height check — player should be standing (hip visible, y > 0.4)
    if visible(rh) and rh['y'] > 0.4:
        score += 0.2
        reasons.append('standing posture')

    return min(score, 1.0), reasons


def score_backhand(peak_lm, prev_lm):
    """
    Backhand signals:
    - Both wrists close together (two-handed) OR non-dominant wrist leads
    - Wrist moves to opposite side from forehand
    - Not overhead
    """
    score = 0.0
    reasons = []

    rw = get_lm(peak_lm, 'right_wrist')
    lw = get_lm(peak_lm, 'left_wrist')
    rs = get_lm(peak_lm, 'right_shoulder')
    ls = get_lm(peak_lm, 'left_shoulder')
    rh = get_lm(peak_lm, 'right_hip')

    if not all(visible(x) for x in [rw, lw, rs, ls]):
        return 0.3, ['insufficient landmarks']

    mid_x = (rs['x'] + ls['x']) / 2

    # Wrist not overhead
    if rw['y'] > (rs['y'] - 0.05):
        score += 0.2
        reasons.append('wrist not overhead')

    # Two-handed backhand: wrists close together
    wrist_sep = abs(rw['x'] - lw['x'])
    if wrist_sep < 0.15:
        score += 0.35
        reasons.append(f'wrists close together (sep={wrist_sep:.3f}) = two-handed')

    # Wrist velocity — left wrist more active (right-handed player's backhand)
    rw_prev = get_lm(prev_lm, 'right_wrist') if prev_lm else None
    lw_prev = get_lm(prev_lm, 'left_wrist') if prev_lm else None
    rw_vel = dist2d(rw, rw_prev) if rw_prev else 0
    lw_vel = dist2d(lw, lw_prev) if lw_prev else 0

    if lw_vel >= rw_vel * 0.7:  # left wrist meaningfully active
        score += 0.25
        reasons.append('left wrist active')

    # Wrists on right side of midline (backhand follow-through goes right)
    avg_wrist_x = (rw['x'] + lw['x']) / 2
    if avg_wrist_x > mid_x:
        score += 0.2
        reasons.append('wrists right of midline')

    if visible(rh) and rh['y'] > 0.4:
        score += 0.1
        reasons.append('standing posture')

    return min(score, 1.0), reasons


def score_serve(peak_lm, prev_lm, window_lms=None):
    """
    Serve signals:
    - At some point in the swing window, wrist reaches above shoulder (trophy/contact)
    - Peak velocity happens on the downswing, so we check the WINDOW not just peak frame
    - Elbow elevated, wrist above head at some point
    """
    score = 0.0
    reasons = []

    # Check peak frame first
    frames_to_check = [peak_lm]
    if window_lms:
        frames_to_check = window_lms + [peak_lm]

    best_overhead = -999
    best_rs_y = None
    elbow_elevated = False
    wrist_above_nose = False

    for lm in frames_to_check:
        rw = get_lm(lm, 'right_wrist')
        lw = get_lm(lm, 'left_wrist')
        rs = get_lm(lm, 'right_shoulder')
        ls = get_lm(lm, 'left_shoulder')
        re = get_lm(lm, 'right_elbow')
        nose = get_lm(lm, 'nose')

        if not all(visible(x) for x in [rs, ls]):
            continue

        # Best overhead margin across window (y smaller = higher in frame)
        if visible(rw):
            overhead = rs['y'] - rw['y']
            if overhead > best_overhead:
                best_overhead = overhead
                best_rs_y = rs['y']
        if visible(lw):
            overhead = ls['y'] - lw['y']
            if overhead > best_overhead:
                best_overhead = overhead

        if visible(re) and re['y'] < rs['y']:
            elbow_elevated = True

        if visible(nose) and visible(rw) and rw['y'] < nose['y'] - 0.05:
            wrist_above_nose = True

    rw_peak = get_lm(peak_lm, 'right_wrist')
    rs_peak = get_lm(peak_lm, 'right_shoulder')
    if not visible(rw_peak) or not visible(rs_peak):
        return 0.3, ['insufficient landmarks at peak']

    # Primary: wrist reached above shoulder at some point in window
    if best_overhead > 0:
        score += min(0.55, best_overhead * 2.5)
        reasons.append(f'wrist overhead by {best_overhead:.3f} in window')
    elif best_overhead > -0.05:
        score += 0.2
        reasons.append('wrist near shoulder height')

    if elbow_elevated:
        score += 0.2
        reasons.append('elbow above shoulder')

    if wrist_above_nose:
        score += 0.2
        reasons.append('wrist above nose (full extension)')

    # Wrist coming down at peak velocity (follow-through) = good serve signal
    if visible(rw_peak) and visible(rs_peak) and rw_peak['y'] > rs_peak['y']:
        score += 0.1
        reasons.append('wrist below shoulder at peak = downswing contact')

    return min(score, 1.0), reasons


SCORERS = {
    'forehand': score_forehand,
    'backhand': score_backhand,
    'serve':    score_serve,
}


# ── Pose lookup by frame number ───────────────────────────────────────────────

def build_pose_index(frames):
    """Map frame_number -> landmarks for fast lookup."""
    index = {}
    for f in frames:
        if f['landmarks']:
            index[f['frame']] = f['landmarks']
    return index


def nearest_pose(index, target_frame, search_range=9):
    """Find closest frame with landmarks to target_frame."""
    for offset in range(search_range):
        for delta in [0, -offset, offset]:
            if target_frame + delta in index:
                return index[target_frame + delta]
    return None


# ── Clip extractor ────────────────────────────────────────────────────────────

def extract_clip(cap, start_frame, end_frame, out_path, fps, fourcc):
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
    for _ in range(end_frame - start_frame):
        ret, frame = cap.read()
        if not ret:
            break
        writer.write(frame)
    writer.release()


# ── Main ──────────────────────────────────────────────────────────────────────

def process_job(job):
    shot_type = job['shot_type']
    scorer = SCORERS[shot_type]
    print(f"\n{'='*50}")
    print(f"  {shot_type.upper()}")
    print(f"{'='*50}")

    with open(job['poses']) as f:
        pose_data = json.load(f)
    with open(job['swings']) as f:
        swing_data = json.load(f)

    fps = pose_data['fps']
    pose_index = build_pose_index(pose_data['frames'])
    swings = swing_data['swings']

    os.makedirs(job['out_dir'], exist_ok=True)
    os.makedirs(job['out_dir'] + '_rejected', exist_ok=True)

    cap = cv2.VideoCapture(job['video'])
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')

    accepted = rejected = 0
    results = []

    for i, sw in enumerate(swings):
        peak_frame = sw['peak_frame']
        peak_lm = nearest_pose(pose_index, peak_frame)
        prev_lm = nearest_pose(pose_index, peak_frame - 3)

        if peak_lm is None:
            rejected += 1
            continue

        if shot_type == 'serve':
            window_lms = []
            for offset in range(-int(fps), int(fps * 0.5), 3):
                lm = nearest_pose(pose_index, sw['peak_frame'] + offset)
                if lm:
                    window_lms.append(lm)
            confidence, reasons = scorer(peak_lm, prev_lm, window_lms)
        else:
            confidence, reasons = scorer(peak_lm, prev_lm)
        sw['confidence'] = round(confidence, 3)
        sw['confidence_reasons'] = reasons

        if confidence >= MIN_CONFIDENCE:
            fname = f"{shot_type}_swing_{sw['swing_id']:04d}_conf{int(confidence*100)}.mp4"
            out_path = os.path.join(job['out_dir'], fname)
            extract_clip(cap, sw['start_frame'], sw['end_frame'], out_path, fps, fourcc)
            accepted += 1
            sw['clip_path'] = out_path
        else:
            rejected += 1
            sw['clip_path'] = None

        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(swings)}] accepted={accepted} rejected={rejected}")

    cap.release()

    # Save updated swings with confidence scores
    swing_data['swings'] = swings
    swing_data['extraction_summary'] = {
        'accepted': accepted,
        'rejected': rejected,
        'min_confidence': MIN_CONFIDENCE,
    }
    validated_path = job['swings'].replace('.json', '_validated.json')
    with open(validated_path, 'w') as f:
        json.dump(swing_data, f, indent=2)

    print(f"\n  Done: {accepted} accepted, {rejected} rejected ({int(100*accepted/(accepted+rejected))}% pass rate)")
    print(f"  Clips saved to: {job['out_dir']}")
    print(f"  Validated swings: {validated_path}")


if __name__ == '__main__':
    for job in JOBS:
        if not os.path.exists(job['poses']) or not os.path.exists(job['swings']):
            print(f"Skipping {job['shot_type']} — files not found")
            continue
        process_job(job)

    print("\nAll done.")
