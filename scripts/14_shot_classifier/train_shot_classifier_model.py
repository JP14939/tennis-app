"""
Trains a shot-type (forehand/backhand/serve) classifier on the rich
pose-derived features extract_training_features.py produces from the 116
real-shot-labeled amateur clips.

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
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '00_utils'))
from paths import DATA_DIR  # noqa: E402
from extract_training_features import FEATURE_NAMES  # noqa: E402

FEATURES_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'training_features.json')
MODEL_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_model.pkl')
META_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_model_meta.json')

N_FOLDS = 5  # 10 backhand examples / 5 folds = 2 per fold -- every fold sees real backhand data
CLASSES = ['forehand', 'backhand', 'serve']


def _to_matrix(rows):
    """features dict (with Nones) -> (N, len(FEATURE_NAMES)) float matrix,
    booleans cast to 0.0/1.0, None left as np.nan for the imputer to fill."""
    X = np.full((len(rows), len(FEATURE_NAMES)), np.nan, dtype=float)
    for i, row in enumerate(rows):
        for j, name in enumerate(FEATURE_NAMES):
            v = row['features'].get(name)
            if v is None:
                continue
            X[i, j] = float(v)
    y = np.array([row['label'] for row in rows])
    return X, y


def build_pipeline():
    return Pipeline([
        ('impute', SimpleImputer(strategy='median')),
        ('scale', StandardScaler()),
        # multi_class param removed in sklearn 1.9 -- lbfgs (the default
        # solver) now always fits a true multinomial model for >2 classes.
        ('clf', LogisticRegression(class_weight='balanced', max_iter=2000)),
    ])


def main():
    with open(FEATURES_PATH) as f:
        rows = json.load(f)
    X, y = _to_matrix(rows)
    print(f'{len(rows)} examples, {len(FEATURE_NAMES)} features')
    print('class counts:', {c: int((y == c).sum()) for c in CLASSES})

    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
    pipeline = build_pipeline()

    # cross_val_predict trains N_FOLDS separate models (one per fold, each
    # fold held out from its own training) and stitches together an
    # out-of-fold prediction for every example -- every prediction below
    # is on data that model never trained on, unlike checking accuracy on
    # the same data used to fit the final model.
    y_pred = cross_val_predict(pipeline, X, y, cv=skf)

    accuracy = accuracy_score(y, y_pred)
    precision, recall, f1, support = precision_recall_fscore_support(
        y, y_pred, labels=CLASSES, zero_division=0)

    print(f'\nOverall CV accuracy: {accuracy:.3f}')
    print(f'{"class":<10} {"precision":>10} {"recall":>8} {"f1":>8} {"n":>4}')
    for i, c in enumerate(CLASSES):
        print(f'{c:<10} {precision[i]:>10.3f} {recall[i]:>8.3f} {f1[i]:>8.3f} {support[i]:>4}')

    # Fit the FINAL model on all 116 examples (the CV loop above was only
    # for honest evaluation -- none of those 5 fold-models are kept).
    final_pipeline = build_pipeline()
    final_pipeline.fit(X, y)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(final_pipeline, MODEL_PATH)

    meta = {
        'trained_at': time.time(),
        'n_examples': len(rows),
        'class_counts': {c: int((y == c).sum()) for c in CLASSES},
        'feature_names': FEATURE_NAMES,
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
