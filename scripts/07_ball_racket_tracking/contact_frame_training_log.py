"""
Training log for find_contact_frame() (racket_tracker.py) -- unlike the
other three teacher-student loops this session built on (shot-contact,
shot-classifier, tip-selector), this is a genuinely new component: there
was previously NO ground truth anywhere for frame-level contact accuracy,
only the binary "was this a real shot" verdict.

Frame accuracy is a numeric-error problem, not a classification one, so the
trust metric here is different from the other three logs' simple agreement
rate: % of examples within a tolerance (default 2 frames) plus mean
absolute frame error, both over a rolling window. frame_error is kept
SIGNED (teacher_frame - student_frame) so a systematic early/late bias is
visible instead of being averaged away by abs().

Two ground-truth sources:
  - 'manual_review': Jack reviewing real match footage via the Dev Page's
    Swing Review tool.
  - 'user_submitted': any real user's own manually-marked contact frame
    from ContactMarkingScreen.js, captured live in backend/src/routes/
    analyse.js -- free, ongoing training data from normal app usage.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'contact_frame_training_log.jsonl')

# A ±2-frame tolerance at typical 30fps footage is ~67ms -- tight enough to
# matter for trajectory alignment (compare_swing.py rounds to the nearest
# pose frame anyway, see plan doc), loose enough that exact-frame agreement
# (unrealistic given even human review has some slop) isn't the bar.
TOLERANCE_FRAMES = 2
MIN_EXAMPLES_BEFORE_TRUST = 50
WITHIN_TOLERANCE_THRESHOLD = 0.90
WINDOW = 100


def log_example(student_frame, student_confidence, student_method, teacher_frame, fps, source,
                lock=None, student_meta=None):
    record = {
        'timestamp': time.time(),
        'student_frame': student_frame,
        'student_confidence': student_confidence,
        'student_method': student_method,
        'teacher_frame': teacher_frame,
        'fps': fps,
        'frame_error': teacher_frame - student_frame,
        'source': source,
        # Extra geometric signals (ball/racket detection counts around the
        # anchor, occlusion-gap length, min ball-racket distance) for
        # train_contact_frame_model.py to learn a correction offset from --
        # purely additive, stats()/read_log() ignore it.
        'student_meta': student_meta or {},
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


def stats(window=WINDOW, source=None):
    """
    {n, mean_abs_error, mean_signed_error, within_tolerance_rate, trusted}
    over the last `window` examples (optionally scoped to one `source`).
    Returns None fields when there's no data at all.
    """
    records = read_log()
    if source is not None:
        records = [r for r in records if r.get('source') == source]
    records = records[-window:]
    if not records:
        return {'n': 0, 'mean_abs_error': None, 'mean_signed_error': None,
                'within_tolerance_rate': None, 'trusted': False}

    errors = [r['frame_error'] for r in records]
    abs_errors = [abs(e) for e in errors]
    n = len(records)
    mean_abs = sum(abs_errors) / n
    mean_signed = sum(errors) / n
    within = sum(1 for e in abs_errors if e <= TOLERANCE_FRAMES) / n

    trusted = n >= MIN_EXAMPLES_BEFORE_TRUST and within >= WITHIN_TOLERANCE_THRESHOLD
    return {
        'n': n,
        'mean_abs_error': round(mean_abs, 2),
        'mean_signed_error': round(mean_signed, 2),
        'within_tolerance_rate': round(within, 4),
        'trusted': trusted,
    }


if __name__ == '__main__':
    all_records = read_log()
    print(f'{len(all_records)} logged examples total')
    overall = stats()
    print(f'Overall (last {WINDOW}): {json.dumps(overall)}')
    for src in ('manual_review', 'user_submitted', 'pro_clip_review'):
        s = stats(source=src)
        print(f'  {src}: {json.dumps(s)}')
