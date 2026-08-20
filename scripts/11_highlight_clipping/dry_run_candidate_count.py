"""
One-off free dry-run: extract poses + find raw wrist-velocity swing
candidates for a video, WITHOUT running the Claude teacher-student
verification step (detect_rallies.py's filter_to_real_rally_shots()) --
this is exactly the free first half of detect_rallies.py's detect_rallies(),
stopping right before any Claude call would happen. No shot_contact_
verifier/classify_shot_verified imports at all, so there is no way for
this to accidentally spend anything.

Used to get a real candidate count for a not-yet-processed video before
deciding how much Claude verification spend to authorize on it, instead
of guessing from file size/duration alone.

Usage:
  python dry_run_candidate_count.py <video_path>
"""
import argparse
import os
import sys
import tempfile
import json

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '03_swing_detection'))

from extract_poses import extract_poses  # noqa: E402
from detect_swings import compute_wrist_velocity, find_swing_peaks, THRESHOLD_PERCENTILE  # noqa: E402

MIN_SWING_GAP_SEC = 1.5  # matches detect_rallies.py's own constant


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    args = parser.parse_args()

    print(f'Extracting poses for {args.video} (free, local, no Claude call)...')
    with tempfile.TemporaryDirectory() as tmp:
        pose_path = os.path.join(tmp, 'poses.json')
        extract_poses(args.video, pose_path, sample_every=3)
        with open(pose_path) as f:
            pose_data = json.load(f)

    fps = pose_data['fps']
    frames = pose_data['frames']

    print('\nComputing wrist velocity / finding swing peaks...')
    velocities = compute_wrist_velocity(frames)
    raw_swings = find_swing_peaks(velocities, frames, fps, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC)

    print(f'\n{len(raw_swings)} raw swing candidates detected:')
    for sw in raw_swings:
        print(f"  {sw['peak_time']:.1f}s")

    duration_sec = pose_data['total_frames'] / fps if fps else 0
    print(f"\nDone. {len(raw_swings)} candidates over {duration_sec:.1f}s "
          f"({len(raw_swings) / (duration_sec / 60):.1f} candidates/min).")


if __name__ == '__main__':
    main()
