"""
Eval: how accurate is the automatic contact-frame predictor on the pro
clips that already have a trustworthy HUMAN contact mark?

Every pro-database entry ships with clip_contact_time_sec = 1.001 (a fixed
placeholder, never a real per-clip detection -- see
backfill_contact_frame_log_from_verdicts.py's note). Jack's Pro Clip Review
pass has since hand-marked the real contact frame on ~197 of them
('contact_time_corrected' / 'label_confirmed' verdicts in
data/06_pro_database/clip_review_log.jsonl).

This script runs the SAME contact pipeline the live app uses --
  find_peak_wrist_frame (anchor)  ->  track_racket_and_ball  ->
  find_contact_frame  ->  (optional) contact_frame_model.pkl offset
-- on each of those clips and compares its prediction to the human mark.

If the heuristic is accurate enough on this footage, the "fix contact time"
step can be dropped from the review entirely (Jack would only exclude bad
videos / relabel shot types), and the pro DB's contact times can be
auto-filled from the predictor instead of the 1.001 placeholder.

Read-only w.r.t. pro_database.json. Writes:
  data/07_ball_racket_tracking/eval_pro_clip_contact.csv   (one row per clip, resumable)
and prints an aggregate report at the end (also available standalone via
--report-only).

Usage:
  python eval_pro_clip_contact.py [--limit N] [--only ID[,ID...]] [--report-only]
"""
import argparse
import csv
import json
import os
import statistics
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE,
          os.path.join(SCRIPTS_DIR, '00_utils'),
          os.path.join(SCRIPTS_DIR, '02_pose_extraction'),
          os.path.join(SCRIPTS_DIR, '08_comparison_engine')):
    if p not in sys.path:
        sys.path.insert(0, p)

from paths import DATA_DIR  # noqa: E402
from clip_urls import PRO_CLIPS_DIR  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
REVIEW_LOG_PATH = os.path.join(DATA_DIR, '06_pro_database', 'clip_review_log.jsonl')
POSE_CACHE_DIR = os.path.join(DATA_DIR, '07_ball_racket_tracking', '.eval_pose_cache')
OUT_CSV = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'eval_pro_clip_contact.csv')

# find_contact_frame only looks within +-0.3s of the anchor; a little extra
# margin so the window has detections at its edges. Restricting YOLO to this
# range instead of the whole clip is ~3x faster with no effect on the result.
TRACK_MARGIN_SEC = 0.8

CSV_FIELDS = [
    'id', 'shot_type', 'camera_angle', 'fps',
    'teacher_time', 'teacher_frame',
    'anchor_frame',
    'pred_frame_heuristic', 'pred_time_heuristic', 'method', 'confidence',
    'model_offset', 'model_available',
    'pred_frame_model', 'pred_time_model',
    'err_frames_heuristic', 'err_frames_model',
    'n_ball_in_window', 'n_racket_in_window', 'n_both_present',
    'error',
]


def teacher_labels():
    """{entry_id: (teacher_time_sec, verdict)} for entries whose LATEST review
    verdict means a human actually pinned the contact frame. For an entry
    corrected more than once, the teacher is the most recent 'new' value."""
    latest = {}
    corrected = {}
    with open(REVIEW_LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            latest[r['entry_id']] = r['verdict']
            if r['verdict'] == 'contact_time_corrected' and r.get('note') and '->' in r['note']:
                try:
                    corrected[r['entry_id']] = float(r['note'].split('->')[1].strip().rstrip('s'))
                except ValueError:
                    pass

    db = json.load(open(PRO_DB_PATH))
    by_id = {e['id']: e for e in db['entries']}

    out = {}
    for eid, verdict in latest.items():
        if eid not in by_id:
            continue
        if verdict == 'contact_time_corrected' and eid in corrected:
            out[eid] = (corrected[eid], verdict)
        elif verdict == 'label_confirmed':
            t = by_id[eid].get('clip_contact_time_sec')
            if t is not None:
                out[eid] = (float(t), verdict)
    return out, by_id


def _landmarks_by_name(frame):
    """extract_poses.py stores landmarks as a list of {name,x,y,z,visibility};
    find_peak_wrist_frame wants a name->dict mapping (compare_swing's inline
    form). None stays None."""
    lm = frame.get('landmarks')
    if not lm:
        return None
    return {d['name']: d for d in lm}


def get_or_extract_poses(clip_path):
    os.makedirs(POSE_CACHE_DIR, exist_ok=True)
    key = os.path.splitext(os.path.basename(clip_path))[0]
    cache_path = os.path.join(POSE_CACHE_DIR, f'{key}_poses.json')
    if not os.path.exists(cache_path):
        import contextlib
        from extract_poses import extract_poses
        with contextlib.redirect_stdout(sys.stderr):
            extract_poses(clip_path, cache_path, sample_every=3)
    with open(cache_path) as f:
        return json.load(f)


def predict_one(entry, clip_path, teacher_anchor_frame=None):
    """Runs the live contact pipeline on one clip. Returns a dict of the
    fields the CSV needs, or {'error': '...'} on any failure. If
    teacher_anchor_frame is given, the wrist-velocity anchor search is
    bypassed and find_contact_frame refines from that frame instead -- an
    upper bound on what the refinement alone can do given a perfect anchor."""
    from compare_swing import find_peak_wrist_frame
    import racket_tracker as rt
    from racket_tracker import find_contact_frame, contact_frame_meta

    pose_data = get_or_extract_poses(clip_path)
    raw_frames = pose_data.get('frames') or []
    frames = [{'frame': fr['frame'], 'landmarks': _landmarks_by_name(fr)} for fr in raw_frames]
    if not any(f['landmarks'] for f in frames):
        return {'error': 'no_pose_detected'}

    if teacher_anchor_frame is not None:
        anchor_frame = int(teacher_anchor_frame)
    else:
        anchor_idx = find_peak_wrist_frame(frames, pose_data.get('fps') or 30.0)
        anchor_frame = frames[anchor_idx]['frame']

    detections, fps = rt.track_racket_and_ball(
        clip_path,
        frame_range=(int(anchor_frame - TRACK_MARGIN_SEC * (pose_data.get('fps') or 30.0)),
                     int(anchor_frame + TRACK_MARGIN_SEC * (pose_data.get('fps') or 30.0))),
    )
    if not fps or fps <= 0:
        fps = pose_data.get('fps') or 30.0

    frame, conf, method = find_contact_frame(detections, anchor_frame, fps)
    cf_meta = contact_frame_meta(detections, anchor_frame, fps)

    model_offset, model_available = 0, False
    try:
        from train_contact_frame_model import predict_contact_offset, OUTLIER_FRAMES
        raw_offset, avail = predict_contact_offset({
            'student_method': method, 'student_confidence': conf,
            'fps': fps, 'student_meta': cf_meta, 'source': 'user_submitted',
        })
        # The shipped contact_frame_model.pkl was trained on only 75 rows with
        # 4 of its 12 features all-NaN -- it extrapolates to absurd offsets
        # (10000+ frames) on this footage. Treat anything past the trainer's
        # own sanity bound as "model not usable here".
        if avail and abs(raw_offset) <= OUTLIER_FRAMES:
            model_offset, model_available = raw_offset, True
        elif avail:
            print(f'  [{entry["id"]}] model offset {raw_offset}f out of range -- ignored',
                  file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f'  [{entry["id"]}] model offset skipped: {e}', file=sys.stderr)

    return {
        'fps': round(fps, 4),
        'anchor_frame': anchor_frame,
        'pred_frame_heuristic': frame,
        'pred_time_heuristic': round(frame / fps, 4),
        'method': method,
        'confidence': conf,
        'model_offset': model_offset,
        'model_available': int(bool(model_available)),
        'pred_frame_model': frame + model_offset,
        'pred_time_model': round((frame + model_offset) / fps, 4),
        'n_ball_in_window': cf_meta.get('n_ball_detections_in_window'),
        'n_racket_in_window': cf_meta.get('n_racket_detections_in_window'),
        'n_both_present': cf_meta.get('n_both_present'),
    }


def load_done():
    if not os.path.exists(OUT_CSV):
        return {}
    with open(OUT_CSV, newline='') as f:
        return {row['id']: row for row in csv.DictReader(f)}


def run(limit=None, only=None, anchor='wrist'):
    global OUT_CSV
    if anchor == 'teacher':
        OUT_CSV = OUT_CSV.replace('.csv', '_teacher_anchor.csv')
    labels, by_id = teacher_labels()
    if only:
        labels = {k: v for k, v in labels.items() if k in only}
    done = load_done()
    todo = [eid for eid in labels if eid not in done]
    todo.sort()
    if limit:
        todo = todo[:limit]

    print(f'{len(labels)} teacher-labelled entries | {len(done)} already done | {len(todo)} to run',
          file=sys.stderr)

    new_file = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        for i, eid in enumerate(todo, 1):
            entry = by_id[eid]
            teacher_time, verdict = labels[eid]
            clip_path = os.path.join(PRO_CLIPS_DIR, entry['clip_path'])
            print(f'[{i}/{len(todo)}] {eid}  ({entry["shot_type"]})', file=sys.stderr)
            row = {k: '' for k in CSV_FIELDS}
            row.update({
                'id': eid, 'shot_type': entry['shot_type'],
                'camera_angle': entry.get('camera_angle'),
                'teacher_time': round(teacher_time, 4),
            })
            if not os.path.exists(clip_path):
                row['error'] = 'clip_missing'
                w.writerow(row); f.flush()
                continue
            try:
                ta = round(teacher_time * 60.0) if anchor == 'teacher' else None
                if anchor == 'teacher':
                    # refine fps first from a cheap probe via the pose cache
                    pd = get_or_extract_poses(clip_path)
                    ta = round(teacher_time * (pd.get('fps') or 60.0))
                res = predict_one(entry, clip_path, teacher_anchor_frame=ta)
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
            row.update(res)
            fps = res['fps']
            row['teacher_frame'] = round(teacher_time * fps)
            row['err_frames_heuristic'] = round(res['pred_frame_heuristic'] - teacher_time * fps, 2)
            row['err_frames_model'] = round(res['pred_frame_model'] - teacher_time * fps, 2)
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
    print(f'PRO-CLIP CONTACT-FRAME EVAL  --  {len(rows)} clips  ({len(ok)} scored, {len(errored)} errored)')
    print('=' * 72)
    if errored:
        from collections import Counter
        print('errors:', dict(Counter(r['error'].split(':')[0] for r in errored)))

    eh = [_fnum(r['err_frames_heuristic']) for r in ok]
    em = [_fnum(r['err_frames_model']) for r in ok]
    print('\nOVERALL')
    _summary(eh, 'heuristic          ')
    _summary(em, 'heuristic + model  ')

    print('\nBY METHOD (heuristic)')
    from collections import defaultdict
    bym = defaultdict(list)
    for r in ok:
        key = r['method'].split('(')[0] if r['method'] else '?'
        bym[key].append(_fnum(r['err_frames_heuristic']))
    for k in sorted(bym):
        _summary(bym[k], f'{k:<20}')

    print('\nBY SHOT TYPE (heuristic)')
    byst = defaultdict(list)
    for r in ok:
        byst[r['shot_type']].append(_fnum(r['err_frames_heuristic']))
    for k in sorted(byst):
        _summary(byst[k], f'{k:<20}')

    print('\nBY CAMERA ANGLE (heuristic)')
    bands = [(0, 20), (20, 35), (35, 50), (50, 90)]
    byca = defaultdict(list)
    for r in ok:
        a = _fnum(r['camera_angle'])
        band = next((f'{lo}-{hi}' for lo, hi in bands if a is not None and lo <= a < hi), 'unknown')
        byca[band].append(_fnum(r['err_frames_heuristic']))
    for k in sorted(byca):
        _summary(byca[k], f'{k:<20}')

    print('\n10 WORST (by |heuristic err|)')
    worst = sorted((r for r in ok if _fnum(r['err_frames_heuristic']) is not None),
                   key=lambda r: -abs(_fnum(r['err_frames_heuristic'])))[:10]
    for r in worst:
        print(f'  {r["id"]:<16} {r["shot_type"]:<9} err={float(r["err_frames_heuristic"]):+6.1f}f  '
              f'method={r["method"]:<24} conf={r["confidence"]}  '
              f'teacher={r["teacher_time"]}s pred={r["pred_time_heuristic"]}s  '
              f'ball/racket in win={r["n_ball_in_window"]}/{r["n_racket_in_window"]}')
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--only', help='comma-separated entry ids')
    ap.add_argument('--report-only', action='store_true')
    ap.add_argument('--anchor', choices=['wrist', 'teacher'], default='wrist')
    args = ap.parse_args()
    global OUT_CSV
    if args.anchor == 'teacher' and args.report_only:
        OUT_CSV = OUT_CSV.replace('.csv', '_teacher_anchor.csv')
    if args.report_only:
        report()
        return
    only = set(args.only.split(',')) if args.only else None
    run(limit=args.limit, only=only, anchor=args.anchor)


if __name__ == '__main__':
    main()
