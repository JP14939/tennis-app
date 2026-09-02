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
import shot_contact_verifier  # noqa: E402
import shot_classifier_training_log as classifier  # noqa: E402
import shot_classifier_ml_training_log as classifier_ml  # noqa: E402
import shot_classifier_verifier  # noqa: E402
import tip_training_log as tips  # noqa: E402
import contact_frame_training_log as contact_frame  # noqa: E402
import contact_frame_ml_training_log as contact_frame_ml  # noqa: E402

# Read the model + its meta by path rather than importing
# train_contact_frame_model (which pulls in sklearn at import) -- this
# reporter runs behind a 30s Dev-route timeout.
_CF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..',
                       'data', '07_ball_racket_tracking')
CONTACT_FRAME_MODEL_PATH = os.path.join(_CF_DIR, 'contact_frame_model.pkl')
CONTACT_FRAME_META_PATH = os.path.join(_CF_DIR, 'contact_frame_model_meta.json')


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
        # This is the verifier that actually fires in the real
        # detect_rallies.py pipeline (its combined call usually answers
        # shot-type too, short-circuiting a separate classifier-verifier
        # call -- see shot_classifier_ml's own verifier_cost note). Real
        # money, confirmed live 2026-08-19.
        'verifier_cost': shot_contact_verifier.cost_summary(),
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


def shot_classifier_ml_status():
    """
    Trust status for the trained ML shot-classifier (classify_shot.
    classify_ml(), see train_shot_classifier_model.py) -- a SEPARATE trust
    gate from shot_classifier_status() above (the rule-based one), so the
    ML model earns trust independently rather than inheriting the
    rule-based classifier's poor ~38% agreement rate. Also surfaces
    shot_classifier_verifier.py's own call cost (single-frame classifier
    verifier) -- confirmed live 2026-08-19 that this verifier RARELY
    actually fires in the real detect_rallies.py pipeline, because
    shot_contact_verifier.py's combined call usually already answers
    shot_type first (see that module's own verifier_cost, surfaced under
    shot_contact above -- THAT one is the real cost driver in practice).
    """
    records = classifier_ml.read_log()
    rate = classifier_ml.agreement_rate()
    return {
        'total_examples': len(records),
        'agreement_rate': round(rate, 4) if rate is not None else None,
        'trusted': classifier_ml.should_trust_student(),
        'thresholds': {
            'min_examples_before_trust': classifier_ml.MIN_EXAMPLES_BEFORE_TRUST,
            'agreement_threshold': classifier_ml.AGREEMENT_THRESHOLD,
            'window': classifier_ml.WINDOW,
        },
        'verifier_cost': shot_classifier_verifier.cost_summary(),
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
        for src in ('manual_review', 'user_submitted', 'pro_clip_review')
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


def contact_frame_ml_status():
    """Trust status for the trained contact-frame corrector
    (train_contact_frame_model.predict_contact_offset()) -- a SEPARATE gate
    from contact_frame_status() above (the heuristic), so the model earns
    trust independently. Reports CV metrics from the model's meta file so
    the Dev screen can show whether it actually beats the heuristic."""
    model_present = os.path.exists(CONTACT_FRAME_MODEL_PATH)
    model_meta = None
    if os.path.exists(CONTACT_FRAME_META_PATH):
        with open(CONTACT_FRAME_META_PATH) as f:
            model_meta = json.load(f)
    return {
        'model_present': model_present,
        'model_meta': model_meta,
        'trust_log': contact_frame_ml.stats(),
        'total_examples': len(contact_frame_ml.read_log()),
        'thresholds': {
            'tolerance_frames': contact_frame_ml.TOLERANCE_FRAMES,
            'min_examples_before_trust': contact_frame_ml.MIN_EXAMPLES_BEFORE_TRUST,
            'within_tolerance_threshold': contact_frame_ml.WITHIN_TOLERANCE_THRESHOLD,
            'window': contact_frame_ml.WINDOW,
        },
    }


def main():
    print(json.dumps({
        'shot_contact': shot_contact_status(),
        'shot_classifier': shot_classifier_status(),
        'shot_classifier_ml': shot_classifier_ml_status(),
        'tip_selector': tip_selector_status(),
        'contact_frame': contact_frame_status(),
        'contact_frame_ml': contact_frame_ml_status(),
    }))


if __name__ == '__main__':
    main()
