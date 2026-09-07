"""
Phase A.2 -- train a classifier that picks the ball-contact onset out of the
~30 audio onsets a clip produces.

Phase A (eval_audio_contact.py) showed the correct onset is in the detected
list ~99% of the time within +-5f, but "loudest wins" only gets it right ~65%.
This scores every onset on how impact-like it sounds AND how well it agrees
with the video (wrist-speed peak / pose contact estimate), then picks the best.

Inputs (both must already exist):
  data/07_ball_racket_tracking/eval_audio_contact.csv      (onsets per clip)
  data/07_ball_racket_tracking/eval_pro_clip_contact.csv   (pose hints per clip)
  data/07_ball_racket_tracking/.audio_cache/*.wav          (from eval_audio_contact.py)

Output:
  data/07_ball_racket_tracking/onset_classifier.pkl
  data/07_ball_racket_tracking/onset_classifier_meta.json

Usage:  python train_onset_classifier.py [--model gb|rf|logreg]
"""
import argparse
import csv
import json
import os
import statistics
import sys

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score, precision_score, recall_score

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '00_utils'))

from paths import DATA_DIR  # noqa: E402
from audio_onset import (  # noqa: E402
    onset_features, ONSET_FEATURE_NAMES, AUDIO_ONLY_FEATURE_NAMES,
    ONSET_BIAS_F, HIGHPASS_HZ_DEFAULT, REPORT_FPS,
)

_D = os.path.join(DATA_DIR, '07_ball_racket_tracking')
AUDIO_CACHE = os.path.join(_D, '.audio_cache')
AUDIO_CSV = os.path.join(_D, 'eval_audio_contact.csv')
POSE_CSV = os.path.join(_D, 'eval_pro_clip_contact.csv')

POS_TOL_F = 4.0   # an onset within this many frames of the human mark = "the contact"

# Set in main() -- the feature columns and output paths depend on --audio-only.
FEATURES = ONSET_FEATURE_NAMES
MODEL_PATH = os.path.join(_D, 'onset_classifier.pkl')
META_PATH = os.path.join(_D, 'onset_classifier_meta.json')
CONF_PROBA, CONF_MARGIN = 0.60, 0.20


def _rows(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_dataset():
    audio = {r['id']: r for r in _rows(AUDIO_CSV) if not r['error']}
    pose = {r['id']: r for r in _rows(POSE_CSV) if not r['error']}

    X, y, groups, meta_rows = [], [], [], []
    clips = []
    skipped_no_wav = skipped_no_pos = 0

    for eid, ar in sorted(audio.items()):
        orig_st, sid = ar['orig_shot_type'], ar['swing_id']
        if not orig_st or not sid:
            continue
        wav = os.path.join(AUDIO_CACHE, f'{orig_st}_{sid}_{HIGHPASS_HZ_DEFAULT:.0f}.wav')
        if not os.path.exists(wav):
            skipped_no_wav += 1
            continue

        teacher = _f(ar['teacher_time'])
        pr = pose.get(eid, {})
        fps = _f(pr.get('fps')) or REPORT_FPS
        hints = {}
        af = _f(pr.get('anchor_frame'))
        if af is not None:
            hints['wrist_peak_sec'] = af / fps
        pp = _f(pr.get('pred_time_heuristic'))
        if pp is not None:
            hints['pose_pred_sec'] = pp
        method = pr.get('method') or ''
        if method.startswith('ball_occlusion_gap'):
            pf = _f(pr.get('pred_frame_heuristic'))
            if pf is not None:
                hints['occlusion_gap_sec'] = pf / fps
        nb = _f(pr.get('n_ball_in_window'))
        if nb is not None:
            hints['n_ball'] = nb

        feats = onset_features(wav, HIGHPASS_HZ_DEFAULT, hints)
        if not feats:
            continue

        # label: the onset closest to the human mark, if within POS_TOL_F frames
        def err_f(ot):
            return abs((ot - ONSET_BIAS_F / fps - teacher) * fps)
        best_i = min(range(len(feats)), key=lambda i: err_f(feats[i][0]))
        recoverable = err_f(feats[best_i][0]) <= POS_TOL_F
        if not recoverable:
            skipped_no_pos += 1

        clip_onsets = []
        for i, (ot, ostr, fd) in enumerate(feats):
            row = [fd.get(n, np.nan) for n in FEATURES]
            label = 1 if (recoverable and i == best_i) else 0
            if recoverable:
                X.append(row)
                y.append(label)
                groups.append(eid)
                meta_rows.append({'id': eid, 'fps': fps, 'teacher': teacher,
                                  'onset_t': ot, 'label': label})
            clip_onsets.append({'onset_t': ot, 'feat_row': row})
        clips.append({'id': eid, 'fps': fps, 'teacher': teacher,
                      'onsets': clip_onsets, 'recoverable': recoverable})

    print(f'clips: {len(clips)}  |  training onsets: {len(X)} '
          f'({sum(y)} pos / {len(y) - sum(y)} neg)  |  '
          f'skipped: {skipped_no_wav} no-wav, {skipped_no_pos} unrecoverable', file=sys.stderr)
    return (np.array(X, float), np.array(y), np.array(groups), meta_rows, clips)


def make_model(kind):
    if kind == 'rf':
        clf = RandomForestClassifier(n_estimators=400, max_depth=6,
                                     class_weight='balanced', random_state=0, n_jobs=-1)
    elif kind == 'logreg':
        clf = LogisticRegression(max_iter=1000, class_weight='balanced')
    else:
        clf = GradientBoostingClassifier(n_estimators=300, max_depth=3,
                                         learning_rate=0.05, random_state=0)
    return Pipeline([
        ('impute', SimpleImputer(strategy='median')),
        ('scale', StandardScaler()),
        ('clf', clf),
    ])


def summarise(errs, label):
    a = sorted(abs(e) for e in errs)
    n = len(a)
    if not n:
        print(f'  {label}: no data'); return
    w = lambda k: sum(1 for e in a if e <= k) / n
    print(f'  {label:<26} n={n:3}  median|e|={statistics.median(a):.2f}f  '
          f'p90={a[int(0.9 * (n - 1))]:.2f}f  '
          f'<=1f={w(1):.0%}  <=2f={w(2):.0%}  <=3f={w(3):.0%}  <=5f={w(5):.0%}')


def main():
    global FEATURES, MODEL_PATH, META_PATH, CONF_PROBA, CONF_MARGIN
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', choices=['gb', 'rf', 'logreg'], default='logreg')
    ap.add_argument('--audio-only', action='store_true',
                    help='train the pure-audio label-generation teacher (14 audio-shape '
                         'features only, no pose/ball/time-prior); saves onset_classifier_audioonly.pkl')
    args = ap.parse_args()

    if args.audio_only:
        FEATURES = AUDIO_ONLY_FEATURE_NAMES
        MODEL_PATH = os.path.join(_D, 'onset_classifier_audioonly.pkl')
        META_PATH = os.path.join(_D, 'onset_classifier_audioonly_meta.json')
        CONF_PROBA, CONF_MARGIN = 0.75, 0.25   # harder gate -- drops the p90 tail
        print(f'AUDIO-ONLY teacher: {len(FEATURES)} features, gate proba>={CONF_PROBA} '
              f'margin>={CONF_MARGIN}', file=sys.stderr)

    X, y, groups, meta_rows, clips = build_dataset()
    n_splits = min(5, len(set(groups)))
    gkf = GroupKFold(n_splits=n_splits)

    pipe = make_model(args.model)
    proba = cross_val_predict(pipe, X, y, groups=groups, cv=gkf,
                              method='predict_proba', n_jobs=-1)[:, 1]

    auc = roc_auc_score(y, proba)
    pred = (proba >= 0.5).astype(int)
    prec = precision_score(y, pred, zero_division=0)
    rec = recall_score(y, pred, zero_division=0)

    # per-clip: pick argmax proba among that clip's training onsets
    by_clip = {}
    for i, m in enumerate(meta_rows):
        by_clip.setdefault(m['id'], []).append((proba[i], m))
    picked_errs, oracle_errs = [], []
    conf_flags = []
    for cid, lst in by_clip.items():
        lst.sort(key=lambda p: -p[0])
        top_p, top_m = lst[0]
        fps = top_m['fps']
        pick_err = (top_m['onset_t'] - ONSET_BIAS_F / fps - top_m['teacher']) * fps
        picked_errs.append(pick_err)
        margin = top_p - (lst[1][0] if len(lst) > 1 else 0.0)
        conf_flags.append((abs(pick_err) <= 3, top_p >= CONF_PROBA and margin >= CONF_MARGIN))
        oracle_errs.append(min(((m['onset_t'] - ONSET_BIAS_F / fps - m['teacher']) * fps
                                for _, m in lst), key=abs))

    print('\n' + '=' * 70)
    print(f'ONSET CLASSIFIER  --  model={args.model}  {n_splits}-fold GroupKFold CV')
    print('=' * 70)
    print(f'onset-level:  AUC={auc:.3f}  precision@.5={prec:.3f}  recall@.5={rec:.3f}')
    print(f'\ncontact-time error (recoverable clips, n={len(picked_errs)}):')
    summarise(picked_errs, 'classifier pick')
    summarise(oracle_errs, 'oracle (ceiling)')
    print(f'\n(Phase A dumb picker baseline: ~60-69% <=3f, oracle ~82% <=3f over all 197)')

    conf = [e for (ok, c), e in zip(conf_flags, picked_errs) if c]
    flag = [e for (ok, c), e in zip(conf_flags, picked_errs) if not c]
    n_conf = len(conf)
    print(f'\nconfidence split:  confident={n_conf}/{len(picked_errs)} '
          f'({n_conf / len(picked_errs):.0%})')
    summarise(conf, 'confident subset')
    summarise(flag, 'flagged subset')

    # fit final on all data + feature importances
    pipe.fit(X, y)
    clf = pipe.named_steps['clf']
    if hasattr(clf, 'feature_importances_'):
        imp = sorted(zip(FEATURES, clf.feature_importances_), key=lambda t: -t[1])
        print('\nfeature importance (top 12):')
        for name, v in imp[:12]:
            print(f'  {name:<24} {v:.3f}')
    elif hasattr(clf, 'coef_'):
        imp = sorted(zip(FEATURES, clf.coef_[0]), key=lambda t: -abs(t[1]))
        print('\nstandardised coefficients (top 12 by |weight|):')
        for name, v in imp[:12]:
            print(f'  {name:<24} {v:+.3f}')

    joblib.dump(pipe, MODEL_PATH)
    meta = {
        'model': args.model, 'feature_names': FEATURES,
        'audio_only': bool(args.audio_only),
        'conf_proba': CONF_PROBA, 'conf_margin': CONF_MARGIN,
        'onset_bias_f': ONSET_BIAS_F, 'pos_tol_f': POS_TOL_F,
        'cv_auc': round(float(auc), 4),
        'cv_contact_median_ae_f': round(statistics.median(abs(e) for e in picked_errs), 3),
        'cv_contact_within_3f': round(sum(1 for e in picked_errs if abs(e) <= 3) / len(picked_errs), 4),
        'confident_frac': round(n_conf / len(picked_errs), 4),
        'n_clips': len(picked_errs),
    }
    json.dump(meta, open(META_PATH, 'w'), indent=2)
    print(f'\nsaved {MODEL_PATH}\nsaved {META_PATH}')


if __name__ == '__main__':
    main()
