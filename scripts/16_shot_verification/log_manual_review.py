"""
Logs Jack's own manual verdict on a swing candidate (from the Dev Page's
DevSwingReviewScreen.js) into up to three training logs -- the free,
no-Claude-cost substitute for the paid batch-verify path. Same
log_example() calls, same (student_pick, teacher_pick, agreed) shape,
source='user_flag' where that field exists, so this feeds
should_trust_bucket()/should_trust_student() identically to a
Claude-verified example.

Usage:
  echo '{"student_is_real_shot": true, "student_contact_confidence": 0.6,
         "student_contact_method": "ball_racket_proximity",
         "student_contact_frame_guess": 142, "fps": 30.0,
         "student_shot_type": "forehand", "student_shot_scores": {...},
         "is_real_shot": true, "shot_type": "backhand",
         "contact_frame": 145}' | python log_manual_review.py

Output (stdout): {"logged_contact": true, "logged_classifier": bool, "logged_contact_frame": bool}
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '16_shot_verification'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '14_shot_classifier'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking'))

import shot_contact_training_log as contact_log  # noqa: E402
import shot_classifier_training_log as classifier_log  # noqa: E402
import contact_frame_training_log as frame_log  # noqa: E402
import reviewed_candidates_log  # noqa: E402
from paths import DATA_DIR  # noqa: E402

HIGHLIGHT_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'highlight_clips', '13')


def main():
    payload = json.loads(sys.stdin.read())

    student_is_real_shot = payload.get('student_is_real_shot')
    is_real_shot = payload['is_real_shot']
    contact_log.log_example(
        student_is_real_shot, is_real_shot, student_is_real_shot == is_real_shot,
        source='user_flag',
        student_meta={
            'contact_confidence': payload.get('student_contact_confidence'),
            'contact_method': payload.get('student_contact_method'),
        },
    )
    # Always record the candidate as reviewed, regardless of verdict --
    # including "No, not a shot", so list_swing_candidates.py never serves
    # it again for this job.
    reviewed_candidates_log.log_reviewed(payload['job_id'], payload['rally_id'], payload['swing_index'])

    logged_classifier = False
    if is_real_shot and payload.get('shot_type'):
        student_shot_type = payload.get('student_shot_type')
        agreed = (student_shot_type == payload['shot_type']) if student_shot_type else None
        clip_path = os.path.join(HIGHLIGHT_CLIPS_DIR, str(payload['job_id']), f"rally_{payload['rally_id']:03d}.mp4")
        classifier_log.log_example(
            payload.get('student_shot_scores'), student_shot_type, payload['shot_type'], agreed,
            clip_path=clip_path, contact_frame=payload.get('contact_frame'),
        )
        logged_classifier = True

    logged_contact_frame = False
    student_contact_frame_guess = payload.get('student_contact_frame_guess')
    if is_real_shot and payload.get('contact_frame') is not None and student_contact_frame_guess is not None:
        # student_meta is sparse here -- this process has no racket/ball
        # `detections` object (unlike log_user_contact_frame.py), so the
        # detection-count features stay missing and get median-imputed by
        # train_contact_frame_model.py.
        meta = {
            'contact_method': payload.get('student_contact_method'),
            'contact_confidence': payload.get('student_contact_confidence'),
        }
        frame_log.log_example(
            student_contact_frame_guess,
            payload.get('student_contact_confidence'),
            payload.get('student_contact_method'),
            payload['contact_frame'],
            payload.get('fps'),
            source='manual_review',
            student_meta=meta,
        )
        logged_contact_frame = True

        try:
            from train_contact_frame_model import predict_contact_offset
            import contact_frame_ml_training_log as ml_log

            offset, available = predict_contact_offset({
                'student_method': payload.get('student_contact_method'),
                'student_confidence': payload.get('student_contact_confidence'),
                'fps': payload.get('fps'), 'student_meta': meta, 'source': 'manual_review',
            })
            if available:
                ml_log.log_example(
                    student_contact_frame_guess + offset, student_contact_frame_guess,
                    payload['contact_frame'], payload.get('fps'), source='manual_review',
                )
        except Exception as e:
            print(f'  [contact-frame-ml] skipped: {e}', file=sys.stderr)

    print(json.dumps({
        'logged_contact': True, 'logged_classifier': logged_classifier, 'logged_contact_frame': logged_contact_frame,
    }))


if __name__ == '__main__':
    main()
