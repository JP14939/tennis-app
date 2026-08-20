"""
Training log for the shot-classifier teacher-student loop, plus rolling
agreement-rate tracking used to decide when the student (classify_shot.py's
rule-based classify()) is accurate enough to trust without calling the
Claude verifier on every request. Mirrors
scripts/09_coaching_ai/tip_training_log.py's pattern exactly.

Two label sources feed this log: 'claude' (the vision teacher's verdict,
paired against the student's own pick, agreed set) and 'user_flag' (a real
person correcting the shot type in the app -- no paired student prediction
at correction time, so agreed=None, same shape/reasoning as
scripts/16_shot_verification/shot_contact_training_log.py's user_flag
entries). See that module's agreement_rate()/should_trust_student() for why
unpaired records must be excluded from the trust math rather than silently
counted as a disagreement and deflating the rate -- same fix applied here.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_training_log.jsonl')

AGREEMENT_THRESHOLD = 0.90
MIN_EXAMPLES_BEFORE_TRUST = 50
WINDOW = 100


def log_example(scores, student_pick, claude_pick, agreed, lock=None, clip_path=None, contact_frame=None):
    """
    Append one training example. `scores` is the student's full
    {'forehand': x, 'backhand': y, 'serve': z} confidence dict -- the input
    a future trained model would learn from; student/claude picks are the
    labels.

    clip_path/contact_frame: optional -- when the caller has them (every
    real call site does), stored alongside the scores so this record can
    later be re-extracted into a richer feature vector (see
    extract_training_features.py), the same way the amateur eval dataset's
    manifest.json lets its swings be re-extracted. Every record logged
    before this was added lacks these fields entirely (no clip reference
    was ever kept) and can't be backfilled -- optional/defaulted to None
    so old callers and old records both still work.

    lock: optional multiprocessing.Lock (or any context-manager-compatible
    lock). When multiple worker processes can call this concurrently
    (analyze_rallies.py's parallel pipeline), pass one in to serialize the
    append and avoid interleaved/corrupted lines -- a plain `open(...,'a')`
    append is not guaranteed atomic across processes on every platform.
    Defaults to None (no locking) so single-process callers are unaffected.
    """
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
    """
    Fraction of the last `window` logged examples where student == claude.
    Only counts records with a real student/claude pairing (`agreed` is not
    None) -- a bare user_flag correction has no paired student prediction
    at correction time, so it's stored as real training data but excluded
    from this trust calculation rather than silently counted as a
    disagreement and deflating the rate.
    """
    records = [r for r in read_log() if r.get('agreed') is not None][-window:]
    if not records:
        return None
    return sum(1 for r in records if r['agreed']) / len(records)


def should_trust_student():
    """
    Whether the student is accurate enough to skip calling Claude. Requires
    both a minimum sample size (don't trust a lucky streak) and a sustained
    agreement rate above AGREEMENT_THRESHOLD. Only counts paired
    (student vs. claude) records toward the minimum -- see agreement_rate().
    """
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
    print(f'Trust student without verifier: {should_trust_student()}')
