"""
Training log for the NEW ML contact-verification model
(train_shot_contact_model.py) against the SAME Claude verdicts the
rule-based bucket trust system (shot_contact_training_log.py) is already
checked against -- a separate log/trust gate, so the ML model has to earn
trust independently rather than inheriting whichever bucket's agreement
rate it happens to correlate with. Mirrors
scripts/14_shot_classifier/shot_classifier_ml_training_log.py's shape/
thresholds exactly -- see that module's docstring for the reasoning behind
each. `student_pick` here is the ML model's pick
(verify_shot_contact_verified.predict_contact_ml()), not the rule-based
bucket's.

No incremental Claude cost from this: it only logs against a Claude call
that's already happening (get_verified_shot_contact() only reaches this
point when the rule-based bucket ISN'T trusted and Claude gets called
anyway), so this rides along for free.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '16_shot_verification', 'shot_contact_ml_training_log.jsonl')

AGREEMENT_THRESHOLD = 0.90
MIN_EXAMPLES_BEFORE_TRUST = 50
WINDOW = 100


def log_example(student_pick, teacher_pick, agreed, lock=None, clip_path=None, contact_frame=None):
    record = {
        'timestamp': time.time(),
        'student_pick': student_pick,
        'teacher_pick': teacher_pick,
        'agreed': agreed,
        'clip_path': clip_path,
        'contact_frame': contact_frame,
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


def agreement_rate(window=WINDOW):
    records = [r for r in read_log() if r.get('agreed') is not None][-window:]
    if not records:
        return None
    return sum(1 for r in records if r['agreed']) / len(records)


def should_trust_student():
    paired = [r for r in read_log() if r.get('agreed') is not None]
    if len(paired) < MIN_EXAMPLES_BEFORE_TRUST:
        return False
    rate = agreement_rate()
    return rate is not None and rate >= AGREEMENT_THRESHOLD


if __name__ == '__main__':
    records = read_log()
    print(f'{len(records)} logged examples')
    rate = agreement_rate()
    print(f'Agreement rate (last {WINDOW}): {rate if rate is not None else "n/a"}')
    print(f'Trust ML model without verifier: {should_trust_student()}')
