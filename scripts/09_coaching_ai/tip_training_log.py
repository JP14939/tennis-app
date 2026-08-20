"""
Training log for the tip-selector teacher-student loop, plus rolling
agreement-rate tracking used to decide when the student (tip_selector.py) is
accurate enough to trust without calling the Claude verifier on every request.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'tip_training_log.jsonl')

# Once the student's agreement with Claude over the last WINDOW examples is
# >= AGREEMENT_THRESHOLD, select_coaching_tips.py can stop calling the
# verifier on every request (see should_trust_student() below).
AGREEMENT_THRESHOLD = 0.90
MIN_EXAMPLES_BEFORE_TRUST = 50
WINDOW = 100


def log_example(shot_type, deviation_features, student_pick_ids, claude_pick_ids, agreed, source='claude'):
    """
    Append one training example. deviation_features is the full scored-issue
    list from tip_selector.score_issues() (signed deviation + magnitude per
    issue) — this is the input a future trained model would learn from;
    student/claude picks are the labels.

    source: 'claude' (default, unchanged behavior for the existing
    select_coaching_tips.py call site) or 'user_flag' -- a real person
    (Jack, via the Dev Page's Tip Review tool) substituting for the Claude
    teacher, free/no-API-cost, same pattern already used by
    shot_contact_training_log.py/shot_classifier_training_log.py.
    """
    record = {
        'timestamp': time.time(),
        'shot_type': shot_type,
        'deviation_features': deviation_features,
        'student_pick_ids': student_pick_ids,
        'claude_pick_ids': claude_pick_ids,
        'agreed': agreed,
        'source': source,
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + '\n')


def read_log():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def agreement_rate(window=WINDOW):
    """Fraction of the last `window` logged examples where student == claude."""
    records = read_log()[-window:]
    if not records:
        return None
    return sum(1 for r in records if r['agreed']) / len(records)


def should_trust_student():
    """
    Whether the student is accurate enough to skip calling Claude. Requires
    both a minimum sample size (don't trust a lucky streak) and a sustained
    agreement rate above AGREEMENT_THRESHOLD.
    """
    records = read_log()
    if len(records) < MIN_EXAMPLES_BEFORE_TRUST:
        return False
    rate = agreement_rate()
    return rate is not None and rate >= AGREEMENT_THRESHOLD


if __name__ == '__main__':
    records = read_log()
    print(f'{len(records)} logged examples')
    rate = agreement_rate()
    print(f'Agreement rate (last {WINDOW}): {rate if rate is not None else "n/a"}')
    print(f'Trust student without verifier: {should_trust_student()}')
