"""
Build the pro swing feature database.

For each validated swing we extract normalised pose features at 3 key moments:
  - backswing  (0.5s before contact)
  - contact    (peak wrist velocity frame)
  - follow-through (1.0s after contact)

Normalisation: translate so shoulder midpoint = (0,0), scale so shoulder width = 1.0.
This makes comparison body-size and camera-distance invariant.

Output: data/pro_database.json
"""

import json
import os
import math
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '05_angle_detection'))
from infer_angle import infer_camera_angle, infer_angle_from_source, create_landmarker

# Upper-body landmarks used for comparison (ignore legs)
KEY_LANDMARKS = [
    'nose',
    'left_shoulder', 'right_shoulder',
    'left_elbow',    'right_elbow',
    'left_wrist',    'right_wrist',
    'left_hip',      'right_hip',
]

JOBS = [
    {
        'shot_type':        'forehand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\forehand_poses.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\forehand\forehand_compilation_1.mp4',
    },
    {
        'shot_type':        'backhand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\backhand_poses.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\backhand\backhand_compilation_1.mp4',
    },
    {
        'shot_type':        'serve',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\serve_poses.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\serve_swings_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\serve\serve_compilation_1.mp4',
    },
    # Additional compilations added 2026-08-02 for footage diversity
    {
        'shot_type':        'forehand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\forehand_poses_2.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings_2_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\forehand\forehand_compilation_2.mp4',
    },
    {
        'shot_type':        'forehand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\forehand_poses_3.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings_3_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\forehand\forehand_compilation_3.mp4',
    },
    {
        'shot_type':        'backhand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\backhand_poses_2.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings_2_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\backhand\backhand_compilation_2.mp4',
    },
    {
        'shot_type':        'backhand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\backhand_poses_3.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings_3_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\backhand\backhand_compilation_3.mp4',
    },
    {
        'shot_type':        'backhand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\backhand_poses_4.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings_4_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\backhand\backhand_compilation_4.mp4',
    },
    {
        'shot_type':        'serve',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\serve_poses_2.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\serve_swings_2_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\serve\serve_compilation_2.mp4',
    },
]

MIN_CONFIDENCE = 0.5


# ── Pose helpers ──────────────────────────────────────────────────────────────

def build_pose_index(frames):
    index = {}
    for f in frames:
        if f['landmarks']:
            index[f['frame']] = {lm['name']: lm for lm in f['landmarks']}
    return index


def get_shoulder_ref(lm_dict):
    ls = lm_dict.get('left_shoulder')
    rs = lm_dict.get('right_shoulder')
    if not ls or not rs:
        return None, None, None
    mid_x = (ls['x'] + rs['x']) / 2
    mid_y = (ls['y'] + rs['y']) / 2
    width = math.sqrt((ls['x'] - rs['x'])**2 + (ls['y'] - rs['y'])**2)
    return mid_x, mid_y, width


def normalise_landmarks(lm_dict, scale=None):
    """Return normalised (x, y) for KEY_LANDMARKS. Returns None if ref missing.

    `scale` should be a single stable shoulder-width value shared across an
    entire trajectory (see trajectory_scale()) rather than this frame's own
    shoulder width. Shoulder width fluctuates ~30% frame-to-frame as the body
    rotates through a swing (foreshortening), so dividing by the per-frame
    width amplifies ordinary pose-detection noise into large coordinate swings
    at exactly the frames that matter (mid-swing, near contact). Translation
    (mid_x/mid_y) is still taken per-frame since it should track the body."""
    mid_x, mid_y, width = get_shoulder_ref(lm_dict)
    if not mid_x or width < 0.01:
        return None
    if scale is None:
        scale = width

    result = {}
    for name in KEY_LANDMARKS:
        lm = lm_dict.get(name)
        if lm and lm.get('visibility', 0) >= 0.3:
            result[name] = {
                'x': round((lm['x'] - mid_x) / scale, 4),
                'y': round((lm['y'] - mid_y) / scale, 4),
            }
        else:
            result[name] = None
    return result


def trajectory_scale(lm_dicts):
    """Median shoulder width across a window of raw landmark dicts — a
    single stable scale for the whole trajectory instead of per-frame width."""
    widths = [w for lm in lm_dicts if lm and (w := get_shoulder_ref(lm)[2]) is not None and w >= 0.01]
    return statistics.median(widths) if widths else None


# ── Trajectory extraction for one swing ──────────────────────────────────────

PRE_SEC = 0.5
POST_SEC = 1.0
MIN_TRAJECTORY_POINTS = 5


def extract_swing_trajectory(swing, pose_index, fps):
    """
    Sample every available pose frame (native ~20fps from extract_poses.py)
    from PRE_SEC before to POST_SEC after the peak (contact) frame, instead
    of 3 fixed snapshots — this preserves the actual shape/speed of the swing
    for DTW comparison rather than compressing it to 3 points.

    Returns a list of {'t': seconds relative to contact, 'landmarks': {...}},
    or None if too few usable frames are found.
    """
    peak = swing['peak_frame']
    lo = peak - int(PRE_SEC * fps)
    hi = peak + int(POST_SEC * fps)

    window_frames = [pose_index[f] for f in range(lo, hi + 1) if f in pose_index]
    scale = trajectory_scale(window_frames)
    if scale is None:
        return None

    trajectory = []
    for f in sorted(fr for fr in pose_index if lo <= fr <= hi):
        norm = normalise_landmarks(pose_index[f], scale)
        if norm is not None:
            trajectory.append({'t': round((f - peak) / fps, 4), 'landmarks': norm})

    if len(trajectory) < MIN_TRAJECTORY_POINTS:
        return None
    return trajectory


# ── Main ──────────────────────────────────────────────────────────────────────

def build_database():
    all_entries = []

    print('Creating pose landmarker for angle inference...')
    angle_landmarker = create_landmarker()

    for job in JOBS:
        shot_type = job['shot_type']
        print(f'\n{shot_type.upper()}')

        with open(job['poses']) as f:
            pose_data = json.load(f)
        with open(job['swings_validated']) as f:
            swing_data = json.load(f)

        fps = pose_data['fps']
        pose_index = build_pose_index(pose_data['frames'])
        swings = [s for s in swing_data['swings'] if s.get('confidence', 0) >= MIN_CONFIDENCE]
        print(f'  {len(swings)} validated swings')

        source_video = job.get('source_video')
        ok = skipped = angle_ok = angle_fail = 0
        for sw in swings:
            trajectory = extract_swing_trajectory(sw, pose_index, fps)
            if trajectory is None:
                skipped += 1
                continue

            # Infer camera angle from the extracted clip
            camera_angle = None
            angle_confidence = None
            clip_path = sw.get('clip_path')
            if clip_path and os.path.exists(clip_path):
                try:
                    ang, conf, _ = infer_camera_angle(clip_path, landmarker=angle_landmarker)
                    if ang is not None:
                        camera_angle = ang
                        angle_confidence = round(conf, 3)
                        angle_ok += 1
                    elif source_video and os.path.exists(source_video):
                        # Clip-based detection failed — try wider window in source video
                        ang, conf, _ = infer_angle_from_source(
                            source_video, sw['peak_time_sec'], landmarker=angle_landmarker
                        )
                        if ang is not None:
                            camera_angle = ang
                            angle_confidence = round(conf, 3)
                            angle_ok += 1
                        else:
                            angle_fail += 1
                    else:
                        angle_fail += 1
                except Exception:
                    angle_fail += 1
            else:
                angle_fail += 1

            entry = {
                'id':               f"{shot_type}_{sw['swing_id']:04d}",
                'shot_type':        shot_type,
                'swing_id':         sw['swing_id'],
                'confidence':       sw['confidence'],
                'peak_time':        sw['peak_time_sec'],
                'clip_path':        clip_path,
                'camera_angle':     camera_angle,
                'angle_confidence': angle_confidence,
                'trajectory':       trajectory,
            }
            all_entries.append(entry)
            ok += 1

            if ok % 20 == 0:
                print(f'    {ok}/{len(swings)} processed...', end='\r')

        print(f'  {ok} entries built, {skipped} skipped  |  angles: {angle_ok} inferred, {angle_fail} failed')

    angle_landmarker.close()

    out_path = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'
    with open(out_path, 'w') as f:
        json.dump({
            'total': len(all_entries),
            'shots': {'forehand': 0, 'backhand': 0, 'serve': 0},
            'entries': all_entries,
        }, f)

    # Update shot counts
    with open(out_path) as f:
        db = json.load(f)
    for e in db['entries']:
        db['shots'][e['shot_type']] += 1
    with open(out_path, 'w') as f:
        json.dump(db, f)

    with_angle = sum(1 for e in db['entries'] if e.get('camera_angle') is not None)
    print(f'\nDatabase built: {len(all_entries)} entries')
    print(f"  Forehand:  {db['shots']['forehand']}")
    print(f"  Backhand:  {db['shots']['backhand']}")
    print(f"  Serve:     {db['shots']['serve']}")
    print(f'  Angles:    {with_angle}/{len(all_entries)} entries have camera_angle')
    print(f'  Saved to:  {out_path}')


if __name__ == '__main__':
    build_database()
