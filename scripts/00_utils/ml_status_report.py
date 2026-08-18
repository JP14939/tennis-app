"""
One JSON summary of all three teacher-student ML loops' current reliability,
for the hidden Dev Page (backend/src/routes/dev.js's GET /dev/ml-status).
Imports each loop's own training-log module directly rather than
reimplementing its math -- this script is just a reporter, not a second
source of truth.

Usage:
  python ml_status_report.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '16_shot_verification'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '14_shot_classifier'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '09_coaching_ai'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '07_ball_racket_tracking'))

import shot_contact_training_log as contact  # noqa: E402
import shot_classifier_training_log as classifier  # noqa: E402
import tip_training_log as tips  # noqa: E402
import contact_frame_training_log as contact_frame  # noqa: E402


def shot_contact_status():
    records = contact.read_log()
    by_source = {}
    for r in records:
        by_source[r['source']] = by_source.get(r['source'], 0) + 1

    buckets = {}
    for bucket in contact.ALL_BUCKETS:
        paired = contact._paired_records(bucket)  # noqa: SLF001 -- reporter mirrors this module's own __main__ block
        n = len(paired)
        rate = contact.agreement_rate(bucket=bucket)
        wilson_lower_bound = None
        if n:
            successes = sum(1 for r in paired[-contact.WINDOW:] if r['agreed'])
            wilson_lower_bound = round(contact._wilson_lower_bound(successes, min(n, contact.WINDOW)), 4)  # noqa: SLF001
        buckets[bucket] = {
            'n': n,
            'agreement_rate': round(rate, 4) if rate is not None else None,
            'wilson_lower_bound': wilson_lower_bound,
            'trusted': contact.should_trust_bucket(bucket),
        }

    return {
        'total_examples': len(records),
        'by_source': by_source,
        'pooled_agreement_rate': round(contact.agreement_rate(), 4) if contact.agreement_rate() is not None else None,
        'buckets': buckets,
        'thresholds': {
            'min_examples_before_trust': contact.MIN_EXAMPLES_BEFORE_TRUST,
            'agreement_threshold': contact.AGREEMENT_THRESHOLD,
            'window': contact.WINDOW,
        },
    }


def shot_classifier_status():
    records = classifier.read_log()
    rate = classifier.agreement_rate()
    return {
        'total_examples': len(records),
        'agreement_rate': round(rate, 4) if rate is not None else None,
        'trusted': classifier.should_trust_student(),
        'thresholds': {
            'min_examples_before_trust': classifier.MIN_EXAMPLES_BEFORE_TRUST,
            'agreement_threshold': classifier.AGREEMENT_THRESHOLD,
            'window': classifier.WINDOW,
        },
    }


def tip_selector_status():
    records = tips.read_log()
    by_shot_type = {}
    for r in records:
        shot_type = r.get('shot_type') or 'unknown'
        by_shot_type[shot_type] = by_shot_type.get(shot_type, 0) + 1

    rate = tips.agreement_rate()
    return {
        'total_examples': len(records),
        'agreement_rate': round(rate, 4) if rate is not None else None,
        'trusted': tips.should_trust_student(),
        'by_shot_type': by_shot_type,
        'thresholds': {
            'min_examples_before_trust': tips.MIN_EXAMPLES_BEFORE_TRUST,
            'agreement_threshold': tips.AGREEMENT_THRESHOLD,
            'window': tips.WINDOW,
        },
    }


def contact_frame_status():
    all_records = contact_frame.read_log()
    overall = contact_frame.stats()
    by_source = {
        src: contact_frame.stats(source=src)
        for src in ('manual_review', 'user_submitted')
    }
    return {
        'total_examples': len(all_records),
        'overall': overall,
        'by_source': by_source,
        'thresholds': {
            'tolerance_frames': contact_frame.TOLERANCE_FRAMES,
            'min_examples_before_trust': contact_frame.MIN_EXAMPLES_BEFORE_TRUST,
            'within_tolerance_threshold': contact_frame.WITHIN_TOLERANCE_THRESHOLD,
            'window': contact_frame.WINDOW,
        },
    }


def main():
    print(json.dumps({
        'shot_contact': shot_contact_status(),
        'shot_classifier': shot_classifier_status(),
        'tip_selector': tip_selector_status(),
        'contact_frame': contact_frame_status(),
    }))


if __name__ == '__main__':
    main()
