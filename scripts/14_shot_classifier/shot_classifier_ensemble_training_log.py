"""
Training log + trust gate for the ENSEMBLE shot classifier
(classify_shot.classify_ensemble: geom overhead-serve gate +
trajectory-kNN forehand/backhand). Separate log from the rule-based and ML
students so the ensemble earns trust on its own record.

Mirrors shot_classifier_ml_training_log.py's shape/thresholds exactly -- see
shot_classifier_training_log.py for the reasoning. `student_pick` here is the
ensemble's pick; 'uncertain' / None picks are logged with agreed=None so they
don't count toward the trust math (they're the cases that SHOULD go to Claude).

Zero incremental Claude cost: rides along on the verdict already being made
for the rule-based student.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_ensemble_training_log.jsonl')

AGREEMENT_THRESHOLD = 0.90
MIN_EXAMPLES_BEFORE_TRUST = 50
WINDOW = 100


def log_example(scores, student_pick, claude_pick, agreed, lock=None, clip_path=None,
                contact_frame=None, source=None):
    record = {
        'timestamp': time.time(),
        'scores': scores,
        'student_pick': student_pick,
        'claude_pick': claude_pick,
        'agreed': agreed,
        'source': source,          # which ensemble branch decided it
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
    print(f'{len(records)} logged examples ({sum(1 for r in records if r.get("agreed") is not None)} paired)')
    rate = agreement_rate()
    print(f'Agreement rate (last {WINDOW}): {rate if rate is not None else "n/a"}')
    print(f'Trust ensemble without verifier: {should_trust_student()}')
