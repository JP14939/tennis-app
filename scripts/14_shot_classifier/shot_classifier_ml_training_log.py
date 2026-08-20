"""
Training log for the NEW ML shot-classifier (train_shot_classifier_model.py)
against the SAME Claude verdicts the rule-based classifier is already being
checked against -- a separate log/trust gate from
shot_classifier_training_log.py's (the rule-based one), so the ML model has
to earn trust independently rather than inheriting the rule-based
classifier's already-poor 38% agreement rate.

Mirrors shot_classifier_training_log.py's shape/thresholds exactly (same
AGREEMENT_THRESHOLD/MIN_EXAMPLES_BEFORE_TRUST/WINDOW) -- see that module's
docstring for the reasoning behind each. `student_pick` here is the ML
model's pick (classify_shot.classify_ml()), not the rule-based one.

No incremental Claude cost from this: Claude is already called on every
shot-classification request (the rule-based student is never trusted --
see shot_classifier_training_log.py), so logging the ML model's pick
against that same already-happening verdict adds zero API calls of its
own -- it only rides along on spend that already exists.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_ml_training_log.jsonl')

AGREEMENT_THRESHOLD = 0.90
MIN_EXAMPLES_BEFORE_TRUST = 50
WINDOW = 100


def log_example(scores, student_pick, claude_pick, agreed, lock=None, clip_path=None, contact_frame=None):
    record = {
        'timestamp': time.time(),
        'scores': scores,
        'student_pick': student_pick,
        'claude_pick': claude_pick,
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
