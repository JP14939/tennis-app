"""
Training log for the shot-contact teacher-student loop, plus rolling
agreement-rate tracking used to decide when the student
(verify_shot_contact.py's geometric wrist-velocity + racket/ball detector)
is accurate enough to trust without calling the Claude verifier on every
request. Mirrors scripts/14_shot_classifier/shot_classifier_training_log.py's
pattern exactly -- separate log file and separate trust threshold from the
shot-type classifier's, since "is this a real shot" and "what shot is it"
are different competencies with no reason to earn trust at the same rate.

Two label sources feed this log, both real ground truth:
  - 'claude': the vision teacher's verdict (shot_contact_verifier.py).
  - 'user_flag': a real person flagging "not a real shot" in the app
    (frontend "Flag as not a real shot" action) -- arguably more valuable
    than Claude's own opinion, since it's a direct human judgment on their
    own footage, not a model's guess.
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '16_shot_verification', 'shot_contact_training_log.jsonl')

AGREEMENT_THRESHOLD = 0.90
MIN_EXAMPLES_BEFORE_TRUST = 50
WINDOW = 100

# Backtesting the 213 examples logged so far found the student's accuracy
# varies a lot by *what kind* of evidence it found (17-100% depending on
# sub-case, see verify_shot_contact.py's module comment) -- pooling all of
# that into one global agreement_rate() means a noisy bucket permanently
# caps a genuinely reliable one from ever being trusted on its own. These
# three buckets collapse the fine-grained contact_method strings (which
# fragment sample size too thin to trust individually, e.g.
# 'ball_occlusion_gap(3f)' vs '(4f)' vs '(5f)'...) into stable categories
# with enough volume to actually reach MIN_EXAMPLES_BEFORE_TRUST.
BUCKET_NO_EVIDENCE = 'no_evidence'
BUCKET_PROXIMITY = 'proximity'
BUCKET_OCCLUSION_GAP = 'occlusion_gap'


def bucket_for(contact_method):
    """
    Maps a swing's contact_method (from verify_shot_contact.py) to one of
    the three coarse buckets above. Strips the old 'static_hold(...)'
    wrapper (verify_swings() no longer produces it, see that module's
    comment, but old logged examples still have it) so pre- and
    post-fix examples of the same underlying evidence type land in the
    same bucket.
    """
    method = str(contact_method or '')
    if method.startswith('static_hold(') and method.endswith(')'):
        method = method[len('static_hold('):-1]
    if method == 'wrist_velocity_fallback':
        return BUCKET_NO_EVIDENCE
    if method == 'ball_racket_proximity':
        return BUCKET_PROXIMITY
    if method.startswith('ball_occlusion_gap'):
        return BUCKET_OCCLUSION_GAP
    return None  # unrecognized/error method -- never eligible for trust


ALL_BUCKETS = (BUCKET_NO_EVIDENCE, BUCKET_PROXIMITY, BUCKET_OCCLUSION_GAP)


def _wilson_lower_bound(successes, n, z=1.96):
    """
    95%-confidence lower bound on a true proportion given `successes` out
    of `n` observed trials -- deliberately more conservative than the raw
    successes/n point estimate, which a small sample can push arbitrarily
    high by luck (several contact_method sub-buckets showed 100% on
    N=1-3 in the logged data, which is noise, not a trustworthy signal).
    Standard Wilson score interval; returns 0.0 for n == 0.
    """
    if n == 0:
        return 0.0
    p_hat = successes / n
    denom = 1 + z * z / n
    center = p_hat + z * z / (2 * n)
    adjustment = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n)
    return (center - adjustment) / denom


def log_example(student_pick, teacher_pick, agreed, source='claude', student_meta=None, lock=None,
                 clip_path=None, contact_frame=None):
    """
    Append one training example. `student_pick`/`teacher_pick` are booleans
    (True = real shot). `student_meta` is the student's full
    contact_confidence/contact_method dict -- the input a future trained
    model would learn from. `source`: 'claude' or 'user_flag' (see module
    docstring).

    clip_path/contact_frame: optional, same reasoning as
    shot_classifier_training_log.py's identical fields -- lets this record
    be traced back to its source clip later (debugging, or a future
    from-scratch feature re-extraction), even though train_shot_contact_model.py
    doesn't need them itself (it trains on student_meta's already-computed
    signals directly, no re-extraction required). Defaulted to None so
    every existing caller/record is unaffected.

    lock: optional multiprocessing.Lock (or any context-manager-compatible
    lock) -- same reasoning as shot_classifier_training_log.py's: needed
    when multiple worker processes can call this concurrently (the batch
    pipeline), a plain `open(...,'a')` append is not guaranteed atomic
    across processes on every platform. Defaults to None (no locking),
    safe for single-process/single-request callers (e.g. a user's flag
    action arriving through the Node backend).
    """
    record = {
        'timestamp': time.time(),
        'student_pick': student_pick,
        'teacher_pick': teacher_pick,
        'agreed': agreed,
        'source': source,
        'student_meta': student_meta,
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


def _current_student_pick(record_bucket):
    """
    What TODAY's student logic (verify_shot_contact.filter_verified_swings)
    would predict for a swing in this bucket -- purely a function of the
    bucket, since that filter is now just "reject no_evidence, keep
    everything else" (see that module's comment for why the old
    speed-ratio-based static_hold rejection was removed). Returns None for
    an unrecognized bucket (never counted as a pairable example).
    """
    if record_bucket == BUCKET_NO_EVIDENCE:
        return False
    if record_bucket in (BUCKET_PROXIMITY, BUCKET_OCCLUSION_GAP):
        return True
    return None


def _paired_records(bucket=None):
    """
    Logged examples with a real teacher verdict to compare against,
    re-scored against TODAY's student policy rather than trusting each
    record's stored `agreed` field -- that field was computed against
    whatever the student logic was *at logging time*, which for most of
    the 213 examples collected so far predates the static_hold fix (see
    verify_shot_contact.py). Re-deriving `agreed` from `teacher_pick` +
    bucket means every logged example (including ones from before this
    fix) is immediately valid evidence for the current policy, and stays
    correct automatically if the student logic changes again later --
    without this, old logged "agreement" would understate how good today's
    student actually is, exactly the discrepancy found when backtesting
    this fix in conversation before writing it.
    """
    out = []
    for r in read_log():
        if r.get('teacher_pick') is None:
            continue
        b = bucket_for((r.get('student_meta') or {}).get('contact_method'))
        if bucket is not None and b != bucket:
            continue
        pick = _current_student_pick(b)
        if pick is None:
            continue
        out.append({**r, 'agreed': pick == r['teacher_pick']})
    return out


def agreement_rate(window=WINDOW, bucket=None):
    """
    Fraction of the last `window` logged examples where student == teacher.
    Only counts records with a real student/teacher pairing (`agreed` is
    not None) -- a bare user flag (source='user_flag') has no paired
    student prediction at flag time, so it's stored as real training data
    but excluded from this trust calculation rather than silently counted
    as a disagreement and deflating the rate.

    bucket: when given, scopes to one of ALL_BUCKETS (see bucket_for()) --
    the window is applied *after* filtering to that bucket, so it's still
    "the last 100 examples of this evidence type," not "the last 100
    examples overall, some of which happen to be this type."
    """
    records = _paired_records(bucket)[-window:]
    if not records:
        return None
    return sum(1 for r in records if r['agreed']) / len(records)


def should_trust_student():
    """
    Global, unscoped trust check -- kept for backward-compatible callers
    and reporting. get_verified_shot_contact() no longer uses this as its
    gate (see should_trust_bucket()); pooling every evidence type together
    means one noisy bucket can permanently mask a reliable one.
    """
    paired = _paired_records()
    if len(paired) < MIN_EXAMPLES_BEFORE_TRUST:
        return False
    rate = agreement_rate()
    return rate is not None and rate >= AGREEMENT_THRESHOLD


def should_trust_bucket(bucket):
    """
    Whether this specific evidence-type bucket is accurate enough to skip
    calling Claude for swings whose contact_method falls in it. Requires
    both a minimum sample size *in that bucket* and the Wilson-lower-bound
    (not the raw point estimate -- see _wilson_lower_bound()) of its
    agreement rate to clear AGREEMENT_THRESHOLD. Other buckets are
    unaffected either way -- each earns trust independently.
    """
    if bucket not in ALL_BUCKETS:
        return False
    records = _paired_records(bucket)[-WINDOW:]
    if len(records) < MIN_EXAMPLES_BEFORE_TRUST:
        return False
    successes = sum(1 for r in records if r['agreed'])
    return _wilson_lower_bound(successes, len(records)) >= AGREEMENT_THRESHOLD


if __name__ == '__main__':
    records = read_log()
    print(f'{len(records)} logged examples')
    rate = agreement_rate()
    print(f'Agreement rate (last {WINDOW}, all buckets pooled): {rate if rate is not None else "n/a"}')
    print(f'Trust student without verifier (global, informational only): {should_trust_student()}')
    by_source = {}
    for r in records:
        by_source[r['source']] = by_source.get(r['source'], 0) + 1
    print(f'By source: {by_source}')

    print('\nPer-bucket breakdown (this is what get_verified_shot_contact() actually gates on):')
    for bucket in ALL_BUCKETS:
        paired = _paired_records(bucket)
        n = len(paired)
        rate = agreement_rate(bucket=bucket)
        trusted = should_trust_bucket(bucket)
        rate_str = f'{rate:.1%}' if rate is not None else 'n/a'
        lb_str = ''
        if n:
            successes = sum(1 for r in paired[-WINDOW:] if r['agreed'])
            lb = _wilson_lower_bound(successes, min(n, WINDOW))
            lb_str = f' (Wilson lower bound: {lb:.1%})'
        print(f'  {bucket}: N={n}, agreement={rate_str}{lb_str}, trusted={trusted}')
