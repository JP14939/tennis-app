"""
Compare every shot-type classifier against real ground truth, in one place.

Primary ground truth: the ~400 pro clips whose shot type Jack confirmed or
corrected in Pro Clip Review (data/14_shot_classifier/training_features_from_
pro.json, joined to pro_database.json by id). Broadcast domain -- the same
domain detect_rallies / analyze_rallies_parallel run on. All right-handed.

Secondary: the 116 Claude-vision-labelled amateur clips (phone domain).

Methods scored per clip:
  geom        classify_shot_geom.classify_geom        (the new geometric tree)
  traj_knn    classify_shot_trajectory               (DTW k-NN, leave-one-out on the pro set)
  rule        extract_clips SCORERS argmax           (the old rule scorers)
  ml_phone    shot_classifier_model.pkl
  ml_pipeline shot_classifier_pipeline_model.pkl     (if present)
  ensemble    geom, falling back to traj_knn/ml when geom confidence is low

No Claude calls. Reuses the 68 Claude picks already in pro_review_results.jsonl
for reference only.

Usage:
  python evaluate_shot_classifiers.py --set pro          # default
  python evaluate_shot_classifiers.py --set both
  python evaluate_shot_classifiers.py --report-only
"""
import argparse
import atexit
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in ('00_utils', '04_clip_extraction', '06_database_build',
          '08_comparison_engine', '14_shot_classifier'):
    sys.path.insert(0, os.path.join(SCRIPTS_DIR, p))

from paths import DATA_DIR  # noqa: E402
from extract_clips import nearest_pose, SCORERS  # noqa: E402
from extract_training_features import build_window, extract_features, FEATURE_NAMES  # noqa: E402
from extract_training_features_from_log import get_poses  # noqa: E402
import classify_shot_geom as geom  # noqa: E402
import classify_shot_trajectory as trajmod  # noqa: E402

PRO_FEATURES = os.path.join(DATA_DIR, '14_shot_classifier', 'training_features_from_pro.json')
PRO_DB = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
PRO_POSE_CACHE = os.path.join(DATA_DIR, '14_shot_classifier', 'pro_derived_poses')
AMATEUR_LABELS = os.path.join(DATA_DIR, '08_coaching_ai', 'amateur_swing_labels.json')
AMATEUR_MANIFEST = os.path.join(DATA_DIR, '04_clips', 'amateur', 'manifest.json')
AMATEUR_POSES = os.path.join(DATA_DIR, '17_amateur_eval', 'poses')
SWINGS_DIR = os.path.join(DATA_DIR, '03_swing_detection')
OUT_DIR = os.path.join(DATA_DIR, '17_amateur_eval')
RESULTS = os.path.join(OUT_DIR, 'shot_classifier_eval.jsonl')
LOCK = os.path.join(OUT_DIR, '.shot_classifier_eval.lock')

CLASSES = ['forehand', 'backhand', 'serve']
CONF_LOW = 0.35   # geom confidence below this -> ensemble consults traj/ml


def _lock():
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(LOCK):
        sys.exit(f'{LOCK} exists -- another run in progress (delete if stale).')
    with open(LOCK, 'w') as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(LOCK) and os.remove(LOCK))


# ── model loading ────────────────────────────────────────────────────────────

def _load_model(path):
    """Skip a model whose meta feature_version doesn't match the current
    extract_features (same guard classify_shot._get_ml_model applies) -- an
    old v1 model on v2 features is silent garbage, not a fair baseline."""
    if not os.path.exists(path):
        return None
    from extract_training_features import FEATURE_VERSION
    meta_path = path.replace('.pkl', '_meta.json')
    try:
        mv = json.load(open(meta_path)).get('feature_version', 'v1')
    except FileNotFoundError:
        mv = 'v1'
    if mv != FEATURE_VERSION:
        print(f'  [{os.path.basename(path)}] feature_version {mv!r} != {FEATURE_VERSION!r} -- skipped', file=sys.stderr)
        return None
    import joblib
    return joblib.load(path)


def _ml_pick(model, feats):
    x = np.array([[feats.get(n, np.nan) for n in FEATURE_NAMES]], dtype=float)
    return str(model.predict(x)[0])


def _ml_pick_conf(model, feats):
    """(pick, winning-class probability) -- the ensemble gates ML on this."""
    if model is None:
        return None, 0.0
    x = np.array([[feats.get(n, np.nan) for n in FEATURE_NAMES]], dtype=float)
    proba = model.predict_proba(x)[0]
    i = int(np.argmax(proba))
    return str(model.classes_[i]), float(proba[i])


def _rule_pick(peak_lm, prev_lm, window_lms):
    scores = {}
    for st, scorer in SCORERS.items():
        try:
            scores[st] = scorer(peak_lm, prev_lm, window_lms)[0] if st == 'serve' else scorer(peak_lm, prev_lm)[0]
        except Exception:
            scores[st] = 0.0
    return max(scores, key=scores.get)


# ── per-clip pose -> landmark lists ──────────────────────────────────────────

def _lms_from_pose_data(pose_data, contact_frame):
    idx = {fr['frame']: fr['landmarks'] for fr in pose_data['frames'] if fr['landmarks']}
    if not idx:
        return None
    peak = nearest_pose(idx, contact_frame)
    if peak is None:
        return None
    prev = nearest_pose(idx, contact_frame - 3)
    win = build_window(idx, contact_frame, pose_data.get('fps') or 30.0)
    return peak, prev, win


def _user_trajectory(pose_data, contact_frame):
    """Build a normalised swing trajectory from a list-form pose cache, the
    shape classify_by_trajectory expects."""
    from compare_swing import build_user_trajectory
    fps = pose_data.get('fps') or 30.0
    frames = [{'frame': fr['frame'],
               'landmarks': {lm['name']: lm for lm in fr['landmarks']} if fr['landmarks'] else None}
              for fr in pose_data['frames']]
    traj, _ = build_user_trajectory(frames, fps, contact_frame / fps)
    return traj


def _ensemble(geom_res, traj_res, ml_pick, use_trajectory=True, ml_conf=0.0):
    """Mirrors classify_shot.classify_ensemble. Broadcast (use_trajectory=True):
    geom-serve -> trajectory-kNN -> geom. Phone (use_trajectory=False): geom-serve
    -> trained model (gated at ML_CONF_MIN) -> geom at the lower
    GEOM_CONF_MIN_NOTRAJ floor. Keep constants in sync with classify_shot.py.
    NOTE: on the amateur set the ML model is train==test here -- read the trainer
    CV, not this row, for the honest ML number."""
    g = geom_res['shot_type']
    tp = (traj_res or {}).get('shot_type')
    tm = (traj_res or {}).get('margin', 0)
    if g == 'serve':
        return 'serve'
    if use_trajectory and tp in ('forehand', 'backhand') and tm >= 0.20:
        return tp
    if not use_trajectory and ml_pick in ('forehand', 'backhand') and ml_conf >= 0.55:  # ML_CONF_MIN
        return ml_pick
    geom_floor = 0.35 if use_trajectory else 0.15   # GEOM_CONF_MIN / GEOM_CONF_MIN_NOTRAJ
    if g in ('forehand', 'backhand') and geom_res.get('confidence', 0) >= geom_floor:
        return g
    return g or (tp if use_trajectory else ml_pick)


# ── run ──────────────────────────────────────────────────────────────────────

def _iter_pro():
    with open(PRO_FEATURES) as f:
        rows = json.load(f)
    with open(PRO_DB, encoding='utf-8') as f:
        db = {e['id']: e for e in json.load(f)['entries']}
    for r in rows:
        if r['label'] not in CLASSES:
            continue
        e = db.get(r['id'], {})
        yield {'set': 'pro', 'id': r['id'], 'label': r['label'],
               'clip_path': r['clip_path'], 'contact_frame': r['contact_frame'],
               'features': r['features'], 'view_direction': e.get('view_direction'),
               'trajectory': e.get('trajectory'), 'pose_cache': PRO_POSE_CACHE}


def _iter_amateur():
    labels = json.load(open(AMATEUR_LABELS))['labels']
    manifest = {f"{m['video_id']}_{m['swing_id']}": m for m in json.load(open(AMATEUR_MANIFEST))}
    swings = {}
    for key, label in labels.items():
        if label not in CLASSES:
            continue
        m = manifest.get(key)
        if not m:
            continue
        vid = m['video_id']
        if vid not in swings:
            p = os.path.join(SWINGS_DIR, f'amateur_{vid}_swings.json')
            swings[vid] = {s['swing_id']: s for s in json.load(open(p))['swings']} if os.path.exists(p) else {}
        sw = swings[vid].get(m['swing_id'])
        if not sw:
            continue
        pose_path = os.path.join(AMATEUR_POSES, f'{key}.json')
        if not os.path.exists(pose_path):
            continue
        yield {'set': 'amateur', 'id': key, 'label': label,
               'pose_path': pose_path, 'contact_frame': m['peak_frame'] - sw['start_frame'],
               'view_direction': None, 'trajectory': None}


def run(which, limit):
    _lock()
    ml_phone = _load_model(os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_model.pkl'))
    ml_pipe = _load_model(os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_pipeline_model.pkl'))

    done = set()
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            done = {json.loads(l)['id'] for l in f if l.strip()}

    iters = []
    if which in ('pro', 'both'):
        iters.append(_iter_pro())
    if which in ('amateur', 'both'):
        iters.append(_iter_amateur())

    n = 0
    fout = open(RESULTS, 'a')
    for it in iters:
        for row in it:
            if limit and n >= limit:
                break
            if row['id'] in done:
                continue
            n += 1
            rec = {'id': row['id'], 'set': row['set'], 'label': row['label'],
                   'view_direction': row['view_direction']}
            try:
                if row['set'] == 'pro':
                    pose_data = get_poses(row['clip_path'], row['contact_frame'], cache_dir=row['pose_cache'])
                    feats = row['features']
                else:
                    pose_data = json.load(open(row['pose_path']))
                    feats = None
                lms = _lms_from_pose_data(pose_data, row['contact_frame'])
                if lms is None:
                    rec['error'] = 'no pose near contact'
                    fout.write(json.dumps(rec) + '\n'); continue
                peak, prev, win = lms
                if feats is None:
                    feats = extract_features(peak, prev, win)

                g = geom.classify_geom(peak, prev, win, 'right')
                rec['geom'] = g['shot_type']
                rec['geom_conf'] = g['confidence']
                rec['rule'] = _rule_pick(peak, prev, win)
                rec['ml_phone'], _ml_phone_conf = _ml_pick_conf(ml_phone, feats)
                rec['ml_pipeline'] = _ml_pick(ml_pipe, feats) if ml_pipe is not None else None

                if row['set'] == 'pro' and row['trajectory']:
                    traj_res = trajmod.classify_by_trajectory(row['trajectory'], exclude_id=row['id'])
                else:
                    # amateur: build the user trajectory from cached poses and
                    # vote against the (broadcast) pro pool -- the real
                    # cross-domain test.
                    ut = _user_trajectory(pose_data, row['contact_frame'])
                    traj_res = trajmod.classify_by_trajectory(ut) if ut else None
                rec['traj_knn'] = (traj_res or {}).get('shot_type')
                rec['traj_margin'] = (traj_res or {}).get('margin')
                # The phone/highlight caller (detect_rallies.py --no-trajectory,
                # wired from highlights.js) runs the amateur domain with the
                # trajectory step off; measure it that way.
                rec['ensemble'] = _ensemble(g, traj_res, rec['ml_phone'],
                                            use_trajectory=(row['set'] == 'pro'),
                                            ml_conf=_ml_phone_conf)
            except Exception as e:  # noqa: BLE001
                rec['error'] = f'{type(e).__name__}: {e}'
            fout.write(json.dumps(rec) + '\n')
            if n % 50 == 0:
                fout.flush()
                print(f'  [{n}] {row["set"]} {row["id"]}', file=sys.stderr)
    fout.close()
    report()


# ── report ───────────────────────────────────────────────────────────────────

def _prf(records, key):
    pairs = [(r['label'], r[key]) for r in records if r.get(key) in CLASSES]
    if not pairs:
        print(f'    {key:<12} (no predictions)')
        return
    acc = sum(1 for t, p in pairs if t == p) / len(pairs)
    print(f'    {key:<12} acc {acc:.1%}  (n={len(pairs)})')
    conf = Counter(pairs)
    for t in CLASSES:
        nt = sum(conf.get((t, p), 0) for p in CLASSES)
        row = ' '.join(f'{p[:2]}:{conf.get((t, p), 0):>3}' for p in CLASSES)
        rec = conf.get((t, t), 0) / nt if nt else 0
        np_ = sum(conf.get((tt, t), 0) for tt in CLASSES)
        prec = conf.get((t, t), 0) / np_ if np_ else 0
        print(f'      true {t:<9} [{row}]  recall {rec:.0%}  precision {prec:.0%}')


def report():
    if not os.path.exists(RESULTS):
        print('no results'); return
    records = [json.loads(l) for l in open(RESULTS) if l.strip()]
    methods = ['geom', 'traj_knn', 'rule', 'ml_phone', 'ml_pipeline', 'ensemble']
    for s in sorted({r['set'] for r in records}):
        rs = [r for r in records if r['set'] == s and not r.get('error')]
        print(f'\n=== {s}  (n={len(rs)}, labels {dict(Counter(r["label"] for r in rs))}) ===')
        for m in methods:
            _prf(rs, m)
        # geom view-invariance
        vd = defaultdict(list)
        for r in rs:
            if r.get('geom') in CLASSES:
                vd[r.get('view_direction')].append(r['geom'] == r['label'])
        if any(k for k in vd):
            print('    geom by view_direction:',
                  {k: f'{sum(v)}/{len(v)}={sum(v)/len(v):.0%}' for k, v in vd.items()})
        # abstain: geom high-conf vs low-conf
        hi = [r for r in rs if r.get('geom') in CLASSES and r.get('geom_conf', 0) >= CONF_LOW]
        lo = [r for r in rs if r.get('geom') in CLASSES and r.get('geom_conf', 0) < CONF_LOW]
        for lbl, grp in (('geom high-conf', hi), ('geom low-conf', lo)):
            if grp:
                a = sum(1 for r in grp if r['geom'] == r['label']) / len(grp)
                print(f'    {lbl}: {len(grp)} clips, acc {a:.1%}')
    errs = Counter(r['error'].split(':')[0] for r in records if r.get('error'))
    if errs:
        print(f'\nerrors: {dict(errs)}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', choices=['pro', 'amateur', 'both'], default='pro')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--report-only', action='store_true')
    args = ap.parse_args()
    if args.report_only:
        report()
    else:
        run(args.set, args.limit)


if __name__ == '__main__':
    main()
