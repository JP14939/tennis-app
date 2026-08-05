"""
Compare a user's swing video against the pro database.

Usage:
  python compare_swing.py <video_path> <shot_type> [--top N]

Returns the top N closest pro swings with similarity scores and coaching tips.
"""

import json
import math
import os
import sys
import argparse
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '09_coaching_ai'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
from infer_angle import infer_camera_angle, angle_label
from build_pro_database import normalise_landmarks, trajectory_scale, PRE_SEC, POST_SEC
from trajectory_compare import dtw_distance
from track_racket_in_clip import track_racket_body, avg_racket_body_distance
from select_coaching_tips import get_coaching_tips
from paths import DATA_DIR
import phase_breakdown

DB_PATH    = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', 'pose_landmarker.task')

KEY_LANDMARKS = [
    'nose',
    'left_shoulder', 'right_shoulder',
    'left_elbow',    'right_elbow',
    'left_wrist',    'right_wrist',
    'left_hip',      'right_hip',
]

LANDMARK_NAMES = [
    'nose','left_eye_inner','left_eye','left_eye_outer','right_eye_inner','right_eye',
    'right_eye_outer','left_ear','right_ear','mouth_left','mouth_right','left_shoulder',
    'right_shoulder','left_elbow','right_elbow','left_wrist','right_wrist','left_pinky',
    'right_pinky','left_index','right_index','left_thumb','right_thumb','left_hip',
    'right_hip','left_knee','right_knee','left_ankle','right_ankle','left_heel',
    'right_heel','left_foot_index','right_foot_index'
]

# ── Maths ─────────────────────────────────────────────────────────────────────

def similarity_score(dist, scale=0.4):
    """Convert a DTW distance (avg per-landmark-per-frame error, in
    shoulder-width units) to a 0-100 similarity score."""
    return round(max(0, 100 * math.exp(-dist / scale)), 1)


# ── Pose extraction from user video ──────────────────────────────────────────

def extract_user_poses(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video_path}')

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps   = cap.get(cv2.CAP_PROP_FPS)
    print(f'  Video: {os.path.basename(video_path)} | {total} frames @ {fps:.1f}fps', file=sys.stderr)

    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        output_segmentation_masks=False,
        num_poses=1,
    )

    frames = []
    idx = 0
    with vision.PoseLandmarker.create_from_options(options) as lmk:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if idx % 3 == 0:  # match extract_poses.py's sample_every=3 used for the pro database, so DTW compares equal-density trajectories
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = lmk.detect(img)
                lm_dict = None
                if result.pose_landmarks:
                    lm_dict = {LANDMARK_NAMES[i]: {'name': LANDMARK_NAMES[i], 'x': lm.x, 'y': lm.y, 'z': lm.z, 'visibility': lm.visibility}
                               for i, lm in enumerate(result.pose_landmarks[0])}
                frames.append({'frame': idx, 'timestamp': round(idx / fps, 3), 'landmarks': lm_dict})
            idx += 1

    cap.release()
    detected = sum(1 for f in frames if f['landmarks'])
    print(f'  Pose detected in {detected}/{len(frames)} sampled frames ({int(100*detected/len(frames) if frames else 0)}%)', file=sys.stderr)
    return frames, fps


def find_peak_wrist_frame(frames, fps):
    """Find the frame with highest wrist velocity — the contact point."""
    max_vel = 0
    peak_idx = len(frames) // 2  # fallback to middle
    prev_rw = prev_lw = None

    for i, f in enumerate(frames):
        if not f['landmarks']:
            continue
        rw = f['landmarks'].get('right_wrist')
        lw = f['landmarks'].get('left_wrist')
        vel = 0
        if rw and prev_rw:
            vel = max(vel, math.sqrt((rw['x']-prev_rw['x'])**2 + (rw['y']-prev_rw['y'])**2))
        if lw and prev_lw:
            vel = max(vel, math.sqrt((lw['x']-prev_lw['x'])**2 + (lw['y']-prev_lw['y'])**2))
        if vel > max_vel:
            max_vel = vel
            peak_idx = i
        prev_rw, prev_lw = rw, lw

    return peak_idx


def build_user_trajectory(frames, fps, contact_time_sec=None):
    """
    Sample every available pose frame (native ~15-30fps, since
    extract_user_poses keeps every 2nd frame) from PRE_SEC before to POST_SEC
    after the contact frame, mirroring extract_swing_trajectory in
    build_pro_database.py so the two are DTW-comparable.

    If contact_time_sec is given (the frame the user manually marked as
    contact in ContactMarkingScreen), that's used directly instead of
    re-detecting contact via wrist velocity — the user's manual frame-by-frame
    marking is ground truth and should never be second-guessed by a heuristic.

    Returns (trajectory, contact_frame_num).
    """
    frame_index = {f['frame']: f['landmarks'] for f in frames if f['landmarks']}

    if contact_time_sec is not None:
        target_frame = round(contact_time_sec * fps)
        contact_frame_num = min((f['frame'] for f in frames), key=lambda x: abs(x - target_frame))
    else:
        contact_frame_num = frames[find_peak_wrist_frame(frames, fps)]['frame']

    lo = contact_frame_num - int(PRE_SEC * fps)
    hi = contact_frame_num + int(POST_SEC * fps)

    window_frames = [frame_index[f] for f in range(lo, hi + 1) if f in frame_index]
    scale = trajectory_scale(window_frames)
    if scale is None:
        return [], contact_frame_num

    trajectory = []
    for f in sorted(fr for fr in frame_index if lo <= fr <= hi):
        norm = normalise_landmarks(frame_index[f], scale)
        if norm is not None:
            trajectory.append({'t': round((f - contact_frame_num) / fps, 4), 'landmarks': norm})

    return trajectory, contact_frame_num


# ── Coaching tips generator ───────────────────────────────────────────────────

# ── Main comparison ───────────────────────────────────────────────────────────

def compare(video_path, shot_type, top_n=3, angle_window=20, contact_time_sec=None):
    print(f'\nAnalysing {shot_type} swing...', file=sys.stderr)

    print('  Extracting poses from user video...', file=sys.stderr)
    frames, fps = extract_user_poses(video_path)
    user_trajectory, peak_frame = build_user_trajectory(frames, fps, contact_time_sec)
    if contact_time_sec is not None:
        print(f'  Using user-marked contact frame {peak_frame} ({peak_frame/fps:.2f}s, requested {contact_time_sec:.2f}s)', file=sys.stderr)
    else:
        print(f'  Contact point auto-detected at frame {peak_frame} ({peak_frame/fps:.2f}s)', file=sys.stderr)

    # Infer user camera angle at the contact frame
    print('  Inferring camera angle...', file=sys.stderr)
    user_angle, angle_conf, angle_debug = infer_camera_angle(video_path, peak_frame)
    if user_angle is not None:
        print(f'  Camera angle: {user_angle}° ({angle_label(user_angle)}) — confidence: {angle_conf}', file=sys.stderr)
    else:
        print(f'  Camera angle: could not infer ({angle_debug})', file=sys.stderr)

    print('  Loading pro database...', file=sys.stderr)
    with open(DB_PATH) as f:
        db = json.load(f)

    all_candidates = [e for e in db['entries'] if e['shot_type'] == shot_type]

    # Filter by angle if we have a user angle and the database has angle data
    if user_angle is not None:
        angle_filtered = [
            c for c in all_candidates
            if c.get('camera_angle') is not None
            and abs(c['camera_angle'] - user_angle) <= angle_window
        ]
        if len(angle_filtered) >= 5:
            candidates = angle_filtered
            print(f'  Angle filter ±{angle_window}°: {len(candidates)}/{len(all_candidates)} {shot_type} candidates', file=sys.stderr)
        else:
            candidates = all_candidates
            print(f'  Angle filter: only {len(angle_filtered)} within ±{angle_window}° — using all {len(candidates)} {shot_type} swings', file=sys.stderr)
    else:
        candidates = all_candidates
        print(f'  No angle data — comparing against all {len(candidates)} {shot_type} swings', file=sys.stderr)

    print(f'  Comparing trajectories (DTW) against {len(candidates)} candidates...', file=sys.stderr)
    results = []
    for entry in candidates:
        dist = dtw_distance(user_trajectory, entry['trajectory'], KEY_LANDMARKS)
        score = similarity_score(dist)
        results.append((score, dist, entry))

    results.sort(key=lambda x: -x[0])
    top = results[:top_n]

    print(f'\n{"="*50}', file=sys.stderr)
    print(f'  TOP {top_n} PRO MATCHES', file=sys.stderr)
    print(f'{"="*50}', file=sys.stderr)

    output = []
    for rank, (score, dist, entry) in enumerate(top, 1):
        tips_result, _ = get_coaching_tips(user_trajectory, entry['trajectory'], shot_type)
        tips = [{'tip_text': t['tip_text'], 'drill': t.get('drill')} for t in tips_result]

        print(f'\n  #{rank} — {entry["id"]}', file=sys.stderr)
        print(f'       Similarity: {score}/100', file=sys.stderr)
        if entry.get('camera_angle') is not None:
            print(f'       Pro angle:  {entry["camera_angle"]}°', file=sys.stderr)
        print(f'       Coaching tips:', file=sys.stderr)
        for tip in tips:
            print(f'         • {tip["tip_text"]}', file=sys.stderr)
        if not tips:
            print(f'         • Great technique! Your form closely matches the pro.', file=sys.stderr)

        output.append({
            'rank':       rank,
            'pro_id':     entry['id'],
            'shot_type':  shot_type,
            'similarity': score,
            'clip_path':  entry.get('clip_path'),
            'pro_angle':  entry.get('camera_angle'),
            'pro_contact_time_sec': entry.get('peak_time'),
            'tips':       tips if tips else [{'tip_text': 'Great technique! Your form closely matches the pro.', 'drill': None}],
        })

    # Phase breakdown (backswing/contact/follow-through/body-rotation) is
    # only computed for the top match -- it needs per-frame racket tracking
    # on the user's video, which is too expensive to run against every
    # candidate.
    if top:
        print('  Computing phase breakdown (top match only)...', file=sys.stderr)
        top_entry = top[0][2]
        try:
            lo = peak_frame - int(PRE_SEC * fps)
            hi = peak_frame + int(POST_SEC * fps)
            racket_frames = track_racket_body(video_path, frame_range=(lo, hi))
            user_racket_body_distance = avg_racket_body_distance(racket_frames)
            breakdown = phase_breakdown.compute_phase_breakdown(
                user_trajectory, top_entry, shot_type, user_racket_body_distance)
            output[0]['phases'] = {k: v for k, v in breakdown.items() if k != 'overall_score'}
            output[0]['overall_score'] = breakdown['overall_score']
            print(f'  Overall phase score: {breakdown["overall_score"]}', file=sys.stderr)
        except Exception as e:
            print(f'  Phase breakdown failed (non-fatal): {e}', file=sys.stderr)

    result = {
        'user_video':   video_path,
        'shot_type':    shot_type,
        'user_angle':   user_angle,
        'angle_label':  angle_label(user_angle) if user_angle is not None else None,
        'angle_conf':   angle_conf if user_angle is not None else None,
        'contact_time_sec': round(peak_frame / fps, 3),
        'matches':      output,
    }

    result_path = os.path.join(DATA_DIR, 'runtime', 'last_comparison.json')
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(f'\n  Results saved to {result_path}', file=sys.stderr)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('video', help='Path to user swing video')
    parser.add_argument('shot_type', choices=['forehand', 'backhand', 'serve'])
    parser.add_argument('--top', type=int, default=3)
    parser.add_argument('--angle-window', type=int, default=20, help='Angle filter window in degrees (default: 20)')
    parser.add_argument('--contact-time', type=float, default=None, help='User-marked contact time in seconds (from ContactMarkingScreen). If omitted, contact is auto-detected via wrist velocity.')
    args = parser.parse_args()
    compare(args.video, args.shot_type, args.top, args.angle_window, args.contact_time)
