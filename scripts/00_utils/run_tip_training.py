"""
First real invocation of the teacher-student coaching-tip loop, against
manually-labeled real footage (not synthetic pro-vs-pro).

Usage:
  1. Watch each clip under data/04_clips/testing/<video>/*.mp4 and move it
     into the matching data/04_clips/testing/<video>/<shot_type>/ subfolder.
  2. python run_tip_training.py [--dry-run]

For each labeled clip: extracts the user's pose trajectory, finds its best
pro-database match (same DTW machinery as compare_swing.py), then calls
select_coaching_tips.get_coaching_tips() -- which runs the rule-based
student, calls Claude as teacher (real API cost, ~$0.002-0.003/call per
tip_verifier.py), and logs the (features, student_pick, claude_pick, agreed)
example to data/08_coaching_ai/tip_training_log.jsonl.
"""
import argparse
import glob
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '08_comparison_engine'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '09_coaching_ai'))

from compare_swing import extract_user_poses, build_user_trajectory, KEY_LANDMARKS, DB_PATH
from infer_angle import infer_camera_angle
from trajectory_compare import dtw_distance
from select_coaching_tips import get_coaching_tips
from tip_training_log import read_log, agreement_rate, should_trust_student

CLIPS_ROOT = r'C:\Users\jackp\tennis_app\data\04_clips\testing'
SHOT_TYPES = ('forehand', 'backhand', 'serve')


def find_labeled_clips():
    clips = []
    for video_dir in glob.glob(os.path.join(CLIPS_ROOT, '*')):
        if not os.path.isdir(video_dir):
            continue
        for shot_type in SHOT_TYPES:
            shot_dir = os.path.join(video_dir, shot_type)
            for clip_path in glob.glob(os.path.join(shot_dir, '*.mp4')):
                clips.append((clip_path, shot_type))
    return clips


def best_pro_match(user_trajectory, shot_type, user_angle, angle_window=20):
    with open(DB_PATH) as f:
        db = json.load(f)
    candidates = [e for e in db['entries'] if e['shot_type'] == shot_type]

    if user_angle is not None:
        angle_filtered = [c for c in candidates if c.get('camera_angle') is not None
                           and abs(c['camera_angle'] - user_angle) <= angle_window]
        if len(angle_filtered) >= 5:
            candidates = angle_filtered

    best_entry, best_dist = None, float('inf')
    for entry in candidates:
        dist = dtw_distance(user_trajectory, entry['trajectory'], KEY_LANDMARKS)
        if dist < best_dist:
            best_dist, best_entry = dist, entry
    return best_entry, best_dist


def process_clip(clip_path, shot_type, dry_run=False):
    print(f'\n=== {os.path.basename(clip_path)} ({shot_type}) ===')
    frames, fps = extract_user_poses(clip_path)
    user_trajectory, contact_frame = build_user_trajectory(frames, fps)
    if not user_trajectory:
        print('  Skipped: no usable trajectory (pose detection failed)')
        return None

    user_angle, angle_conf, _ = infer_camera_angle(clip_path, contact_frame)
    entry, dist = best_pro_match(user_trajectory, shot_type, user_angle)
    if entry is None:
        print('  Skipped: no pro match found')
        return None
    print(f'  Best pro match: {entry["id"]} (dist={dist:.3f}, user_angle={user_angle})')

    if dry_run:
        print('  [dry-run] Would call get_coaching_tips() here (real Claude API call)')
        return None

    tips, meta = get_coaching_tips(user_trajectory, entry['trajectory'], shot_type)
    print(f'  Source: {meta["source"]}  verified={meta["verified"]}')
    if meta.get('agreed_with_student') is not None:
        print(f'  Agreed with student: {meta["agreed_with_student"]}')
    for t in tips:
        print(f'    - [{t.get("severity")}] {t.get("tip_text")}')
    return tips, meta


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                         help='Run pose extraction + pro matching, but skip the Claude verifier call')
    args = parser.parse_args()

    clips = find_labeled_clips()
    if not clips:
        print(f'No labeled clips found under {CLIPS_ROOT}/<video>/<shot_type>/*.mp4')
        print('Move clips into their shot-type subfolder first.')
        sys.exit(0)

    print(f'Found {len(clips)} labeled clips.')
    by_shot = {}
    for _, st in clips:
        by_shot[st] = by_shot.get(st, 0) + 1
    print(by_shot)

    for clip_path, shot_type in clips:
        process_clip(clip_path, shot_type, dry_run=args.dry_run)

    if not args.dry_run:
        n = len(read_log())
        rate = agreement_rate()
        print(f'\n{n} total logged training examples. '
              f'Agreement rate (last 100): {rate if rate is not None else "n/a"}. '
              f'Trust student without verifier: {should_trust_student()}')
