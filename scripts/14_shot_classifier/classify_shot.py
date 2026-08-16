"""
Automatic shot-type classifier: forehand / backhand / serve.

Reuses extract_clips.py's existing rule-based confidence scorers
(score_forehand/score_backhand/score_serve) -- today they only validate an
ALREADY-ASSIGNED shot type's confidence; a classifier is just running all
three against an unknown swing and taking the highest score. No ML model,
consistent with this codebase's existing rule-based-first pattern
(tip_selector.py, phase_breakdown.py).

Usage:
  python classify_shot.py <video_path> <contact_time_sec>
"""
import argparse
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '08_comparison_engine'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '04_clip_extraction'))
from compare_swing import extract_user_poses  # noqa: E402
from extract_clips import SCORERS, nearest_pose  # noqa: E402

# Same window shape extract_clips.py's process_job() already uses for serve:
# -1s to +0.5s around contact, sampled every 3 frames.
SERVE_WINDOW_PRE_SEC = 1.0
SERVE_WINDOW_POST_SEC = 0.5
SERVE_WINDOW_STEP_FRAMES = 3


def classify(video_path, contact_time_sec, frames_fps=None):
    """
    frames_fps: optional pre-extracted (frames, fps) tuple (same shape
    extract_user_poses returns) to avoid re-running pose extraction when the
    caller already has it for this exact video -- e.g. classify_shot_verified.py
    reuses the same extraction compare_swing.compare() would otherwise redo.
    Defaults to None so every existing caller behaves exactly as before.
    """
    frames, fps = frames_fps if frames_fps is not None else extract_user_poses(video_path)
    pose_index = {f['frame']: list(f['landmarks'].values()) for f in frames if f['landmarks']}
    if not pose_index:
        raise RuntimeError('No pose detected anywhere in this video')

    contact_frame = round(contact_time_sec * fps)
    peak_lm = nearest_pose(pose_index, contact_frame)
    prev_lm = nearest_pose(pose_index, contact_frame - 3)
    if peak_lm is None:
        raise RuntimeError('No pose detected near the given contact time')

    window_lms = []
    lo = -int(SERVE_WINDOW_PRE_SEC * fps)
    hi = int(SERVE_WINDOW_POST_SEC * fps)
    for offset in range(lo, hi, SERVE_WINDOW_STEP_FRAMES):
        lm = nearest_pose(pose_index, contact_frame + offset)
        if lm:
            window_lms.append(lm)

    scores = {}
    for shot_type, scorer in SCORERS.items():
        if shot_type == 'serve':
            score, _ = scorer(peak_lm, prev_lm, window_lms)
        else:
            score, _ = scorer(peak_lm, prev_lm)
        scores[shot_type] = round(score, 3)

    best_shot = max(scores, key=scores.get)
    return {'shot_type': best_shot, 'scores': scores}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('contact_time_sec', type=float)
    args = parser.parse_args()

    try:
        result = classify(args.video, args.contact_time_sec)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
