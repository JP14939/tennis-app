import json
import math
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '04_clip_extraction'))
from extract_clips import SCORERS, build_pose_index, nearest_pose

JOBS = [
    ('forehand', r'C:\Users\jackp\tennis_app\data\02_pose_extraction\forehand_poses.json', r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings.json'),
    ('backhand', r'C:\Users\jackp\tennis_app\data\02_pose_extraction\backhand_poses.json', r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings.json'),
    ('serve',    r'C:\Users\jackp\tennis_app\data\02_pose_extraction\serve_poses.json',    r'C:\Users\jackp\tennis_app\data\03_swing_detection\serve_swings.json'),
]

THRESHOLD = 0.5

for shot_type, poses_path, swings_path in JOBS:
    with open(poses_path) as f:
        pose_data = json.load(f)
    with open(swings_path) as f:
        swing_data = json.load(f)

    pose_index = build_pose_index(pose_data['frames'])
    scorer = SCORERS[shot_type]
    swings = swing_data['swings']

    fps = pose_data['fps']
    scores = []
    for sw in swings:
        peak_lm = nearest_pose(pose_index, sw['peak_frame'])
        prev_lm = nearest_pose(pose_index, sw['peak_frame'] - 3)
        if peak_lm is None:
            scores.append(0.0)
            continue
        # For serve, pass landmarks from entire window so scorer can find peak wrist height
        if shot_type == 'serve':
            window_lms = []
            for offset in range(-int(fps), int(fps * 0.5), 3):
                lm = nearest_pose(pose_index, sw['peak_frame'] + offset)
                if lm:
                    window_lms.append(lm)
            conf, _ = scorer(peak_lm, prev_lm, window_lms)
        else:
            conf, _ = scorer(peak_lm, prev_lm)
        scores.append(conf)

    accepted = sum(1 for s in scores if s >= THRESHOLD)
    total = len(scores)
    avg = sum(scores) / total if total else 0

    buckets = {'0.0-0.3': 0, '0.3-0.5': 0, '0.5-0.7': 0, '0.7-1.0': 0}
    for s in scores:
        if s < 0.3:    buckets['0.0-0.3'] += 1
        elif s < 0.5:  buckets['0.3-0.5'] += 1
        elif s < 0.7:  buckets['0.5-0.7'] += 1
        else:          buckets['0.7-1.0'] += 1

    print(f"\n{shot_type.upper()}")
    print(f"  Total swings : {total}")
    print(f"  Pass (>={THRESHOLD}) : {accepted}  ({int(100*accepted/total)}%)")
    print(f"  Avg confidence : {avg:.3f}")
    print(f"  Distribution  : {buckets}")
