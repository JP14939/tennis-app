"""
Section 8 item 5: fit infer_angle.FULL_NET_FRACTION against coarse known
camera angles from 0c fence footage.

BLOCKED until a 0c manifest exists. The manifest is a JSON list:
  [{"video": "<path>", "coarse_bucket": "front|semi|diagonal|side",
    "approx_deg": 35, "notes": "behind centre mark, tripod ~net height"}, ...]
`approx_deg` is optional (used only for the secondary RMSE); `coarse_bucket`
is the primary signal.

Method: run the real pipeline once per video to get the median net width
(f-independent), then sweep f in [0.60, 1.00]. For each f, convert every
video's net width to an angle via the net-foreshortening formula
(acos(min(width/f, 1))), bucket it with infer_angle.angle_label, and score
against the manifest bucket with an ordinal (|rank difference|) loss.

Output: loss vs f, the best f, the confusion matrix at best f, and -- the
honest headline -- the RANGE of f within one bucket-error of optimal. If that
range is wide and contains 0.80, the recommendation is "leave 0.80".

Writes nothing outside data/10_net_detection/.

Usage:
  python calibrate_full_net_fraction.py --manifest <manifest.json>
"""
import argparse
import json
import math
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import angle_label, infer_camera_angle, create_landmarker  # noqa: E402

OUT_DIR = os.path.join(SCRIPTS_DIR, '..', 'data', '10_net_detection', 'full_net_fraction_calib')

# front < semi < diagonal < side  -- ordinal ranks for the loss
BUCKET_RANK = {'front': 0, 'semi': 1, 'diagonal': 2, 'side': 3}
LABEL_RANK = {
    'Front view': 0, 'Semi-front': 1, 'Diagonal (ideal)': 2,
    'Semi-side': 3, 'Side view': 3, 'Unknown': None,
}
F_GRID = [round(0.60 + 0.01 * i, 2) for i in range(41)]  # 0.60 .. 1.00


def angle_from_width(net_width, f):
    return math.degrees(math.acos(max(min(net_width / f, 1.0), 0.001)))


def measure_widths(manifest, landmarker):
    """One real pipeline run per video -> f-independent median net width."""
    out = []
    for item in manifest:
        video = item['video']
        if not os.path.exists(video):
            print(f'  MISSING: {video}', file=sys.stderr)
            continue
        angle, conf, debug = infer_camera_angle(video, landmarker=landmarker)
        width = debug.get('median_width') if isinstance(debug, dict) else None
        if width is None:
            print(f'  no net width for {os.path.basename(video)} '
                  f'(method={debug.get("net_detection_method") if isinstance(debug, dict) else debug})',
                  file=sys.stderr)
            continue
        out.append({
            'video': os.path.basename(video),
            'bucket': item['coarse_bucket'],
            'approx_deg': item.get('approx_deg'),
            'net_width': width,
            'pipeline_angle': angle,
            'pipeline_conf': conf,
        })
    return out


def score_f(rows, f):
    ord_loss = 0
    sq_err = []
    confusion = {}  # (true_bucket, pred_label) -> count
    for r in rows:
        pred_deg = angle_from_width(r['net_width'], f)
        pred_label = angle_label(pred_deg)
        tr = BUCKET_RANK[r['bucket']]
        pr = LABEL_RANK.get(pred_label)
        if pr is not None:
            ord_loss += abs(tr - pr)
        confusion[(r['bucket'], pred_label)] = confusion.get((r['bucket'], pred_label), 0) + 1
        if r['approx_deg'] is not None:
            sq_err.append((pred_deg - r['approx_deg']) ** 2)
    rmse = math.sqrt(sum(sq_err) / len(sq_err)) if sq_err else None
    return ord_loss, rmse, confusion


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    args = ap.parse_args()

    with open(args.manifest) as f:
        manifest = json.load(f)
    for item in manifest:
        if item['coarse_bucket'] not in BUCKET_RANK:
            raise SystemExit(f"bad coarse_bucket {item['coarse_bucket']!r} "
                             f"(want one of {list(BUCKET_RANK)})")

    lm = create_landmarker()
    rows = measure_widths(manifest, lm)
    lm.close()
    if not rows:
        raise SystemExit('no usable videos -- nothing to fit')

    print(f'\n{len(rows)}/{len(manifest)} videos yielded a net width.\n')

    results = []
    for f in F_GRID:
        ord_loss, rmse, _ = score_f(rows, f)
        results.append((f, ord_loss, rmse))

    best_loss = min(r[1] for r in results)
    within_one = [r[0] for r in results if r[1] <= best_loss + len(rows)]  # <= 1 bucket-error/video worse
    best_fs = [r[0] for r in results if r[1] == best_loss]
    best_f = best_fs[len(best_fs) // 2]  # middle of the optimal plateau

    print(f"{'f':>6} {'ord_loss':>9} {'rmse_deg':>9}")
    for f, ol, rmse in results:
        mark = '  <-- best' if ol == best_loss else ''
        print(f'{f:>6.2f} {ol:>9} {rmse if rmse is None else round(rmse, 1):>9}{mark}')

    print(f'\nbest f (plateau middle): {best_f}')
    print(f'f within one bucket-error/video of optimal: '
          f'{min(within_one):.2f} .. {max(within_one):.2f}')
    print(f'0.80 in that band? {"YES -- leave FULL_NET_FRACTION at 0.80" if min(within_one) <= 0.80 <= max(within_one) else "NO -- consider moving it (atomic commit, see infer_angle.py)"}')

    _, _, confusion = score_f(rows, best_f)
    print(f'\nconfusion at f={best_f} (true bucket -> predicted angle_label):')
    for (tb, pl), c in sorted(confusion.items()):
        print(f'  {tb:<9} -> {pl:<18} {c}')

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, 'fit.json')
    with open(out_path, 'w') as fh:
        json.dump({'rows': rows, 'grid': results, 'best_f': best_f,
                   'within_one_band': [min(within_one), max(within_one)]}, fh, indent=1)
    print(f'\nwrote {out_path}')


if __name__ == '__main__':
    main()
