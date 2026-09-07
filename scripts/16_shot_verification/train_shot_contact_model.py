"""
Trains a binary "is this really a shot" classifier on top of the geometric
signals verify_shot_contact.py already computes (contact_confidence, which
evidence bucket it landed in, occlusion-gap length, racket speed at
contact/peak) -- the "rules + ML" combination: the rules extract the
signals, this learns how to weigh them instead of the hand-picked
thresholds filter_verified_swings() uses today.

Trains directly on shot_contact_training_log.jsonl's already-logged
student_meta -- no clip re-extraction needed (unlike the shot-type
classifier), since every real verification call already computes and now
logs these signals (see verify_shot_contact_verified.py's _student_meta()).
Works today on the ~1,000 examples already logged (754 real Claude calls +
248 from the amateur-eval backfill); the racket-speed features will just be
mostly missing (median-imputed) for anything logged before this session,
denser going forward. Re-run any time to pick up new labels -- that's the
whole "improves as you label more" mechanism here.

Usage:
  python train_shot_contact_model.py

Output:
  data/16_shot_verification/shot_contact_model.pkl       (joblib, sklearn Pipeline)
  data/16_shot_verification/shot_contact_model_meta.json (training date, CV metrics, feature list)
"""
import json
import os
import re
import sys
import time

import joblib
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support, accuracy_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '00_utils'))
from paths import DATA_DIR  # noqa: E402
from shot_contact_training_log import LOG_PATH, BUCKET_NO_EVIDENCE, BUCKET_PROXIMITY, BUCKET_OCCLUSION_GAP, bucket_for  # noqa: E402

MODEL_PATH = os.path.join(DATA_DIR, '16_shot_verification', 'shot_contact_model.pkl')
META_PATH = os.path.join(DATA_DIR, '16_shot_verification', 'shot_contact_model_meta.json')

FEATURE_NAMES = [
    'contact_confidence', 'bucket_no_evidence', 'bucket_proximity', 'bucket_occlusion_gap',
    'occlusion_gap_frames', 'is_static_hold', 'racket_speed_at_contact', 'racket_peak_speed',
]

N_FOLDS = 5
OCCLUSION_RE = re.compile(r'ball_occlusion_gap\((\d+)f\)')


def features_from_student_meta(meta):
    """Shared by training (from logged student_meta) and inference (from a
    freshly-verified swing's own fields, same shape via
    verify_shot_contact_verified.py's _student_meta()). Returns None for
    any signal that isn't available -- the trained pipeline's imputer fills
    those, same convention extract_training_features.py uses."""
    meta = meta or {}
    raw_method = str(meta.get('contact_method') or '')
    bucket = bucket_for(raw_method)
    m = OCCLUSION_RE.search(raw_method)

    return {
        'contact_confidence': meta.get('contact_confidence'),
        'bucket_no_evidence': 1.0 if bucket == BUCKET_NO_EVIDENCE else 0.0,
        'bucket_proximity': 1.0 if bucket == BUCKET_PROXIMITY else 0.0,
        'bucket_occlusion_gap': 1.0 if bucket == BUCKET_OCCLUSION_GAP else 0.0,
        'occlusion_gap_frames': float(m.group(1)) if m else None,
        'is_static_hold': 1.0 if raw_method.startswith('static_hold(') else 0.0,
        'racket_speed_at_contact': meta.get('racket_speed_at_contact'),
        'racket_peak_speed': meta.get('racket_peak_speed'),
    }


def _to_matrix(rows):
    X = np.full((len(rows), len(FEATURE_NAMES)), np.nan, dtype=float)
    for i, row in enumerate(rows):
        feats = features_from_student_meta(row['student_meta'])
        for j, name in enumerate(FEATURE_NAMES):
            v = feats.get(name)
            if v is not None:
                X[i, j] = float(v)
    y = np.array([bool(row['teacher_pick']) for row in rows])
    return X, y


def build_pipeline():
    return Pipeline([
        ('impute', SimpleImputer(strategy='median')),
        ('scale', StandardScaler()),
        ('clf', LogisticRegression(class_weight='balanced', max_iter=2000)),
    ])


def main():
    if not os.path.exists(LOG_PATH):
        print(f'No log at {LOG_PATH} -- nothing to train on yet.')
        return

    with open(LOG_PATH) as f:
        records = [json.loads(line) for line in f if line.strip()]

    # Only records with a real student_meta.contact_confidence are usable --
    # user_flag corrections have no paired student evidence (student_meta is
    # just {'analysis_id': ...}), so they're real labels but not feature
    # rows for this model (same "unpaired records excluded" reasoning
    # shot_classifier_training_log.py's agreement_rate() already applies).
    rows = [r for r in records if (r.get('student_meta') or {}).get('contact_confidence') is not None]

    if len(rows) < 20:
        print(f'Only {len(rows)} usable examples (need real student_meta.contact_confidence) -- too few to train on yet.')
        return

    X, y = _to_matrix(rows)
    print(f'{len(rows)} examples ({len(records) - len(rows)} skipped -- no paired student evidence), {len(FEATURE_NAMES)} features')
    print('label counts: real_shot =', int(y.sum()), ' not_real_shot =', int((~y).sum()))

    n_splits = min(N_FOLDS, int(min((y == True).sum(), (y == False).sum())))  # noqa: E712
    if n_splits < 2:
        print('Not enough examples of one class to cross-validate -- skipping CV, fitting on all data.')
        cv_accuracy, cv_per_class = None, None
    else:
        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        pipeline = build_pipeline()
        y_pred = cross_val_predict(pipeline, X, y, cv=skf)

        accuracy = accuracy_score(y, y_pred)
        precision, recall, f1, support = precision_recall_fscore_support(
            y, y_pred, labels=[True, False], zero_division=0)

        print(f'\nOverall CV accuracy: {accuracy:.3f} ({n_splits} folds)')
        print(f'{"label":<14} {"precision":>10} {"recall":>8} {"f1":>8} {"n":>4}')
        for i, label in enumerate(['real_shot', 'not_real_shot']):
            print(f'{label:<14} {precision[i]:>10.3f} {recall[i]:>8.3f} {f1[i]:>8.3f} {support[i]:>4}')

        cv_accuracy = round(float(accuracy), 4)
        cv_per_class = {
            label: {'precision': round(float(precision[i]), 4), 'recall': round(float(recall[i]), 4),
                    'f1': round(float(f1[i]), 4), 'n': int(support[i])}
            for i, label in enumerate(['real_shot', 'not_real_shot'])
        }

    final_pipeline = build_pipeline()
    final_pipeline.fit(X, y)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(final_pipeline, MODEL_PATH)

    meta = {
        'trained_at': time.time(),
        'n_examples': len(rows),
        'n_skipped_no_student_evidence': len(records) - len(rows),
        'label_counts': {'real_shot': int(y.sum()), 'not_real_shot': int((~y).sum())},
        'feature_names': FEATURE_NAMES,
        'cv_folds': n_splits if n_splits >= 2 else None,
        'cv_accuracy': cv_accuracy,
        'cv_per_class': cv_per_class,
    }
    with open(META_PATH, 'w') as f:
        json.dump(meta, f, indent=2)

    print(f'\nModel saved to {MODEL_PATH}')
    print(f'Metadata saved to {META_PATH}')


if __name__ == '__main__':
    main()
