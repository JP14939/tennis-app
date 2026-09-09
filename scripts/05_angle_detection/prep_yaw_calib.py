"""
Phase 2 prep: turn the long multi-swing calibration recordings into a
per-swing manifest for validate_yaw_normalization.py.

Input recordings (Jack, 2026-09-09) -- same forehand repeated from 6 camera
positions, ~2.7 min each:
  IMG_5901  center, on the centre mark            ~0  deg   (bucket A)
  IMG_5902  ~1.5 m off centre, behind baseline    ~18 deg   (bucket B)
  IMG_5905  down the doubles tramline             ~30 deg   (bucket C)
  IMG_5906  down the doubles tramline             ~30 deg   (bucket C)
  IMG_5907  in the corner, diagonal across        ~45 deg   (bucket D)
  IMG_5909  side on, from the sideline            ~88 deg   (bucket E, negative control)

For each recording: extract pose (image + world landmarks) at POSE_STRIDE and
cache it; find wrist-velocity swing peaks; keep the ones with >= LEADIN_MIN_SEC
of quiet (near-zero wrist speed) before them -- those have the ready-stance
lead-in the yaw estimate needs. Emit data/05_angle_detection/yaw_calib_manifest.json.

Usage:
  python prep_yaw_calib.py                 # extract (cached) + build manifest
  python prep_yaw_calib.py --per-source 3  # keep at most N swings per recording
"""
import argparse
import json
import os
import sys

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '03_swing_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
from detect_swings import compute_wrist_velocity, smooth, SMOOTH_WINDOW  # noqa: E402
from extract_poses import LANDMARK_NAMES  # noqa: E402
from viewpoint_normalization import facing_azimuth  # noqa: E402

DATA_DIR = os.path.join(SCRIPTS_DIR, '..', 'data')
CALIB_DIR = os.path.join(DATA_DIR, '05_angle_detection', 'yaw_calib')
CLIPS_DIR = os.path.join(CALIB_DIR, 'clips')
POSE_DIR = os.path.join(CALIB_DIR, 'poses')
MANIFEST_PATH = os.path.join(DATA_DIR, '05_angle_detection', 'yaw_calib_manifest.json')
MODEL_PATH = os.path.join(SCRIPTS_DIR, 'pose_landmarker.task')

POSE_STRIDE = 3          # every 3rd frame -- enough for detection + the relative checks
# Jack self-feeds (drop/toss then hit) and walks to collect balls between reps,
# so there is no long "stand perfectly still" lead-in and wrist speed is never
# truly zero. Select swings by AZIMUTH STABILITY instead: a strong wrist-speed
# spike whose ~0.5 s pre-swing window has the shoulder/hip facing held steady
# (that steadiness is exactly what the yaw estimate needs).
LEADIN_LO_SEC = -0.75    # pre-swing azimuth window: [LO, HI] seconds relative to the peak
LEADIN_HI_SEC = -0.15
LEADIN_MIN_FRAMES = 4
LEADIN_MAX_AZ_STDEV = 22.0
HANDEDNESS = 'right'
SHOT_TYPE = 'forehand'

SOURCES = [
    ('IMG_5901', 'A', 0),
    ('IMG_5902', 'B', 18),
    ('IMG_5905', 'C', 30),
    ('IMG_5906', 'C', 30),
    ('IMG_5907', 'D', 45),
    ('IMG_5909', 'E', 88),
]


def _extract_pose(mov_path, out_path):
    if os.path.exists(out_path):
        return json.load(open(out_path))
    cap = cv2.VideoCapture(mov_path)
    if not cap.isOpened():
        raise RuntimeError(f'cannot open {mov_path}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    opts = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=MODEL_PATH), num_poses=1)
    frames = []
    idx = 0
    with vision.PoseLandmarker.create_from_options(opts) as lm:
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            if idx % POSE_STRIDE == 0:
                img = mp.Image(image_format=mp.ImageFormat.SRGB,
                               data=cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
                r = lm.detect(img)
                rec = {'frame': idx, 'timestamp': round(idx / fps, 3),
                       'landmarks': None, 'world_landmarks': None}
                if r.pose_landmarks:
                    rec['landmarks'] = [
                        {'name': LANDMARK_NAMES[i], 'x': round(p.x, 4), 'y': round(p.y, 4),
                         'z': round(p.z, 4), 'visibility': round(p.visibility, 4)}
                        for i, p in enumerate(r.pose_landmarks[0])]
                if r.pose_world_landmarks:
                    rec['world_landmarks'] = [
                        {'name': LANDMARK_NAMES[i], 'x': round(p.x, 4), 'y': round(p.y, 4),
                         'z': round(p.z, 4), 'visibility': round(p.visibility, 4)}
                        for i, p in enumerate(r.pose_world_landmarks[0])]
                frames.append(rec)
                if len(frames) % 200 == 0:
                    print(f'    {os.path.basename(mov_path)}: {idx}/{total}', flush=True)
            idx += 1
    cap.release()
    data = {'video': os.path.basename(mov_path), 'fps': fps, 'total_frames': total, 'frames': frames}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(data, open(out_path, 'w'))
    return data


def _swings_with_leadin(pose_data, per_source):
    import statistics
    all_frames = pose_data['frames']
    img_frames = [f for f in all_frames if f['landmarks']]
    fps = pose_data['fps']
    if len(img_frames) < 20:
        return []
    vel = smooth(compute_wrist_velocity(img_frames), SMOOTH_WINDOW)
    world = {f['frame']: {lm['name']: lm for lm in f['world_landmarks']}
             for f in all_frames if f.get('world_landmarks')}
    wfnums = sorted(world)

    vs = sorted(vel)
    thr = vs[int(len(vs) * 0.90)]
    min_gap = int(2.5 * fps)

    # strongest local maxima first
    cand = [(vel[i], img_frames[i]['frame']) for i in range(3, len(vel) - 3)
            if vel[i] >= thr and vel[i] == max(vel[i - 3:i + 4])]
    cand.sort(reverse=True)

    picked, used = [], []
    for pv, pf in cand:
        if any(abs(pf - u) < min_gap for u in used):
            continue
        azs = [az for fn in wfnums
               if LEADIN_LO_SEC <= (fn - pf) / fps <= LEADIN_HI_SEC
               and (az := facing_azimuth(world[fn])) is not None]
        if len(azs) < LEADIN_MIN_FRAMES or statistics.pstdev(azs) > LEADIN_MAX_AZ_STDEV:
            continue
        picked.append({'peak_frame': pf, 'peak_time_sec': round(pf / fps, 3),
                       'peak_velocity': round(pv, 5),
                       'leadin_az_median': round(statistics.median(azs), 1),
                       'leadin_az_stdev': round(statistics.pstdev(azs), 1),
                       'leadin_n': len(azs)})
        used.append(pf)
        if len(picked) >= per_source:
            break
    picked.sort(key=lambda x: x['peak_frame'])
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-source', type=int, default=4)
    args = ap.parse_args()

    manifest = []
    for grp_i, (name, bucket, deg) in enumerate(SOURCES):
        mov = os.path.join(CLIPS_DIR, f'{name}.MOV')
        if not os.path.exists(mov):
            print(f'  MISSING {mov}')
            continue
        print(f'  {name} (bucket {bucket}, ~{deg} deg)...')
        pose = _extract_pose(mov, os.path.join(POSE_DIR, f'{name}.json'))
        swings = _swings_with_leadin(pose, args.per_source)
        print(f'    {len(swings)} swings with lead-in')
        for si, sw in enumerate(swings):
            manifest.append({
                'source': name,
                'pose_cache': f'poses/{name}.json',
                'swing_group': f'{name}_{si}',
                'coarse_bucket': {'A': 'behind_centre', 'B': 'behind_centre',
                                  'C': 'diagonal', 'D': 'diagonal', 'E': 'side_on'}[bucket],
                'bucket_letter': bucket,
                'approx_deg': deg,
                'shot_type': SHOT_TYPE,
                'handedness': HANDEDNESS,
                'contact_frame': sw['peak_frame'],
                'contact_time_sec': sw['peak_time_sec'],
                'peak_velocity': sw['peak_velocity'],
                'leadin_az_median': sw['leadin_az_median'],
                'leadin_az_stdev': sw['leadin_az_stdev'],
                'leadin_n': sw['leadin_n'],
            })

    json.dump(manifest, open(MANIFEST_PATH, 'w'), indent=1)
    print(f'\n{len(manifest)} swings -> {MANIFEST_PATH}')
    from collections import Counter
    print('  by bucket:', dict(Counter(m['bucket_letter'] for m in manifest)))


if __name__ == '__main__':
    main()
