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
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '09_coaching_ai'))

from infer_angle import infer_camera_angle, angle_label
from compare_swing import extract_user_poses, build_user_trajectory, similarity_score, KEY_LANDMARKS, build_overlay_trajectory
from trajectory_compare import dtw_distance
from select_coaching_tips import get_coaching_tips

# Above this angular difference between the two videos' inferred camera
# angles, the two clips aren't comparable — unlike the pro-database flow
# (which only ever matches against angle-filtered, pre-vetted clips), a 1v1
# comparison has no such filtering, so a framing mismatch this large is
# treated as a hard rejection rather than a soft warning.
ANGLE_MISMATCH_WARNING_DEG = 25

# Vertical elevation compatibility: reject unless both videos' elevation
# bands are equal or adjacent on this scale. 'unknown' (no readable height
# signal) never matches anything, since there's no way to confirm the two
# cameras were at a similar height.
ELEVATION_ORDER = ['level', 'uncertain', 'possibly_elevated']


def elevation_compatible(status_a, status_b):
    if status_a not in ELEVATION_ORDER or status_b not in ELEVATION_ORDER:
        return False
    return abs(ELEVATION_ORDER.index(status_a) - ELEVATION_ORDER.index(status_b)) <= 1


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
    angle_a, angle_a_conf, debug_a = infer_camera_angle(reference_path, peak_a)

    print('  Extracting poses from your video...', file=sys.stderr)
    frames_b, fps_b = extract_user_poses(your_path)
    traj_b, peak_b = build_user_trajectory(frames_b, fps_b, contact_b)
    angle_b, angle_b_conf, debug_b = infer_camera_angle(your_path, peak_b)

    if not traj_a or not traj_b:
        raise RuntimeError('Could not extract a usable pose trajectory from one of the videos — try a clearer angle or trim closer to the contact point.')

    print('  Comparing trajectories (DTW)...', file=sys.stderr)
    dist = dtw_distance(traj_a, traj_b, KEY_LANDMARKS)
    score = similarity_score(dist)

    angle_mismatch_deg = None
    if angle_a is not None and angle_b is not None:
        angle_mismatch_deg = round(abs(angle_a - angle_b), 1)

    tips_result, _ = get_coaching_tips(traj_b, traj_a, shot_type)
    tips = [{'tip_text': t['tip_text'], 'drill': t.get('drill')} for t in tips_result]

    # Hard camera-setup gate: a 1v1 comparison has no angle-filtered pro
    # database to fall back on, so a framing mismatch this large corrupts
    # the DTW score more than the pro-database flow's soft warning allows for.
    if angle_mismatch_deg is None or angle_mismatch_deg > ANGLE_MISMATCH_WARNING_DEG:
        raise RuntimeError(
            "Couldn't confirm both videos were filmed from a similar angle — "
            'film both from a similar side/face-on position and try again.'
        )
    if not elevation_compatible(debug_a.get('elevation_status'), debug_b.get('elevation_status')):
        raise RuntimeError(
            'Camera heights look different between the two videos — film both '
            'from a similar height (see the fence-mount guide) and try again.'
        )

    return {
        'shot_type':          shot_type,
        'similarity':         score,
        'reference_angle':    angle_a,
        'reference_angle_label': angle_label(angle_a) if angle_a is not None else None,
        'reference_contact_time_sec': round(peak_a / fps_a, 3),
        'your_angle':         angle_b,
        'your_angle_label':   angle_label(angle_b) if angle_b is not None else None,
        'your_contact_time_sec': round(peak_b / fps_b, 3),
        'reference_overlay_trajectory': build_overlay_trajectory(frames_a),
        'your_overlay_trajectory': build_overlay_trajectory(frames_b),
        'angle_mismatch_deg': angle_mismatch_deg,
        'angle_mismatch_warning': angle_mismatch_deg is not None and angle_mismatch_deg > ANGLE_MISMATCH_WARNING_DEG,
        'tips': tips if tips else [{'tip_text': 'Great technique! Your form closely matches the reference video.', 'drill': None}],
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
