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
from infer_angle import infer_camera_angle, angle_label, detect_view_direction, extract_frame, create_landmarker
from build_pro_database import normalise_landmarks, trajectory_scale, PRE_SEC, POST_SEC, MIN_TRAJECTORY_POINTS
from trajectory_compare import dtw_distance
from track_racket_in_clip import track_racket_body, avg_racket_body_distance, track_racket_path
from select_coaching_tips import get_coaching_tips
from paths import DATA_DIR
import phase_breakdown

DB_PATH         = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
OVERLAY_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'overlay_trajectories.json')
PLAYER_NAMES_PATH = os.path.join(DATA_DIR, '06_pro_database', 'player_names.json')
MODEL_PATH      = os.path.join(os.path.dirname(__file__), '..', 'pose_landmarker.task')

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


def build_racket_overlay_trajectory(racket_frames, fps):
    """
    Same convention as build_overlay_trajectory() but for racket keypoints
    (handle/throat/tip/left_edge/right_edge, from track_racket_path()) rather
    than body landmarks -- feeds the frontend's racket swing-path overlay.
    't' is video-relative seconds computed the same way (frame / fps), so
    both overlays sync to one shared playhead with no extra translation.
    """
    result = []
    for f in racket_frames:
        points = {name: ({'x': p[0], 'y': p[1]} if p else None) for name, p in f['points'].items()}
        result.append({'t': round(f['frame'] / fps, 3), 'points': points})
    return result


def build_overlay_trajectory(frames):
    """
    Reduce raw per-frame pose output (extract_user_poses' shape) to the 9
    upper-body KEY_LANDMARKS, keeping RAW image-normalized (0-1) x/y --
    unlike build_user_trajectory, this is NOT re-centered/rescaled for DTW,
    since a skeleton overlay needs to line up with actual video pixels, not
    a shoulder-width-normalized comparison space. 't' is the frame's own
    video-relative timestamp so the frontend can sync directly to the
    video's own playhead.
    """
    result = []
    for f in frames:
        if not f['landmarks']:
            continue
        landmarks = {}
        for k in KEY_LANDMARKS:
            lm = f['landmarks'].get(k)
            landmarks[k] = {'x': lm['x'], 'y': lm['y']} if lm and lm['visibility'] >= 0.3 else None
        result.append({'t': f['timestamp'], 'landmarks': landmarks})
    return result


# ── Pose extraction from user video ──────────────────────────────────────────

def extract_user_poses(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video_path}')

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps   = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        # Some malformed/corrupt containers report fps=0.0 from OpenCV. Left
        # unguarded, the very next `round(idx / fps, 3)` below raises
        # ZeroDivisionError on frame 0 -- caught by pro_matcher.py's/
        # video_matcher.py's outer try/except, but surfaces to the user as an
        # opaque "float division by zero" instead of an actionable message.
        cap.release()
        raise RuntimeError(f'Could not read a valid frame rate from the uploaded video ({os.path.basename(video_path)}) -- it may be corrupted.')
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
        # MediaPipe always returns an x/y for every landmark regardless of
        # confidence -- rw/lw are truthy even when `visibility` is near 0
        # (motion blur is common right at contact, on fast swings). Without
        # this gate, a spuriously large frame-to-frame jump from a
        # low-confidence wrist detection can be mistaken for the velocity
        # peak, silently shifting the whole comparison window and
        # corrupting the DTW score with no error surfacing anywhere. Same
        # 0.5 threshold as detect_swings.py's compute_wrist_velocity(),
        # the pro-database side's equivalent function.
        if rw and prev_rw and rw['visibility'] > 0.5:
            vel = max(vel, math.sqrt((rw['x']-prev_rw['x'])**2 + (rw['y']-prev_rw['y'])**2))
        if lw and prev_lw and lw['visibility'] > 0.5:
            vel = max(vel, math.sqrt((lw['x']-prev_lw['x'])**2 + (lw['y']-prev_lw['y'])**2))
        if vel > max_vel:
            max_vel = vel
            peak_idx = i
        prev_rw, prev_lw = rw, lw

    return peak_idx


def build_user_trajectory(frames, fps, contact_time_sec=None):
    """
    Sample every available pose frame (native ~15-30fps, since
    extract_user_poses keeps every 3rd frame) from PRE_SEC before to POST_SEC
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

    # Mirrors extract_swing_trajectory's guard in build_pro_database.py --
    # without it, a near-empty (1-4 point) trajectory sails past the `if not
    # user_trajectory` check below (it's non-empty, just barely) and DTW
    # against a full pro swing degrades into little more than the average
    # per-frame distance from one static pose, silently returning a
    # meaningless similarity score instead of the clear "couldn't extract a
    # usable pose trajectory" error this same failure mode already produces
    # when it's total rather than near-total.
    if len(trajectory) < MIN_TRAJECTORY_POINTS:
        return [], contact_frame_num

    return trajectory, contact_frame_num


# ── Coaching tips generator ───────────────────────────────────────────────────

# ── Main comparison ───────────────────────────────────────────────────────────

def compare(video_path, shot_type, top_n=3, angle_window=20, contact_time_sec=None, view_direction_hint=None, frames_fps=None):
    """
    frames_fps: optional pre-extracted (frames, fps) tuple (same shape
    extract_user_poses returns) to skip re-running pose extraction when the
    caller already has it for this exact video. Defaults to None so every
    existing caller (pro_matcher.py / the live /api/analyse route) behaves
    exactly as before -- this is purely an opt-in fast path.
    """
    print(f'\nAnalysing {shot_type} swing...', file=sys.stderr)

    if frames_fps is not None:
        print('  Reusing already-extracted poses from user video...', file=sys.stderr)
        frames, fps = frames_fps
    else:
        print('  Extracting poses from user video...', file=sys.stderr)
        frames, fps = extract_user_poses(video_path)
    if not frames:
        # find_peak_wrist_frame's fallback (len(frames)//2) and the
        # contact_time_sec min() below both index/reduce over `frames` --
        # on an empty list that's an unhandled IndexError/ValueError instead
        # of a clear error. Happens on a corrupt/undecodable upload where
        # cv2 opens the file but every single cap.read() fails.
        raise RuntimeError('No frames could be decoded from the uploaded video')
    user_trajectory, peak_frame = build_user_trajectory(frames, fps, contact_time_sec)
    if not user_trajectory:
        # Same guard compare_videos.py already has for the equivalent case --
        # without it, DTW against every pro candidate returns inf, similarity
        # collapses to 0 for all of them, and the caller gets a normal-looking
        # HTTP 200 "0% similarity to every pro" instead of a clear error that
        # pose extraction effectively failed (e.g. player barely visible,
        # very oblique angle, poor lighting).
        raise RuntimeError('Could not extract a usable pose trajectory from the video — try a clearer angle or better lighting.')
    if contact_time_sec is not None:
        print(f'  Using user-marked contact frame {peak_frame} ({peak_frame/fps:.2f}s, requested {contact_time_sec:.2f}s)', file=sys.stderr)
        # Free, ongoing training data for the previously-untrained
        # find_contact_frame() detector (see contact_frame_training_log.py)
        # -- deliberately NOT run inline here. Measured this session: the
        # racket/ball tracking pass alone takes ~5s regardless of outcome,
        # real added latency on a synchronous user-facing response for a
        # step that provides zero value to the user. backend/src/routes/
        # analyse.js instead spawns log_user_contact_frame_cli.py as a
        # detached background process AFTER the response is already sent --
        # this function does not touch it at all.
    else:
        print(f'  Contact point auto-detected at frame {peak_frame} ({peak_frame/fps:.2f}s)', file=sys.stderr)

    # A single shared landmarker for the angle/view-direction detection below
    # (both accept one for exactly this reason -- see infer_angle.py's
    # create_landmarker() docstring) instead of each creating and tearing
    # down their own model instance.
    shared_landmarker = create_landmarker()

    # Infer user camera angle at the contact frame
    print('  Inferring camera angle...', file=sys.stderr)
    user_angle, angle_conf, angle_debug = infer_camera_angle(
        video_path, peak_frame, landmarker=shared_landmarker, view_direction_hint=view_direction_hint)
    if user_angle is not None:
        print(f'  Camera angle: {user_angle}° ({angle_label(user_angle)}) — confidence: {angle_conf}', file=sys.stderr)
    else:
        print(f'  Camera angle: could not infer ({angle_debug})', file=sys.stderr)

    # View direction (front = camera at the net facing you, back = camera
    # behind the baseline) -- a separate signal from the angle above, since
    # both can produce a similarly narrow net width despite mirrored pose
    # landmarks. Server-side detection is the source of truth; the
    # frontend's record-time picker is only used as a fallback when
    # detection itself can't tell (contact frame not usable, net not found).
    user_view_direction = 'unknown'
    try:
        contact_frame_img = extract_frame(video_path, peak_frame)
        user_view_direction = detect_view_direction(contact_frame_img, landmarker=shared_landmarker)
    except Exception as e:
        print(f'  View direction detection failed (non-fatal): {e}', file=sys.stderr)
    if user_view_direction == 'unknown' and view_direction_hint in ('front', 'back'):
        user_view_direction = view_direction_hint
        print(f'  View direction: could not detect, using stated hint "{view_direction_hint}"', file=sys.stderr)
    else:
        print(f'  View direction: {user_view_direction}', file=sys.stderr)

    # Done with the shared landmarker -- release it now rather than at
    # function end, since there's real work below (DTW over hundreds of
    # candidates, phase breakdown) and this is called once per swing in
    # long batch runs; no reason to hold the model loaded any longer than
    # its actual usage window.
    try:
        shared_landmarker.close()
    except Exception:
        pass

    print('  Loading pro database...', file=sys.stderr)
    with open(DB_PATH) as f:
        db = json.load(f)

    player_names = {}
    if os.path.exists(PLAYER_NAMES_PATH):
        with open(PLAYER_NAMES_PATH, encoding='utf-8') as f:
            player_names = json.load(f)

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

    # Filter by view direction on top of the angle filter, same
    # fall-back-if-too-few-candidates shape as the angle filter above --
    # some shot types have very few (or zero, for serve) front-view
    # entries, so this must never leave too small a pool to compare against.
    if user_view_direction in ('front', 'back'):
        direction_filtered = [c for c in candidates if c.get('view_direction') == user_view_direction]
        if len(direction_filtered) >= 5:
            candidates = direction_filtered
            print(f'  View-direction filter ({user_view_direction}): {len(candidates)} candidates', file=sys.stderr)
        else:
            print(f'  View-direction filter: only {len(direction_filtered)} matching "{user_view_direction}" — keeping the angle-filtered set', file=sys.stderr)

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
        # use_verifier=False: this runs synchronously on every real user
        # request (unlike the offline training scripts that call this same
        # function to deliberately invoke the verifier) -- see
        # select_coaching_tips.py's docstring for why this must stay off
        # here until the teacher-student loop is intentionally wired live.
        tips_result, _ = get_coaching_tips(user_trajectory, entry['trajectory'], shot_type, use_verifier=False)
        tips = [{'id': t.get('issue_id'), 'tip_text': t['tip_text'], 'drill': t.get('drill'),
                  'severity': t.get('severity')} for t in tips_result]

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
            'player_name': player_names.get(entry['id']),
            'shot_type':  shot_type,
            'similarity': score,
            'clip_path':  entry.get('clip_path'),
            'pro_angle':  entry.get('camera_angle'),
            # Contact time WITHIN entry['clip_path'] (the played-back clip
            # file), not entry['peak_time'] (contact time in the source
            # compilation video, wrong timeline for seeking clip_path).
            'pro_contact_time_sec': entry.get('clip_contact_time_sec'),
            'tips':       tips if tips else [{'tip_text': 'Great technique! Your form closely matches the pro.', 'drill': None}],
        })

    # Phase breakdown (backswing/contact/follow-through/body-rotation) is
    # only computed for the top match -- it needs per-frame racket tracking
    # on the user's video, which is too expensive to run against every
    # candidate.
    user_racket_overlay_trajectory = None
    if top:
        print('  Computing phase breakdown (top match only)...', file=sys.stderr)
        top_entry = top[0][2]
        try:
            lo = peak_frame - int(PRE_SEC * fps)
            hi = peak_frame + int(POST_SEC * fps)
            # sample_every=4 to match enrich_pro_racket_body.py's stride when
            # it precomputed top_entry['racket_body_distance'] for every pro
            # database entry -- the default (3) here would compare the user's
            # distance against a pro value built from a different sampling
            # density than what's actually being diffed against it.
            racket_frames = track_racket_body(video_path, frame_range=(lo, hi), sample_every=4)
            user_racket_body_distance = avg_racket_body_distance(racket_frames)
            breakdown = phase_breakdown.compute_phase_breakdown(
                user_trajectory, top_entry, shot_type, user_racket_body_distance)
            output[0]['phases'] = {
                k: v for k, v in breakdown.items() if k not in ('overall_score', 'phase_markers')
            }
            output[0]['overall_score'] = breakdown['overall_score']
            output[0]['phase_markers'] = breakdown['phase_markers']
            print(f'  Overall phase score: {breakdown["overall_score"]}', file=sys.stderr)
        except Exception as e:
            print(f'  Phase breakdown failed (non-fatal): {e}', file=sys.stderr)

        # Racket swing-path overlay -- separate detection pass from
        # track_racket_body() above (that one only keeps the 'handle' point,
        # this keeps all 5, for tracing the racket tip's path over time, not
        # scoring body rotation). Same reasoning as the skeleton overlay:
        # user side is cheap/live since we already have the frame range;
        # non-fatal on failure, same pattern as phase breakdown above.
        try:
            racket_path_frames = track_racket_path(video_path, frame_range=(lo, hi))
            user_racket_overlay_trajectory = build_racket_overlay_trajectory(racket_path_frames, fps)
        except Exception as e:
            print(f'  Racket path tracking failed (non-fatal): {e}', file=sys.stderr)

        # Skeleton overlay data -- only for the top match, mirroring the
        # phase-breakdown-only-for-top-match pattern above. Pro side is a
        # precomputed lookup (see 13_overlay_trajectories/); user side is
        # cheap since we already have the raw frames from this request.
        try:
            with open(OVERLAY_DB_PATH, encoding='utf-8') as f:
                overlay_db = json.load(f)
            pro_overlay = overlay_db.get(top_entry['id'])
            if pro_overlay is not None:
                output[0]['pro_overlay_trajectory'] = pro_overlay
        except FileNotFoundError:
            print('  No overlay_trajectories.json found (run 13_overlay_trajectories/build_pro_overlay_trajectories.py) -- skipping pro skeleton overlay', file=sys.stderr)
        except Exception as e:
            print(f'  Pro overlay lookup failed (non-fatal): {e}', file=sys.stderr)

        # Pro-side racket path -- unlike the skeleton overlay above, there's
        # no precomputed database for this yet, so it's tracked live against
        # the pro's own clip file (same one pro_clip_url is served from).
        # Real added cost (not "already running" the way the user side is,
        # since nothing currently tracks racket keypoints on pro clips) --
        # acceptable for one top-match clip, non-fatal on failure.
        try:
            # entry['clip_path'] is stored relative to 04_clips (not an
            # absolute path -- see relative_clip_path() in
            # build_pro_database.py), so it has to be resolved against this
            # machine's own DATA_DIR before it's a real file.
            pro_clip_path_rel = top_entry.get('clip_path')
            pro_clip_path = os.path.join(DATA_DIR, '04_clips', pro_clip_path_rel) if pro_clip_path_rel else None
            if pro_clip_path and os.path.exists(pro_clip_path):
                pro_racket_frames = track_racket_path(pro_clip_path)
                pro_cap = cv2.VideoCapture(pro_clip_path)
                pro_fps = pro_cap.get(cv2.CAP_PROP_FPS) or fps
                pro_cap.release()
                output[0]['pro_racket_overlay_trajectory'] = build_racket_overlay_trajectory(pro_racket_frames, pro_fps)
        except Exception as e:
            print(f'  Pro racket path tracking failed (non-fatal): {e}', file=sys.stderr)

    result = {
        'user_video':   video_path,
        'shot_type':    shot_type,
        'user_angle':   user_angle,
        'angle_label':  angle_label(user_angle) if user_angle is not None else None,
        'angle_conf':   angle_conf if user_angle is not None else None,
        'contact_time_sec': round(peak_frame / fps, 3),
        'user_view_direction': user_view_direction,
        'user_overlay_trajectory': build_overlay_trajectory(frames),
        'racket_overlay_trajectory': user_racket_overlay_trajectory,
        'matches':      output,
    }

    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('video', help='Path to user swing video')
    parser.add_argument('shot_type', choices=['forehand', 'backhand', 'serve'])
    parser.add_argument('--top', type=int, default=3)
    parser.add_argument('--angle-window', type=int, default=20, help='Angle filter window in degrees (default: 20)')
    parser.add_argument('--contact-time', type=float, default=None, help='User-marked contact time in seconds (from ContactMarkingScreen). If omitted, contact is auto-detected via wrist velocity.')
    parser.add_argument('--view-direction-hint', choices=['front', 'back'], default=None, help='User-stated filming position (from the record-time picker), used only if server-side detection is inconclusive.')
    args = parser.parse_args()
    result = compare(args.video, args.shot_type, args.top, args.angle_window, args.contact_time, args.view_direction_hint)

    # Debug convenience for a manual CLI run only -- moved out of compare()
    # itself, which the live backend calls once per /api/analyse request via
    # pro_matcher.py (never through this __main__ block). Every one of those
    # concurrent, per-user calls used to write this exact same fixed path,
    # racing every other in-flight request's write for no reader anywhere in
    # the app (confirmed: nothing else references last_comparison.json).
    result_path = os.path.join(DATA_DIR, 'runtime', 'last_comparison.json')
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(f'\n  Results saved to {result_path}', file=sys.stderr)
