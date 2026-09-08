"""
Evaluate the net-keypoint model's CORNER PRECISION against the hand-labeled,
source-disjoint net_keypoint_testset_v1 -- the number that decides whether
homography-based signed azimuth is viable (see net_geometry_sensitivity.py).

The existing test_net_detector_*.py scripts only answer "net detected: yes/no".
This one measures where the corners land.

Metrics
  detection : net-return rate, all-4-corner rate, top-2-corner rate, FP rate on
              the negative bucket
  localization (points present in GT and returned):
              per-keypoint L2 pixel error -- raw px, / image width, / GT net width
              mean / median / p90 / max ; OKS (k=0.05 uniform) ; left/right swap rate
  calibration : pixel error binned by predicted confidence
  slices : source bucket / view_direction_guess / occludes_net / top vs base

Outputs to data/10_net_detection/net_keypoint_eval/
  results_<run>.jsonl   report_<run>.txt   report_<run>.json   gallery_<run>/

Usage
  python eval_net_keypoints.py --model-run yolo_pose_run_v4
  python eval_net_keypoints.py --model-run yolo_pose_run_v4 --compare yolo_pose_run_v5
  python eval_net_keypoints.py --model-run yolo_pose_run_v4 --report-only
  python eval_net_keypoints.py --model-run yolo_pose_run_v4 --limit 20 --conf 0.25
"""
import argparse
import json
import math
import os
import statistics as stats
import sys
from collections import defaultdict

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', '..', 'data'))
NET_DIR = os.path.join(DATA, '10_net_detection')
TESTSET_DIR = os.path.join(NET_DIR, 'net_keypoint_testset_v1')
FRAMES_DIR = os.path.join(TESTSET_DIR, 'frames')
LABELS_PATH = os.path.join(TESTSET_DIR, 'net_keypoint_testset_v1_labels.json')
MANIFEST_PATH = os.path.join(TESTSET_DIR, 'frame_manifest.json')
OUT_DIR = os.path.join(NET_DIR, 'net_keypoint_eval')

POINTS = ['net_top_left', 'net_top_right', 'left_post_base', 'right_post_base']
CONF_BINS = [(0.0, 0.4), (0.4, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]
OKS_K = 0.05


def resolve_weights(run_or_path):
    if os.path.isfile(run_or_path):
        return run_or_path
    cand = os.path.join(NET_DIR, run_or_path, 'weights', 'best.pt')
    if os.path.isfile(cand):
        return cand
    raise SystemExit(f'Cannot resolve weights from "{run_or_path}"')


def run_name(run_or_path):
    if os.path.isfile(run_or_path):
        return os.path.splitext(os.path.basename(run_or_path))[0]
    return run_or_path


def l2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def load_checkpoint(path):
    done = {}
    if not os.path.exists(path):
        return done
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                done[rec['frame_file']] = rec
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def append_result(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a') as f:
        f.write(json.dumps(rec) + '\n')


def predict(model, img_bgr, conf):
    """Returns {name: {xy, conf}}. Handles 2- or 4-keypoint models: the first N
    of POINTS are used, N = the model's keypoint count."""
    res = model.predict(img_bgr, verbose=False, conf=conf)
    if not res or res[0].keypoints is None or len(res[0].keypoints) == 0:
        return {}
    kp = res[0].keypoints
    if kp.xy.shape[1] == 0:
        return {}
    xy = kp.xy[0].cpu().numpy()
    n = min(xy.shape[0], len(POINTS))
    confs = kp.conf[0].cpu().numpy() if kp.conf is not None else [None] * n
    out = {}
    for i in range(n):
        name = POINTS[i]
        x, y = float(xy[i][0]), float(xy[i][1])
        if x == 0 and y == 0:
            continue
        out[name] = {'xy': [round(x, 2), round(y, 2)],
                     'conf': (round(float(confs[i]), 4) if i < len(confs) and confs[i] is not None else None)}
    return out


def net_width(pts):
    tl, tr = pts.get('net_top_left'), pts.get('net_top_right')
    if tl and tr:
        return abs(tr[0] - tl[0])
    return None


def gt_bbox_area(gt):
    xs = [p[0] for p in gt.values() if p]
    ys = [p[1] for p in gt.values() if p]
    if len(xs) < 2:
        return None
    return max(1.0, (max(xs) - min(xs)) * (max(ys) - min(ys)))


def process(frame_file, gt_rec, man_rec, model, conf):
    path = os.path.join(FRAMES_DIR, frame_file)
    img = cv2.imread(path)
    if img is None:
        return {'frame_file': frame_file, 'error': 'unreadable frame'}
    h, w = img.shape[:2]
    pred = predict(model, img, conf)

    gt = {p: gt_rec['keypoints'].get(p) for p in POINTS}
    is_negative = (man_rec or {}).get('source_kind') == 'negative' or gt_rec.get('no_net')

    rec = {
        'frame_file': frame_file,
        'source_kind': (man_rec or {}).get('source_kind'),
        'source_video': (man_rec or {}).get('source_video'),
        'gt_confidence': gt_rec.get('gt_confidence'),
        'view_direction_guess': (man_rec or {}).get('view_direction_guess'),
        'occludes_net': (man_rec or {}).get('occludes_net'),
        'is_negative': bool(is_negative),
        'partial_net': bool(gt_rec.get('partial_net')),
        'usable': gt_rec.get('usable', False),
        'img_w': w, 'img_h': h,
        'pred_points': sorted(pred.keys()),
        'any_return': len(pred) > 0,
        'all4': len(pred) == 4,
        'top2': ('net_top_left' in pred and 'net_top_right' in pred),
    }

    if is_negative:
        rec['false_positive'] = len(pred) > 0
        return rec
    if not gt_rec.get('usable'):
        return rec

    gt_w = net_width({k: v for k, v in gt.items() if v})
    pred_xy = {k: v['xy'] for k, v in pred.items()}
    rec['pred_xy'] = pred_xy  # persisted for net_geometry_sensitivity.py Part A
    rec['gt_xy'] = {p: gt[p] for p in POINTS if gt[p] is not None}
    pred_w = net_width(pred_xy)
    rec['net_width_gt'] = round(gt_w, 2) if gt_w else None
    rec['net_width_pred'] = round(pred_w, 2) if pred_w else None

    errs = {}
    for p in POINTS:
        if gt[p] is not None and p in pred_xy:
            errs[p] = round(l2(gt[p], pred_xy[p]), 2)
    rec['errors_px'] = errs
    rec['errors_frac_w'] = {p: round(e / w, 5) for p, e in errs.items()}
    if gt_w:
        rec['errors_frac_netw'] = {p: round(e / gt_w, 4) for p, e in errs.items()}

    if 'net_top_left' in pred_xy and 'net_top_right' in pred_xy:
        rec['swapped'] = pred_xy['net_top_left'][0] > pred_xy['net_top_right'][0]

    area = gt_bbox_area({k: v for k, v in gt.items() if v})
    if area and errs:
        s2 = area
        oks_terms = [math.exp(-(e ** 2) / (2 * s2 * OKS_K ** 2)) for e in errs.values()]
        rec['oks'] = round(sum(oks_terms) / len(oks_terms), 4)

    rec['pred_conf'] = {k: v['conf'] for k, v in pred.items()}
    return rec


# ---------------- reporting ----------------

def _stat_line(vals):
    if not vals:
        return 'n=0'
    vals = sorted(vals)
    p90 = vals[min(len(vals) - 1, int(0.9 * len(vals)))]
    return (f'n={len(vals):3d}  mean={stats.mean(vals):7.2f}  median={stats.median(vals):7.2f}  '
            f'p90={p90:7.2f}  max={max(vals):7.2f}')


def _wilson_lb(succ, n, z=1.96):
    if n == 0:
        return 0.0
    p = succ / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (c - a) / d


def build_report(records, run, weights):
    L = []
    def w(s=''):
        L.append(s)

    usable = [r for r in records if r.get('usable') and not r.get('is_negative') and 'error' not in r]
    negs = [r for r in records if r.get('is_negative')]
    errored = [r for r in records if 'error' in r]

    w(f'=== eval_net_keypoints  run={run} ===')
    w(f'weights: {weights}')
    w(f'testset: net_keypoint_testset_v1   usable={len(usable)}  negatives={len(negs)}  errored={len(errored)}')
    w()

    w('--- detection (usable frames) ---')
    n = len(usable)
    for label, key in [('any net returned', 'any_return'), ('all 4 corners', 'all4'),
                       ('top-2 corners', 'top2')]:
        s = sum(1 for r in usable if r.get(key))
        w(f'  {label:20s} {s:3d}/{n}  ({s/n:.1%} , Wilson LB {_wilson_lb(s, n):.1%})' if n else f'  {label}: n=0')
    if negs:
        fp = sum(1 for r in negs if r.get('false_positive'))
        w(f'  FP on negatives      {fp:3d}/{len(negs)}  ({fp/len(negs):.1%})')
    w()

    w('--- localization: per-keypoint L2 error ---')
    for norm_key, norm_label in [('errors_px', 'raw px'), ('errors_frac_w', '/ image width'),
                                 ('errors_frac_netw', '/ GT net width')]:
        w(f'  [{norm_label}]')
        for p in POINTS:
            vals = [r[norm_key][p] for r in usable if norm_key in r and p in r[norm_key]]
            w(f'    {p:16s} {_stat_line(vals)}')
        allvals = [v for r in usable if norm_key in r for v in r[norm_key].values()]
        w(f'    {"ALL":16s} {_stat_line(allvals)}')
    top_px = [r['errors_px'][p] for r in usable if 'errors_px' in r
              for p in ('net_top_left', 'net_top_right') if p in r['errors_px']]
    base_px = [r['errors_px'][p] for r in usable if 'errors_px' in r
               for p in ('left_post_base', 'right_post_base') if p in r['errors_px']]
    w(f'    {"top corners":16s} {_stat_line(top_px)}')
    w(f'    {"post bases":16s} {_stat_line(base_px)}')
    w()

    oks_vals = [r['oks'] for r in usable if 'oks' in r]
    if oks_vals:
        w(f'--- OKS (k={OKS_K}) ---')
        w(f'  mean OKS={stats.mean(oks_vals):.3f}   AP@.5={sum(1 for v in oks_vals if v>=.5)/len(oks_vals):.1%}'
          f'   AP@.75={sum(1 for v in oks_vals if v>=.75)/len(oks_vals):.1%}')
        sw = sum(1 for r in usable if r.get('swapped'))
        w(f'  left/right swap rate: {sw}/{len(usable)}')
        w()

    w('--- confidence calibration (per returned keypoint) ---')
    bins = defaultdict(list)
    for r in usable:
        for p, e in r.get('errors_px', {}).items():
            c = r.get('pred_conf', {}).get(p)
            if c is None:
                continue
            for lo, hi in CONF_BINS:
                if lo <= c < hi:
                    bins[(lo, hi)].append(e)
                    break
    for lo, hi in CONF_BINS:
        vals = bins[(lo, hi)]
        if vals:
            vs = sorted(vals)
            p90 = vs[min(len(vs) - 1, int(0.9 * len(vs)))]
            w(f'  conf [{lo:.2f},{hi:.2f})  n={len(vals):3d}  mean_err={stats.mean(vals):6.2f}  p90={p90:6.2f}')
    w()

    w('--- slices: mean / p90 ALL-keypoint px error ---')
    def slice_by(fn, title):
        w(f'  by {title}:')
        groups = defaultdict(list)
        for r in usable:
            groups[fn(r)].append(r)
        for g, rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
            vals = [v for r in rs if 'errors_px' in r for v in r['errors_px'].values()]
            if vals:
                vs = sorted(vals)
                p90 = vs[min(len(vs) - 1, int(0.9 * len(vs)))]
                w(f'    {str(g):22s} frames={len(rs):3d}  mean={stats.mean(vals):6.2f}  p90={p90:6.2f}')
    slice_by(lambda r: r.get('source_kind'), 'source bucket')
    slice_by(lambda r: r.get('view_direction_guess'), 'view_direction_guess')
    slice_by(lambda r: r.get('occludes_net'), 'occludes_net')
    slice_by(lambda r: r.get('gt_confidence'), 'gt_confidence')
    return '\n'.join(L)


def report_json(records):
    usable = [r for r in records if r.get('usable') and not r.get('is_negative') and 'error' not in r]
    all_px = [v for r in usable if 'errors_px' in r for v in r['errors_px'].values()]
    top_px = [r['errors_px'][p] for r in usable if 'errors_px' in r
              for p in ('net_top_left', 'net_top_right') if p in r['errors_px']]
    def p90(v):
        v = sorted(v)
        return v[min(len(v) - 1, int(0.9 * len(v)))] if v else None
    return {
        'n_usable': len(usable),
        'all4_rate': sum(1 for r in usable if r.get('all4')) / len(usable) if usable else None,
        'top2_rate': sum(1 for r in usable if r.get('top2')) / len(usable) if usable else None,
        'err_px_all_median': stats.median(all_px) if all_px else None,
        'err_px_all_p90': p90(all_px),
        'err_px_top_median': stats.median(top_px) if top_px else None,
        'err_px_top_p90': p90(top_px),
        'mean_oks': stats.mean([r['oks'] for r in usable if 'oks' in r]) if any('oks' in r for r in usable) else None,
    }


def save_gallery(records, run, n_worst=20):
    gdir = os.path.join(OUT_DIR, f'gallery_{run}')
    os.makedirs(gdir, exist_ok=True)
    scored = []
    for r in records:
        if 'errors_px' in r and r['errors_px']:
            scored.append((max(r['errors_px'].values()), r))
    scored.sort(key=lambda t: t[0], reverse=True)  # sort on the px error only -- the dict tie-breaker is unorderable
    worst = [r for _, r in scored[:n_worst]]
    fps = [r for r in records if r.get('false_positive')]
    missed = [r for r in records if r.get('usable') and not r.get('any_return') and not r.get('is_negative')]
    with open(os.path.join(gdir, 'index.json'), 'w') as f:
        json.dump({'worst': [r['frame_file'] for r in worst],
                   'false_positives': [r['frame_file'] for r in fps],
                   'missed': [r['frame_file'] for r in missed]}, f, indent=2)
    return gdir, len(worst), len(fps), len(missed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-run', required=True)
    ap.add_argument('--compare', default=None)
    ap.add_argument('--report-only', action='store_true')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--conf', type=float, default=0.25, help='detection conf floor for predict()')
    ap.add_argument('--no-gallery', action='store_true')
    ap.add_argument('--source-videos', default=None,
                    help='comma-separated source_video ids to keep (e.g. eval a model on '
                         'ONLY the videos it held out of training). Appends a _<tag> to the '
                         'results/report filenames so it does not clobber the full run.')
    args = ap.parse_args()

    keep_videos = set(args.source_videos.split(',')) if args.source_videos else None
    os.makedirs(OUT_DIR, exist_ok=True)
    run = run_name(args.model_run)
    if keep_videos:
        run = f'{run}_heldout'
    results_path = os.path.join(OUT_DIR, f'results_{run}.jsonl')

    if not args.report_only:
        if not os.path.exists(LABELS_PATH):
            raise SystemExit(f'No labels at {LABELS_PATH} -- label the test set first.')
        with open(LABELS_PATH) as f:
            labels = {r['frame_file']: r for r in json.load(f)['labels']}
        man = {}
        if os.path.exists(MANIFEST_PATH):
            with open(MANIFEST_PATH) as f:
                man = {r['frame_file']: r for r in json.load(f)}

        from ultralytics import YOLO
        weights = resolve_weights(args.model_run)
        model = YOLO(weights)

        done = load_checkpoint(results_path)
        items = list(labels.items())
        if keep_videos:
            items = [(ff, r) for ff, r in items
                     if (man.get(ff, {}).get('source_video') in keep_videos
                         or r.get('source_video') in keep_videos)]
            print(f'--source-videos: {len(items)} frames kept for {sorted(keep_videos)}', file=sys.stderr)
        if args.limit:
            items = items[:args.limit]
        for i, (ff, rec) in enumerate(items, 1):
            if ff in done:
                continue
            print(f'[{i}/{len(items)}] {ff}', file=sys.stderr)
            try:
                out = process(ff, rec, man.get(ff), model, args.conf)
            except Exception as e:  # noqa: BLE001
                out = {'frame_file': ff, 'error': str(e)}
                print(f'  ERROR {e}', file=sys.stderr)
            append_result(results_path, out)

    records = list(load_checkpoint(results_path).values())
    if not records:
        print('No results.')
        return
    weights = resolve_weights(args.model_run) if os.path.exists(
        os.path.join(NET_DIR, run)) or os.path.isfile(args.model_run) else run
    txt = build_report(records, run, weights)
    with open(os.path.join(OUT_DIR, f'report_{run}.txt'), 'w') as f:
        f.write(txt + '\n')
    with open(os.path.join(OUT_DIR, f'report_{run}.json'), 'w') as f:
        json.dump(report_json(records), f, indent=2)
    print(txt)

    if not args.no_gallery:
        gdir, nw, nfp, nm = save_gallery(records, run)
        print(f'\ngallery: {gdir}  (worst={nw} fp={nfp} missed={nm})')

    if args.compare:
        crun = run_name(args.compare)
        cpath = os.path.join(OUT_DIR, f'results_{crun}.jsonl')
        if not os.path.exists(cpath):
            print(f'\n--compare: no results for {crun} yet -- run eval on it first.')
            return
        a, b = report_json(records), report_json(list(load_checkpoint(cpath).values()))
        print(f'\n=== compare  {run}  vs  {crun} ===')
        for k in a:
            av, bv = a[k], b[k]
            if isinstance(av, float) and isinstance(bv, float):
                print(f'  {k:22s} {av:8.3f}   {bv:8.3f}   d={av-bv:+.3f}')
            else:
                print(f'  {k:22s} {av}   {bv}')
        better = (a['err_px_top_p90'] or 9e9) < (b['err_px_top_p90'] or 9e9)
        print(f'\n  verdict: {run} top-corner p90 error is '
              f'{"LOWER (better)" if better else "not lower"} than {crun}')


if __name__ == '__main__':
    main()
