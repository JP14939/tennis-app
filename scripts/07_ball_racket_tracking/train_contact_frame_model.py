"""
Trains a regressor that predicts how many frames OFF the geometric
contact-frame heuristic (racket_tracker.find_contact_frame) is, so its guess
can be corrected toward the true contact frame.

Ground truth comes from contact_frame_training_log.jsonl:
  - source='user_submitted' / 'manual_review': heuristic vs a human's mark
  - source='pro_clip_review'  : the original automated pro-DB peak vs Jack's
    corrected contact frame (backfilled by
    backfill_contact_frame_log_from_verdicts.py). Different "student" (the
    swing detector's wrist-velocity peak, not find_contact_frame), flagged
    with a one-hot feature so the model can weight it separately.

Target y = frame_error (signed: teacher_frame - student_frame). At inference
the model predicts an offset to ADD to the heuristic's guess.

Trains directly on logged student_meta -- no clip re-extraction (like
train_shot_contact_model.py, unlike the shot-type classifier). Re-run any
time to pick up new labels.

Usage:  python train_contact_frame_model.py

Output:
  data/07_ball_racket_tracking/contact_frame_model.pkl       (joblib, sklearn Pipeline)
  data/07_ball_racket_tracking/contact_frame_model_meta.json
"""
import json
import os
import re
import sys
import time

import argparse

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import HuberRegressor
from sklearn.model_selection import GroupKFold, KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '00_utils'))
from paths import DATA_DIR  # noqa: E402
from contact_frame_training_log import LOG_PATH, TOLERANCE_FRAMES  # noqa: E402

MODEL_PATH = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'contact_frame_model.pkl')
META_PATH = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'contact_frame_model_meta.json')

FEATURE_NAMES = [
    'student_confidence', 'fps',
    'method_gap', 'method_proximity', 'method_fallback', 'method_wrist_peak',
    'occlusion_gap_frames',
    'n_ball_detections_in_window', 'n_racket_detections_in_window',
    'n_both_present', 'min_ball_racket_dist',
    # wrist kinematics around the anchor (Phase C) -- the hand brakes hard at
    # impact, a signal the speed-peak anchor ignores. From
    # build_contact_student_dataset._wrist_kinematics().
    'wrist_speed_at_anchor', 'wrist_accel_at_anchor', 'wrist_jerk_at_anchor',
    'wrist_decel_offset_f', 'wrist_halfspeed_offset_f',
    # noisier-label one-hot: audio-teacher rows vs. human/user marks.
    'source_audio_teacher',
]

N_FOLDS = 5
MIN_USABLE = 40
# Rows this far off are a frame-reference bug, not a real error the model
# should try to fit. Reported, then dropped.
OUTLIER_FRAMES = 15
# Phase C: the student trains on human marks (Pro Clip Review + user-submitted)
# and audio-teacher labels (build_contact_student_dataset.py). 'manual_review'
# rows carry a frame-reference bug (|error| in the hundreds) -- still excluded.
# 'pro_clip_review' rows were the fixed 1.001s placeholder -- dead, excluded.
TRAIN_SOURCES = {'user_submitted', 'human', 'audio_teacher'}
OCCLUSION_RE = re.compile(r'ball_occlusion_gap\((\d+)f\)')


def features_from_record(record):
    """Shared by training (from a logged row) and inference (from a freshly
    computed row of the same shape). None for any missing signal."""
    meta = record.get('student_meta') or {}
    method = str(record.get('student_method') or '')
    m = OCCLUSION_RE.search(method)
    occlusion = float(m.group(1)) if m else meta.get('occlusion_gap_frames')

    return {
        'student_confidence': record.get('student_confidence'),
        'fps': record.get('fps'),
        'method_gap': 1.0 if method.startswith('ball_occlusion_gap') else 0.0,
        'method_proximity': 1.0 if method == 'ball_racket_proximity' else 0.0,
        'method_fallback': 1.0 if method == 'wrist_velocity_fallback' else 0.0,
        'method_wrist_peak': 1.0 if method == 'swing_detector_wrist_peak' else 0.0,
        'occlusion_gap_frames': occlusion,
        'n_ball_detections_in_window': meta.get('n_ball_detections_in_window'),
        'n_racket_detections_in_window': meta.get('n_racket_detections_in_window'),
        'n_both_present': meta.get('n_both_present'),
        'min_ball_racket_dist': meta.get('min_ball_racket_dist'),
        'wrist_speed_at_anchor': meta.get('wrist_speed_at_anchor'),
        'wrist_accel_at_anchor': meta.get('wrist_accel_at_anchor'),
        'wrist_jerk_at_anchor': meta.get('wrist_jerk_at_anchor'),
        'wrist_decel_offset_f': meta.get('wrist_decel_offset_f'),
        'wrist_halfspeed_offset_f': meta.get('wrist_halfspeed_offset_f'),
        'source_audio_teacher': 1.0 if record.get('source') == 'audio_teacher' else 0.0,
    }


def _to_matrix(rows):
    X = np.full((len(rows), len(FEATURE_NAMES)), np.nan, dtype=float)
    for i, row in enumerate(rows):
        feats = features_from_record(row)
        for j, name in enumerate(FEATURE_NAMES):
            v = feats.get(name)
            if v is not None:
                X[i, j] = float(v)
    y = np.array([float(row['frame_error']) for row in rows])
    return X, y


def build_pipeline(kind='gb'):
    reg = (GradientBoostingRegressor(n_estimators=300, max_depth=3,
                                     learning_rate=0.05, random_state=42)
           if kind == 'gb' else HuberRegressor(max_iter=2000))
    return Pipeline([
        ('impute', SimpleImputer(strategy='median')),
        ('scale', StandardScaler()),
        ('reg', reg),
    ])


def _within(errors, k=TOLERANCE_FRAMES):
    return float(np.mean(np.abs(errors) <= k))


def _group_key(record):
    """One group per source video -- so CV never trains and tests on swings
    from the same compilation (they share crowd noise, lighting, camera)."""
    m = record.get('student_meta') or {}
    sk = m.get('swing_key')            # e.g. 'forehand_2013'
    if sk:
        st, _, sid = sk.rpartition('_')
        try:
            return f'{st}_job{int(sid) // 1000}'
        except ValueError:
            return sk
    return f'{record.get("source")}_{hash(json.dumps(m, sort_keys=True)) % 97}'


def _dist(errors, label):
    a = np.sort(np.abs(errors))
    n = len(a)
    print(f'  {label:<22} n={n:3}  median={np.median(a):.2f}f  p90={a[int(0.9 * (n - 1))]:.2f}f  '
          f'<=1f={_within(errors,1):.0%}  <=2f={_within(errors,2):.0%}  '
          f'<=3f={_within(errors,3):.0%}  <=5f={_within(errors,5):.0%}')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--reg', choices=['gb', 'huber'], default='gb')
    args = ap.parse_args(argv)

    if not os.path.exists(LOG_PATH):
        print(f'No log at {LOG_PATH} -- nothing to train on yet.')
        return

    with open(LOG_PATH) as f:
        records = [json.loads(line) for line in f if line.strip()]
    records = [r for r in records if r.get('frame_error') is not None]

    in_scope = [r for r in records if r.get('source') in TRAIN_SOURCES]
    print(f'{len(records)} rows total, {len(in_scope)} in scope (sources: {sorted(TRAIN_SOURCES)})')

    kept = [r for r in in_scope if abs(r['frame_error']) <= OUTLIER_FRAMES]
    n_outliers = len(in_scope) - len(kept)
    print(f'{n_outliers} dropped as outliers (|error| > {OUTLIER_FRAMES}f)')

    if len(kept) < MIN_USABLE:
        print(f'Only {len(kept)} usable rows (need {MIN_USABLE}) -- too few to train yet.')
        return

    X, y = _to_matrix(kept)
    groups = np.array([_group_key(r) for r in kept])
    by_source = {}
    for r in kept:
        by_source[r.get('source')] = by_source.get(r.get('source'), 0) + 1
    print(f'by source: {by_source}   groups: {len(set(groups))}')
    print(f'target frame_error: mean {y.mean():.2f}, std {y.std():.2f}')

    n_splits = min(N_FOLDS, len(set(groups)))
    cv = (GroupKFold(n_splits=n_splits) if n_splits >= 2
          else KFold(n_splits=2, shuffle=True, random_state=42))
    y_pred = cross_val_predict(build_pipeline(args.reg), X, y, groups=groups, cv=cv)
    residual = y - y_pred  # error remaining after applying the predicted offset

    cv_mae = float(np.mean(np.abs(residual)))
    cv_median_ae = float(np.median(np.abs(residual)))
    cv_within_before = _within(y)
    cv_within_after = _within(residual)
    print(f'\nCV ({n_splits}-fold GroupKFold, {args.reg}):')
    print('  student (find_contact_frame) alone vs teacher:')
    _dist(y, 'raw')
    print('  after applying the model offset:')
    _dist(residual, 'corrected')

    # scoped to the gold human labels only -- the number that actually matters
    hmask = np.array([r.get('source') in ('human', 'user_submitted') for r in kept])
    if hmask.sum() >= 10:
        print('  human-labelled rows only:')
        _dist(y[hmask], 'raw (human)')
        _dist(residual[hmask], 'corrected (human)')

    final = build_pipeline(args.reg)
    final.fit(X, y)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(final, MODEL_PATH)
    meta = {
        'trained_at': time.time(),
        'n_examples': len(kept),
        'n_outliers_dropped': n_outliers,
        'by_source': by_source,
        'feature_names': FEATURE_NAMES,
        'cv_folds': n_splits,
        'cv_mae_frames': round(cv_mae, 3),
        'cv_median_ae_frames': round(cv_median_ae, 3),
        'cv_within_tolerance_before': round(cv_within_before, 4),
        'cv_within_tolerance_after': round(cv_within_after, 4),
        'tolerance_frames': TOLERANCE_FRAMES,
    }
    with open(META_PATH, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f'\nModel saved to {MODEL_PATH}')
    print(f'Metadata saved to {META_PATH}')


# ── Inference ────────────────────────────────────────────────────────────────

_model = None
_model_missing_logged = False


def _get_model():
    global _model, _model_missing_logged
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            if not _model_missing_logged:
                print(f'[contact_frame_model] no trained model at {MODEL_PATH} -- '
                      'run train_contact_frame_model.py', file=sys.stderr)
                _model_missing_logged = True
            return None
        _model = joblib.load(MODEL_PATH)
    return _model


def predict_contact_offset(record):
    """record: same shape as a contact_frame_training_log row (student_method,
    student_confidence, fps, student_meta, ...). Returns (offset_frames:int,
    available:bool). offset is what to ADD to the heuristic's guessed frame."""
    model = _get_model()
    if model is None:
        return 0, False
    feats = features_from_record(record)
    x = np.full((1, len(FEATURE_NAMES)), np.nan, dtype=float)
    for j, name in enumerate(FEATURE_NAMES):
        v = feats.get(name)
        if v is not None:
            x[0, j] = float(v)
    return int(round(float(model.predict(x)[0]))), True


if __name__ == '__main__':
    main()
