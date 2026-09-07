"""
Training log for the ML contact-frame corrector (train_contact_frame_model.py)
against the SAME ground-truth marks the heuristic student
(contact_frame_training_log.py) is checked against -- a separate log / trust
gate so the model earns trust independently rather than inheriting the
heuristic's ~50% within-tolerance rate. Mirrors
scripts/16_shot_verification/shot_contact_ml_training_log.py, but the metric
is regression (frame error), not agreement, so it reuses
contact_frame_training_log.py's tolerance-rate conventions.

Rides along for free: every place that logs a heuristic-vs-teacher example
(log_user_contact_frame.py, log_manual_review.py) also computes the model's
corrected frame and logs it here -- no new ground truth is collected.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402
from contact_frame_training_log import (  # noqa: E402
    TOLERANCE_FRAMES, MIN_EXAMPLES_BEFORE_TRUST, WITHIN_TOLERANCE_THRESHOLD, WINDOW,
)

LOG_PATH = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'contact_frame_ml_training_log.jsonl')


def log_example(ml_frame, student_frame, teacher_frame, fps, lock=None, source=None, clip_path=None):
    record = {
        'timestamp': time.time(),
        'ml_frame': ml_frame,
        'student_frame': student_frame,
        'teacher_frame': teacher_frame,
        'fps': fps,
        'ml_error': teacher_frame - ml_frame,
        'student_error': teacher_frame - student_frame,
        'source': source,
        'clip_path': clip_path,
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

    def _write():
        with open(LOG_PATH, 'a') as f:
            f.write(json.dumps(record) + '\n')

    if lock is not None:
        with lock:
            _write()
    else:
        _write()


def read_log():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def stats(window=WINDOW):
    """{n, ml_mean_abs_error, ml_within_tolerance_rate,
        student_within_tolerance_rate, trusted} over the last `window` rows.
    trusted iff the ML corrector clears the tolerance bar the heuristic
    couldn't -- i.e. it's actually adding value."""
    records = [r for r in read_log() if r.get('ml_error') is not None][-window:]
    if not records:
        return {'n': 0, 'ml_mean_abs_error': None, 'ml_within_tolerance_rate': None,
                'student_within_tolerance_rate': None, 'trusted': False}

    n = len(records)
    ml_abs = [abs(r['ml_error']) for r in records]
    ml_within = sum(1 for e in ml_abs if e <= TOLERANCE_FRAMES) / n
    stu_within = sum(1 for r in records if abs(r['student_error']) <= TOLERANCE_FRAMES) / n

    trusted = n >= MIN_EXAMPLES_BEFORE_TRUST and ml_within >= WITHIN_TOLERANCE_THRESHOLD
    return {
        'n': n,
        'ml_mean_abs_error': round(sum(ml_abs) / n, 2),
        'ml_within_tolerance_rate': round(ml_within, 4),
        'student_within_tolerance_rate': round(stu_within, 4),
        'trusted': trusted,
    }


def should_trust_student():
    return stats()['trusted']


if __name__ == '__main__':
    print(f'{len(read_log())} logged examples')
    print(json.dumps(stats(), indent=2))
