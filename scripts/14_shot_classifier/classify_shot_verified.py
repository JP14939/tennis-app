"""
Orchestrator for the shot-classifier teacher-student loop. Mirrors
scripts/09_coaching_ai/select_coaching_tips.py's pattern exactly.

While the student (classify_shot.py's rule-based classify()) is still
learning (agreement rate below threshold, per shot_classifier_training_log.py),
every request also calls the Claude vision verifier, logs the
(scores, student_pick, claude_pick, agreed) example, and returns Claude's
pick (the teacher is authoritative during learning). Once the student is
trusted, Claude is skipped and the student's pick is returned directly --
saving API cost.

Usage:
  python classify_shot_verified.py <video_path> <contact_time_sec>
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '05_angle_detection'))
from classify_shot import classify  # noqa: E402
from shot_classifier_training_log import log_example, should_trust_student  # noqa: E402
from shot_classifier_verifier import verify_shot  # noqa: E402
from infer_angle import extract_frame  # noqa: E402


def get_verified_shot_type(video_path, contact_time_sec, use_verifier=True, frames_fps=None, log_lock=None):
    """
    frames_fps: optional pre-extracted (frames, fps) tuple, passed straight
    through to classify() to skip re-running pose extraction when the caller
    (analyze_rallies.py) already has it for this exact video. Defaults to
    None so existing behavior (extract internally) is unchanged.

    log_lock: optional lock passed straight through to
    shot_classifier_training_log.log_example() -- see that function's
    docstring. Defaults to None (no locking), safe for single-process callers.
    """
    student_result = classify(video_path, contact_time_sec, frames_fps=frames_fps)
    student_pick = student_result['shot_type']
    scores = student_result['scores']

    if not use_verifier or should_trust_student():
        return student_pick, {'source': 'student', 'verified': False, 'scores': scores}

    try:
        if frames_fps is not None:
            _, fps = frames_fps
        else:
            # extract_frame expects a frame number; classify() already knows
            # fps internally but doesn't expose it, so re-derive via cv2
            # quickly here rather than changing classify()'s return shape.
            import cv2
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            cap.release()
        frame = extract_frame(video_path, round(contact_time_sec * fps))

        claude_result = verify_shot(frame, scores, student_pick)
    except Exception as e:
        print(f'  Verifier call failed ({e}) -- falling back to student pick', file=sys.stderr)
        return student_pick, {'source': 'student', 'verified': False, 'scores': scores, 'verifier_error': str(e)}

    claude_pick = claude_result['shot_type']
    agreed = claude_pick == student_pick
    log_example(scores, student_pick, claude_pick, agreed, lock=log_lock)

    return claude_pick, {
        'source': 'claude_verified', 'verified': True, 'agreed_with_student': agreed,
        'scores': scores, 'reasoning': claude_result.get('reasoning'),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('contact_time_sec', type=float)
    parser.add_argument('--no-verifier', action='store_true', help='Skip Claude, use the rule-based student only')
    args = parser.parse_args()

    try:
        shot_type, meta = get_verified_shot_type(args.video, args.contact_time_sec, use_verifier=not args.no_verifier)
        print(json.dumps({'shot_type': shot_type, **meta}))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
