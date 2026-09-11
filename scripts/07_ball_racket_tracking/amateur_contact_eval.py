"""
Runs the live no-audio contact-frame pipeline against REAL amateur contact-
time ground truth (data/07_ball_racket_tracking/amateur_contact_labels.jsonl)
-- the acceptance gate plan swirling-popping-flame.md's Phase 4 calls for.
Every number in eval_pro_clip_contact.py comes from broadcast PRO footage;
this is the first check against footage that actually looks like what a real
no-audio user uploads (real amateur players, phone/YouTube framing).

Labels in amateur_contact_labels.jsonl come from two sources (both trustworthy,
tagged by `source`):
  - 'audio_pseudolabel' (label_amateur_contact_from_audio.py) -- the SAME
    onset_classifier.pkl + confidence gate the live app uses, run against the
    amateur source videos' own audio (the cut clips themselves have none --
    see that script's docstring). Only CONFIDENT picks are kept, the same
    methodology that validated the pro-DB audio fill (96% within 50ms of a
    human mark).
  - 'manual' (mark_amateur_contact_time.py) -- Jack's own hand-marked frame,
    for footage with no audio at all (his own raw fence clips).

Sibling of eval_pro_clip_contact.py; reuses its predict_one() directly (same
live pipeline: auto_contact_anchor_frame -> track_racket_and_ball ->
find_contact_frame) rather than re-implementing it -- this only supplies a
different label source and a synthetic `entry` dict predict_one() expects.

Usage:
  python amateur_contact_eval.py [--limit N] [--source audio_pseudolabel|manual]
"""
import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
for p in (HERE, os.path.join(SCRIPTS_DIR, '00_utils'), os.path.join(SCRIPTS_DIR, '02_pose_extraction'),
          os.path.join(SCRIPTS_DIR, '08_comparison_engine')):
    if p not in sys.path:
        sys.path.insert(0, p)

from paths import DATA_DIR  # noqa: E402
from eval_pro_clip_contact import predict_one  # noqa: E402

LABELS_PATH = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'amateur_contact_labels.jsonl')
OUT_CSV = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'amateur_contact_eval.csv')

CSV_FIELDS = [
    'clip_path', 'shot_type', 'label_source', 'label_confidence',
    'teacher_time', 'teacher_frame', 'anchor_frame',
    'pred_frame_heuristic', 'pred_time_heuristic', 'method', 'confidence',
    'err_frames_heuristic',
    'n_ball_in_window', 'n_racket_in_window', 'n_both_present',
    'error',
]


def load_labels(source_filter=None):
    if not os.path.exists(LABELS_PATH):
        return []
    rows = []
    with open(LABELS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get('skipped') or r.get('contact_frame') is None:
                continue
            if source_filter and r.get('source') != source_filter:
                continue
            rows.append(r)
    return rows


def load_done():
    if not os.path.exists(OUT_CSV):
        return set()
    with open(OUT_CSV, newline='') as f:
        return {row['clip_path'] for row in csv.DictReader(f)}


def run(limit=None, source_filter=None):
    labels = load_labels(source_filter)
    done = load_done()
    todo = [r for r in labels if r['clip_path'] not in done]
    if limit:
        todo = todo[:limit]

    print(f'{len(labels)} labelled clips | {len(done)} already done | {len(todo)} to run',
          file=sys.stderr)

    new_file = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        for i, label in enumerate(todo, 1):
            clip_path = label['clip_path']
            print(f"[{i}/{len(todo)}] {label['shot_type']} {os.path.basename(clip_path)}",
                  file=sys.stderr)
            row = {k: '' for k in CSV_FIELDS}
            row.update({
                'clip_path': clip_path, 'shot_type': label['shot_type'],
                'label_source': label.get('source', 'manual'),
                'label_confidence': label.get('confidence', ''),
                'teacher_time': label['contact_time_sec'],
            })
            if not os.path.exists(clip_path):
                row['error'] = 'clip_missing'
                w.writerow(row); f.flush()
                continue
            try:
                # predict_one() also touches entry['id'] in a diagnostic print
                # when the (dead, but not necessarily deleted from disk)
                # contact_frame_model.pkl is present -- give it something.
                entry = {'shot_type': label['shot_type'], 'id': os.path.basename(clip_path)}
                res = predict_one(entry, clip_path, anchor_mode='auto')
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                row['error'] = f'exception:{type(e).__name__}:{e}'
                w.writerow(row); f.flush()
                continue
            if 'error' in res:
                row['error'] = res['error']
                w.writerow(row); f.flush()
                continue
            fps = res['fps']
            row.update({
                'anchor_frame': res['anchor_frame'],
                'pred_frame_heuristic': res['pred_frame_heuristic'],
                'pred_time_heuristic': res['pred_time_heuristic'],
                'method': res['method'], 'confidence': res['confidence'],
                'n_ball_in_window': res['n_ball_in_window'],
                'n_racket_in_window': res['n_racket_in_window'],
                'n_both_present': res['n_both_present'],
            })
            row['teacher_frame'] = round(label['contact_time_sec'] * fps)
            row['err_frames_heuristic'] = round(res['pred_frame_heuristic'] - label['contact_time_sec'] * fps, 2)
            w.writerow(row); f.flush()

    report()


def _fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _summary(errs, label):
    errs = [e for e in errs if e is not None]
    if not errs:
        print(f'  {label}: no data')
        return
    abse = [abs(e) for e in errs]
    n = len(abse)
    within = lambda k: sum(1 for e in abse if e <= k) / n
    print(f'  {label}:  n={n}  '
          f'median|err|={statistics.median(abse):.2f}f  '
          f'mean|err|={statistics.mean(abse):.2f}f  '
          f'p90={sorted(abse)[int(0.9 * (n - 1))]:.2f}f  '
          f'bias(med)={statistics.median(errs):+.2f}f  '
          f'<=1f={within(1):.0%}  <=2f={within(2):.0%}  <=3f={within(3):.0%}')


def report():
    if not os.path.exists(OUT_CSV):
        print('no CSV yet', file=sys.stderr); return
    rows = list(csv.DictReader(open(OUT_CSV, newline='')))
    ok = [r for r in rows if not r.get('error')]
    errored = [r for r in rows if r.get('error')]

    print('\n' + '=' * 72)
    print(f'AMATEUR CONTACT-FRAME EVAL (real footage, not broadcast pro)  --  '
          f'{len(rows)} clips  ({len(ok)} scored, {len(errored)} errored)')
    print('=' * 72)
    if errored:
        from collections import Counter
        print('errors:', dict(Counter(r['error'].split(':')[0] for r in errored)))

    eh = [_fnum(r['err_frames_heuristic']) for r in ok]
    print('\nOVERALL')
    _summary(eh, 'heuristic          ')

    print('\nBY LABEL SOURCE')
    bysrc = defaultdict(list)
    for r in ok:
        bysrc[r['label_source']].append(_fnum(r['err_frames_heuristic']))
    for k in sorted(bysrc):
        _summary(bysrc[k], f'{k:<20}')

    print('\nBY METHOD')
    bym = defaultdict(list)
    for r in ok:
        key = r['method'].split('(')[0] if r['method'] else '?'
        bym[key].append(_fnum(r['err_frames_heuristic']))
    for k in sorted(bym):
        _summary(bym[k], f'{k:<20}')

    print('\nBY SHOT TYPE')
    byst = defaultdict(list)
    for r in ok:
        byst[r['shot_type']].append(_fnum(r['err_frames_heuristic']))
    for k in sorted(byst):
        _summary(byst[k], f'{k:<20}')

    fb = [r for r in ok if (r['method'].split('(')[0] if r['method'] else '?') == 'wrist_velocity_fallback']
    print(f'\nwrist_velocity_fallback (no visual evidence): {len(fb)}/{len(ok)} clips '
          f'({len(fb) / len(ok):.0%})' if ok else '')

    print('\n10 WORST (by |err|)')
    worst = sorted((r for r in ok if _fnum(r['err_frames_heuristic']) is not None),
                   key=lambda r: -abs(_fnum(r['err_frames_heuristic'])))[:10]
    for r in worst:
        print(f'  {os.path.basename(r["clip_path"]):<40} {r["shot_type"]:<9} '
              f'err={float(r["err_frames_heuristic"]):+6.1f}f  method={r["method"]:<24} '
              f'src={r["label_source"]}')
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--source', choices=['audio_pseudolabel', 'manual'])
    ap.add_argument('--report-only', action='store_true')
    args = ap.parse_args()
    if args.report_only:
        report()
        return
    run(limit=args.limit, source_filter=args.source)


if __name__ == '__main__':
    main()
