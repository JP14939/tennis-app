"""
Trains a shot-type (forehand/backhand/serve) classifier on the rich
pose-derived features extract_training_features.py produces from the 116
real-shot-labeled amateur clips, PLUS whatever extract_training_features_
from_log.py has re-extracted from real logged Claude verdicts since it was
last run (data/14_shot_classifier/training_features_from_log.json -- run
that script first to pick up anything new; this trainer just concatenates
both files if the log-derived one exists, and works fine on the amateur set
alone if it doesn't). This is the whole "improves as more gets labeled"
mechanism -- re-run the extractor then this trainer any time.

Multinomial logistic regression, not a tree/boosted model -- chosen for
N=116 with a severely imbalanced backhand class (10 examples): lower
variance, much less prone to memorizing the smallest class, and still
fully interpretable (unlike the rule-based scorer's hand-picked weights,
these are at least LEARNED from real data). class_weight='balanced' so
the 10 backhand examples aren't drowned out by 57 serve/49 forehand ones.

Missing landmarks (see extract_training_features.py's None-for-missing
convention) are median-imputed, not dropped -- 56 of 116 rows have at
least one None feature (mostly the left wrist, often out of frame/occluded
in real amateur footage), and this dataset is too small to throw half of
it away.

Validated with STRATIFIED K-fold cross-validation, not a single train/test
split -- a single split could leave a fold with zero backhand examples
(only 10 total). Reports per-class precision/recall/F1, not just overall
accuracy, since accuracy alone would hide how badly the smallest class is
doing -- the same mistake a raw rule-based score would make.

Usage:
  python train_shot_classifier_model.py

Output:
  data/14_shot_classifier/shot_classifier_model.pkl       (joblib, sklearn Pipeline)
  data/14_shot_classifier/shot_classifier_model_meta.json (training date, CV metrics, feature list)
"""
import json
import os
import sys
import time

import joblib
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support, accuracy_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '00_utils'))
from paths import DATA_DIR  # noqa: E402
from extract_training_features import FEATURE_NAMES, FEATURE_VERSION  # noqa: E402

FEATURES_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'training_features.json')
LOG_FEATURES_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'training_features_from_log.json')
# Jack-verified pro BROADCAST clips (extract_training_features_from_pro_verdicts.py).
# TESTED 2026-08-27 and NOT USED: evaluated honestly (train on amateur + pro, score
# ONLY on held-out amateur rows) at weights 0.15-1.0 and with backhand-only / relabel-only
# subsets -- every configuration made the amateur backhand F1 WORSE (0.30 -> 0.12-0.21),
# not better. The apparent "backhand +0.13" in a naive combined CV was the model learning
# to classify *pro* backhands. Broadcast framing (player fills less of the frame) shifts
# the raw-magnitude features too far from phone footage. Kept the extractor + this file
# path for a possible future pro-specific model; the amateur trainer ignores it.
PRO_FEATURES_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'training_features_from_pro.json')
# D.4 (2026-09-02): re-evaluating with body-normalised features (FEATURE_VERSION
# v2-bodynorm) -- the 2026-08-27 rejection was raw image-space magnitudes.
# Overridable from the CLI (--use-pro / --pro-weight) for the D.3 comparison.
USE_PRO_FEATURES = False
PRO_WEIGHT = 0.25

MODEL_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_model.pkl')
META_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_model_meta.json')

N_FOLDS = 5  # 10 backhand examples / 5 folds = 2 per fold -- every fold sees real backhand data
CLASSES = ['forehand', 'backhand', 'serve']


def _to_matrix(rows):
    """features dict (with Nones) -> (N, len(FEATURE_NAMES)) float matrix,
    booleans cast to 0.0/1.0, None left as np.nan for the imputer to fill.
    Also returns per-row sample weights (PRO_WEIGHT for pro-review rows)."""
    X = np.full((len(rows), len(FEATURE_NAMES)), np.nan, dtype=float)
    for i, row in enumerate(rows):
        for j, name in enumerate(FEATURE_NAMES):
            v = row['features'].get(name)
            if v is None:
                continue
            X[i, j] = float(v)
    y = np.array([row['label'] for row in rows])
    w = np.array([PRO_WEIGHT if row.get('source') == 'pro_review' else 1.0 for row in rows])
    return X, y, w


def build_pipeline():
    return Pipeline([
        ('impute', SimpleImputer(strategy='median')),
        ('scale', StandardScaler()),
        # multi_class param removed in sklearn 1.9 -- lbfgs (the default
        # solver) now always fits a true multinomial model for >2 classes.
        ('clf', LogisticRegression(class_weight='balanced', max_iter=2000)),
    ])


def _per_class(y_true, y_hat, tag):
    acc = accuracy_score(y_true, y_hat)
    p, r, f, s = precision_recall_fscore_support(y_true, y_hat, labels=CLASSES, zero_division=0)
    print(f'\n{tag}  (accuracy {acc:.3f})')
    print(f'  {"class":<10} {"precision":>10} {"recall":>8} {"f1":>8} {"n":>4}')
    for i, c in enumerate(CLASSES):
        print(f'  {c:<10} {p[i]:>10.3f} {r[i]:>8.3f} {f[i]:>8.3f} {s[i]:>4}')
    return acc, {c: {'precision': round(float(p[i]), 4), 'recall': round(float(r[i]), 4),
                     'f1': round(float(f[i]), 4), 'n': int(s[i])} for i, c in enumerate(CLASSES)}


def main():
    global USE_PRO_FEATURES, PRO_WEIGHT
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--use-pro', action='store_true')
    ap.add_argument('--pro-weight', type=float, default=PRO_WEIGHT)
    ap.add_argument('--no-log', action='store_true',
                    help='skip training_features_from_log.json (serve-contaminated: 73 serve / 1 backhand)')
    ap.add_argument('--dry-run', action='store_true', help='report CV only, do not overwrite the model')
    args = ap.parse_args()
    if args.use_pro:
        USE_PRO_FEATURES = True
    PRO_WEIGHT = args.pro_weight

    with open(FEATURES_PATH) as f:
        rows = json.load(f)
    for row in rows:
        row.setdefault('source', 'amateur')
    n_amateur = len(rows)

    n_log = 0
    if not args.no_log and os.path.exists(LOG_FEATURES_PATH):
        with open(LOG_FEATURES_PATH) as f:
            log_rows = json.load(f)
        for row in log_rows:
            row.setdefault('source', 'log')
        rows = rows + log_rows
        n_log = len(log_rows)

    n_pro = 0
    if USE_PRO_FEATURES and os.path.exists(PRO_FEATURES_PATH):
        with open(PRO_FEATURES_PATH) as f:
            pro_rows = json.load(f)
        rows = rows + pro_rows
        n_pro = len(pro_rows)

    X, y, w = _to_matrix(rows)
    is_amateur = np.array([r.get('source') == 'amateur' for r in rows])
    print(f'{len(rows)} examples ({n_amateur} amateur-eval + {n_log} log-derived + '
          f'{n_pro} pro-review @ weight {PRO_WEIGHT}), {len(FEATURE_NAMES)} features')
    print('class counts:', {c: int((y == c).sum()) for c in CLASSES})

    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)

    # Manual weighted CV loop -- each fold-model sees the pro-review
    # down-weighting during fit, so reported per-class F1 reflects the model
    # that ships. Every prediction is out-of-fold.
    y_pred = np.empty_like(y)
    for tr, te in skf.split(X, y):
        fold = build_pipeline()
        fold.fit(X[tr], y[tr], clf__sample_weight=w[tr])
        y_pred[te] = fold.predict(X[te])

    accuracy, cv_per_class = _per_class(y, y_pred, 'CV over the whole pool')

    # The regression guard: score ONLY the held-out amateur rows. Adding pro
    # data can flatter a naive combined CV (the model learns to classify pro
    # backhands) while hurting the real target -- see the 2026-08-27 note.
    if is_amateur.sum() >= N_FOLDS:
        _per_class(y[is_amateur], y_pred[is_amateur], 'held-out AMATEUR rows only')
    precision, recall, f1, support = precision_recall_fscore_support(
        y, y_pred, labels=CLASSES, zero_division=0)

    if args.dry_run:
        print('\n--dry-run: model NOT saved.')
        return

    # Fit the FINAL model on all examples (the CV loop above was only for
    # honest evaluation -- none of those 5 fold-models are kept).
    final_pipeline = build_pipeline()
    final_pipeline.fit(X, y, clf__sample_weight=w)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(final_pipeline, MODEL_PATH)

    meta = {
        'trained_at': time.time(),
        'n_examples': len(rows),
        'n_amateur': n_amateur,
        'n_log_derived': n_log,
        'n_pro_review': n_pro,
        'pro_sample_weight': PRO_WEIGHT,
        'class_counts': {c: int((y == c).sum()) for c in CLASSES},
        'feature_names': FEATURE_NAMES,
        'feature_version': FEATURE_VERSION,
        'cv_folds': N_FOLDS,
        'cv_accuracy': round(float(accuracy), 4),
        'cv_per_class': {
            c: {'precision': round(float(precision[i]), 4), 'recall': round(float(recall[i]), 4),
                'f1': round(float(f1[i]), 4), 'n': int(support[i])}
            for i, c in enumerate(CLASSES)
        },
    }
    with open(META_PATH, 'w') as f:
        json.dump(meta, f, indent=2)

    print(f'\nModel saved to {MODEL_PATH}')
    print(f'Metadata saved to {META_PATH}')


if __name__ == '__main__':
    main()
