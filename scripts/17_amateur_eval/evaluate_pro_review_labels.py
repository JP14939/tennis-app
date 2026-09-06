"""
Cross-check the shot-type classifiers against Jack's OWN ground-truth labels.

Every other shot-type "label" on disk is either Claude's own vision label or
agreement-with-Claude. The one genuine hand-verified set is Pro Clip Review:
~400 pro broadcast clips Jack confirmed or corrected the shot type on, already
materialised by extract_training_features_from_pro_verdicts.py into
data/14_shot_classifier/training_features_from_pro.json
({clip_path, contact_frame, label, features, verdict, id}).

For each labelled clip this records, and reports a confusion matrix for:
  rule_pick         -- classify_shot.classify()          (free)
  ml_pick           -- shot_classifier_model.pkl          (free, needs a v2 retrain)
  claude_primed_pick -- shot_classifier_verifier.verify_shot(), told the rule pick
  claude_blind_pick  -- verify_shot(blind=True), NOT told the rule pick

The two Claude variants only run on a stratified --claude-subset (default 100,
every backhand force-included) and cost ~$0.0015/call on Haiku. Priming vs blind
separates "Claude is bad at this" from "Claude rubber-stamps the student's pick"
(the production verify_shot() is always primed).

This is measurement only -- it does NOT backfill any training log (pro-review
labels give negative transfer to the live model; see HANDOVER.md "Session
2026-09-02 (later)" section 7).

Usage:
  python evaluate_pro_review_labels.py                       # rule + ml only, all clips
  python evaluate_pro_review_labels.py --claude-subset 100    # + Claude on 100 stratified clips
  python evaluate_pro_review_labels.py --claude-subset 0      # explicitly no Claude
  python evaluate_pro_review_labels.py --report-only
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '08_comparison_engine'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '04_clip_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '14_shot_classifier'))

import cv2  # noqa: E402
from paths import DATA_DIR  # noqa: E402
from classify_shot import classify  # noqa: E402
from extract_training_features import FEATURE_NAMES  # noqa: E402

PRO_FEATURES_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'training_features_from_pro.json')
ML_MODEL_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_model.pkl')
ML_META_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_model_meta.json')
OUT_DIR = os.path.join(DATA_DIR, '17_amateur_eval')
RESULTS_PATH = os.path.join(OUT_DIR, 'pro_review_results.jsonl')

CLASSES = ['forehand', 'backhand', 'serve']


# ── students ─────────────────────────────────────────────────────────────────

def _load_ml():
    if not os.path.exists(ML_MODEL_PATH):
        print('  [ml] no shot_classifier_model.pkl -- ml_pick will be null', file=sys.stderr)
        return None
    import joblib
    meta = {}
    if os.path.exists(ML_META_PATH):
        with open(ML_META_PATH) as f:
            meta = json.load(f)
    if meta.get('feature_version') != 'v2-bodynorm':
        print(f"  [ml] model meta feature_version={meta.get('feature_version')!r} "
              f"(need 'v2-bodynorm') -- retrain first (train_shot_classifier_model.py). "
              f"ml_pick will be null.", file=sys.stderr)
        return None
    return joblib.load(ML_MODEL_PATH)


def _ml_pick(model, features):
    """features: the stored dict from training_features_from_pro.json."""
    x = np.array([[features.get(n, np.nan) for n in FEATURE_NAMES]], dtype=float)
    return str(model.predict(x)[0])


def _rule_pick(clip_path, contact_frame):
    cap = cv2.VideoCapture(clip_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if not fps or fps <= 0:
        raise RuntimeError('bad fps')
    res = classify(clip_path, contact_frame / fps)
    return res['shot_type'], res['scores']


def _contact_frame_image(clip_path, contact_frame):
    cap = cv2.VideoCapture(clip_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, contact_frame))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f'could not read frame {contact_frame}')
    return frame


# ── stratified Claude subset ─────────────────────────────────────────────────

def pick_claude_subset(rows, n):
    """Deterministic stratified sample of ~n clips, id-ordered. Rare/informative
    classes first (serve, then backhand), forehand fills the remainder -- so a
    small budget still measures precision on every class, not just forehand."""
    if n <= 0:
        return set()
    by_label = defaultdict(list)
    for r in sorted(rows, key=lambda r: r['id']):
        by_label[r['label']].append(r['id'])

    chosen = list(by_label.get('serve', [])[:n])          # all serves (only ~27)
    rest = n - len(chosen)
    bh = by_label.get('backhand', [])
    fh = by_label.get('forehand', [])
    take_bh = min(len(bh), round(rest * 0.6))             # backhand is the class in question
    chosen.extend(bh[:take_bh])
    chosen.extend(fh[:n - len(chosen)])
    return set(chosen[:n])


# ── run ──────────────────────────────────────────────────────────────────────

def load_checkpoint():
    done = {}
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    done[r['id']] = r
                except (json.JSONDecodeError, KeyError):
                    continue
    return done


def append_result(rec):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RESULTS_PATH, 'a') as f:
        f.write(json.dumps(rec) + '\n')


def _acquire_lock():
    """Single-instance guard -- this script makes paid Claude calls; two copies
    racing (e.g. a stale background launch + a new one) double the spend and
    corrupt the append-only results file."""
    lock = os.path.join(OUT_DIR, '.pro_review_eval.lock')
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(lock):
        with open(lock) as f:
            who = f.read().strip()
        sys.exit(f'Another run holds {lock} ({who}). If it is dead, delete the file and retry.')
    with open(lock, 'w') as f:
        f.write(f'pid {os.getpid()} @ {os.path.basename(sys.argv[0])}')
    import atexit
    atexit.register(lambda: os.path.exists(lock) and os.remove(lock))


def run(claude_subset, limit):
    _acquire_lock()
    if not os.path.exists(PRO_FEATURES_PATH):
        sys.exit(f'{PRO_FEATURES_PATH} not found -- run:\n'
                 f'  python 14_shot_classifier/extract_training_features_from_pro_verdicts.py')
    with open(PRO_FEATURES_PATH) as f:
        rows = json.load(f)
    rows = [r for r in rows if r.get('label') in CLASSES]
    if limit:
        rows = rows[:limit]

    claude_ids = pick_claude_subset(rows, claude_subset)
    print(f'{len(rows)} labelled clips; Claude on {len(claude_ids)} '
          f'(labels: {dict(Counter(r["label"] for r in rows))})', file=sys.stderr)

    model = _load_ml()
    done = load_checkpoint()

    verify_shot = cost_before = None
    if claude_ids:
        from shot_classifier_verifier import verify_shot, cost_summary
        cost_before = cost_summary()['estimated_cost_usd']

    for i, r in enumerate(rows, 1):
        rid = r['id']
        prev = done.get(rid)
        # redo a row only if it's now in the Claude subset but wasn't run with Claude before
        if prev and not (rid in claude_ids and prev.get('claude_primed_pick') is None and 'claude_error' not in prev):
            continue

        rec = {'id': rid, 'label': r['label'], 'verdict': r.get('verdict'),
               'clip_path': r['clip_path'], 'contact_frame': r['contact_frame']}

        rec['ml_pick'] = _ml_pick(model, r['features']) if model is not None else None

        try:
            rec['rule_pick'], rec['rule_scores'] = _rule_pick(r['clip_path'], r['contact_frame'])
        except Exception as e:  # noqa: BLE001
            rec['rule_pick'], rec['rule_scores'], rec['rule_error'] = None, None, str(e)

        if rid in claude_ids:
            try:
                frame = _contact_frame_image(r['clip_path'], r['contact_frame'])
                scores = rec.get('rule_scores') or {c: 0.0 for c in CLASSES}
                pick = rec.get('rule_pick') or 'forehand'
                rec['claude_primed_pick'] = verify_shot(frame, scores, pick).get('shot_type')
                rec['claude_blind_pick'] = verify_shot(frame, scores, pick, blind=True).get('shot_type')
            except Exception as e:  # noqa: BLE001
                rec['claude_error'] = str(e)

        append_result(rec)
        if i % 25 == 0:
            print(f'  [{i}/{len(rows)}] {rid}', file=sys.stderr)

    if claude_ids:
        from shot_classifier_verifier import cost_summary
        spent = round(cost_summary()['estimated_cost_usd'] - cost_before, 4)
        print(f'\nEstimated Claude spend this run: ~${spent}', file=sys.stderr)

    print_report()


# ── report ───────────────────────────────────────────────────────────────────

def _score(records, pick_key):
    pairs = [(r['label'], r[pick_key]) for r in records if r.get(pick_key) in CLASSES]
    if not pairs:
        print(f'  {pick_key}: no predictions')
        return
    correct = sum(1 for t, p in pairs if t == p)
    print(f'\n  {pick_key}  (N={len(pairs)}, accuracy={correct / len(pairs):.1%})')
    conf = Counter(pairs)
    for t in CLASSES:
        row = '  '.join(f'{p}:{conf.get((t, p), 0):>3}' for p in CLASSES)
        n_t = sum(conf.get((t, p), 0) for p in CLASSES)
        rec = conf.get((t, t), 0) / n_t if n_t else 0.0
        print(f'    true {t:<9} -> {row}    recall={rec:.0%}')
    for p in CLASSES:
        n_p = sum(conf.get((t, p), 0) for t in CLASSES)
        prec = conf.get((p, p), 0) / n_p if n_p else 0.0
        print(f'    precision {p:<9} {prec:.0%}')


def print_report():
    if not os.path.exists(RESULTS_PATH):
        print('No results yet.')
        return
    with open(RESULTS_PATH) as f:
        records = [json.loads(l) for l in f if l.strip()]

    print(f'\n=== {len(records)} clips scored vs Jack\'s Pro Clip Review labels ===')
    print(f'label mix: {dict(Counter(r["label"] for r in records))}')
    for key in ('rule_pick', 'ml_pick', 'claude_primed_pick', 'claude_blind_pick'):
        _score(records, key)

    claude_rows = [r for r in records if r.get('claude_primed_pick') in CLASSES
                   and r.get('claude_blind_pick') in CLASSES]
    if claude_rows:
        prime_right = sum(1 for r in claude_rows if r['claude_primed_pick'] == r['label'])
        blind_right = sum(1 for r in claude_rows if r['claude_blind_pick'] == r['label'])
        flipped_to_rule = sum(1 for r in claude_rows
                              if r['claude_primed_pick'] == r.get('rule_pick')
                              and r['claude_blind_pick'] != r.get('rule_pick'))
        print(f'\n  --- priming effect (N={len(claude_rows)}) ---')
        print(f'    primed correct {prime_right}/{len(claude_rows)}  |  '
              f'blind correct {blind_right}/{len(claude_rows)}')
        print(f'    primed matched the rule pick where blind did not: {flipped_to_rule}')

    errs = Counter(k for r in records for k in ('rule_error', 'claude_error') if r.get(k))
    if errs:
        print(f'\n  errors: {dict(errs)}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--claude-subset', type=int, default=0,
                    help='run the two Claude variants on this many clips (stratified, every backhand included). 0 = none.')
    ap.add_argument('--limit', type=int, default=None, help='only the first N clips')
    ap.add_argument('--report-only', action='store_true')
    args = ap.parse_args()

    if args.report_only:
        print_report()
        return
    run(args.claude_subset, args.limit)


if __name__ == '__main__':
    main()
