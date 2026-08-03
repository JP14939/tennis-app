"""
Direct 1v1 comparison — compare a user's swing against an arbitrary
reference video (e.g. a pro clip they found themselves) instead of the
curated pro database. Reuses the same pose extraction / DTW / tips machinery
as compare_swing.py, just without the database lookup or angle filtering
(there's no candidate pool to filter here — it's exactly these two videos).

Usage:
  python compare_videos.py <reference_video> <your_video> <shot_type> \
      [--contact-a SEC] [--contact-b SEC]

Output (stdout): JSON — see compare_videos() docstring.
On error: {"error": "..."}
"""

import sys
import os
import json
import argparse

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))

from infer_angle import infer_camera_angle, angle_label
from compare_swing import extract_user_poses, build_user_trajectory, generate_tips, similarity_score, KEY_LANDMARKS
from trajectory_compare import dtw_distance, contact_landmarks

# Above this angular difference between the two videos' inferred camera
# angles, the DTW score is likely distorted by framing rather than technique
# — surfaced to the frontend as a caveat, not treated as an error.
ANGLE_MISMATCH_WARNING_DEG = 25


def compare_videos(reference_path, your_path, shot_type, contact_a=None, contact_b=None):
    """
    reference_path: the video you want to copy (e.g. a pro you found yourself)
    your_path:      your own swing video
    Returns a dict: similarity score, both videos' inferred camera angles
    (plus a mismatch flag), and coaching tips describing how `your_path`
    differs from `reference_path` at the contact frame.
    """
    print('  Extracting poses from reference video...', file=sys.stderr)
    frames_a, fps_a = extract_user_poses(reference_path)
    traj_a, peak_a = build_user_trajectory(frames_a, fps_a, contact_a)
    angle_a, angle_a_conf, _ = infer_camera_angle(reference_path, peak_a)

    print('  Extracting poses from your video...', file=sys.stderr)
    frames_b, fps_b = extract_user_poses(your_path)
    traj_b, peak_b = build_user_trajectory(frames_b, fps_b, contact_b)
    angle_b, angle_b_conf, _ = infer_camera_angle(your_path, peak_b)

    if not traj_a or not traj_b:
        raise RuntimeError('Could not extract a usable pose trajectory from one of the videos — try a clearer angle or trim closer to the contact point.')

    print('  Comparing trajectories (DTW)...', file=sys.stderr)
    dist = dtw_distance(traj_a, traj_b, KEY_LANDMARKS)
    score = similarity_score(dist)

    angle_mismatch_deg = None
    if angle_a is not None and angle_b is not None:
        angle_mismatch_deg = round(abs(angle_a - angle_b), 1)

    contact_a_lm = contact_landmarks(traj_a)
    contact_b_lm = contact_landmarks(traj_b)
    tips = generate_tips(contact_b_lm, contact_a_lm, shot_type)

    return {
        'shot_type':          shot_type,
        'similarity':         score,
        'reference_angle':    angle_a,
        'reference_angle_label': angle_label(angle_a) if angle_a is not None else None,
        'your_angle':         angle_b,
        'your_angle_label':   angle_label(angle_b) if angle_b is not None else None,
        'angle_mismatch_deg': angle_mismatch_deg,
        'angle_mismatch_warning': angle_mismatch_deg is not None and angle_mismatch_deg > ANGLE_MISMATCH_WARNING_DEG,
        'tips': tips if tips else ['Great technique! Your form closely matches the reference video.'],
    }


def main():
    parser = argparse.ArgumentParser(description='Compare two swing videos directly (no pro database)')
    parser.add_argument('reference_video', help='Video you want to copy')
    parser.add_argument('your_video', help='Your swing video')
    parser.add_argument('shot_type', choices=['forehand', 'backhand', 'serve'])
    parser.add_argument('--contact-a', type=float, default=None, help='User-marked contact time in reference video (seconds)')
    parser.add_argument('--contact-b', type=float, default=None, help='User-marked contact time in your video (seconds)')
    args = parser.parse_args()

    for path, label in [(args.reference_video, 'reference'), (args.your_video, 'your')]:
        if not os.path.exists(path):
            print(json.dumps({'error': f'{label.capitalize()} video not found: {path}'}))
            sys.exit(1)

    try:
        result = compare_videos(args.reference_video, args.your_video, args.shot_type,
                                 contact_a=args.contact_a, contact_b=args.contact_b)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
