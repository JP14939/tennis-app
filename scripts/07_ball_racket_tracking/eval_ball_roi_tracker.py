"""
Evaluate ball_roi_tracker.refine_ball_track (pass 2) WITH-ROI vs WITHOUT-ROI.

The GO / NO-GO gate for wiring the ROI re-detector into any consumer (plan
stage 4). Reuses calibrate_ball_inference_scale.py's primitives (_iou,
_new_cell/_record/_finalize, shot-type join via app.db).

Datasets:
  sparse  -- the 354-row hand-drawn manual_ball_label_log_server.jsonl boxes.
             For each labelled frame: run pass-1 detection on a window of the
             source clip, run refine_ball_track, compare AT that frame.
             Headline metrics: detect_rate (up on the hard subset), mean_iou
             (must not collapse), fp_rate on ball_visible:false rows
             (HARD GATE -- must stay ~= pass-1's ~8%, fail if it rises > 2 pts).
  dense   -- consecutive-frame track labels (data/10b_ball_detection/
             dense_ball_track_labels.jsonl, built by label_dense_ball_track.py).
             Track continuity over each clip's full flight. Skipped with a
             notice if the file isn't present yet.

Usage:
  python eval_ball_roi_tracker.py --dataset sparse|dense|both [--limit N]
  python eval_ball_roi_tracker.py --calibrate-roi-imgsz   # dense set only

Output: data/07_audits/ball_roi_tracker_eval.json + a printed table.
"""
import argparse
import json
import os
import sqlite3
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
for sub in ('00_utils',):
    p = os.path.join(SCRIPTS_DIR, sub)
    if p not in sys.path:
        sys.path.insert(0, p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from paths import DATA_DIR, BACKEND_DIR  # noqa: E402
from racket_tracker import track_racket_and_ball, _center_in_original_space  # noqa: E402
import ball_roi_tracker  # noqa: E402
from ball_roi_tracker import refine_ball_track  # noqa: E402
from calibrate_ball_inference_scale import _iou, _new_cell, _record, _finalize  # noqa: E402

BALL_LABEL_LOG = os.path.join(DATA_DIR, '10b_ball_detection', 'manual_ball_label_log_server.jsonl')
CANDIDATE_META = os.path.join(DATA_DIR, '10b_ball_detection', 'candidate_frames', 'candidate_metadata.json')
DENSE_LABELS = os.path.join(DATA_DIR, '10b_ball_detection', 'dense_ball_track_labels.jsonl')
DENSE_CLIPS = os.path.join(DATA_DIR, '10b_ball_detection', 'dense_eval_clips.json')
DB_PATH = os.path.join(BACKEND_DIR, 'data', 'app.db')
OUT_PATH = os.path.join(DATA_DIR, '07_audits', 'ball_roi_tracker_eval.json')

# Window (frames each side of the labelled frame) fed to pass-1 detection --
# wide enough for the CV filter to bootstrap, narrow enough to stay cheap.
WINDOW_FRAMES = 24
TOL_PX = 40  # a track point within this of GT centre counts as "on the ball"


def _shot_type_for_analysis(conn, analysis_id, cache):
    if analysis_id in cache:
        return cache[analysis_id]
    shot_type = 'unknown'
    try:
        row = conn.execute('SELECT result_json FROM analyses WHERE id = ?', (analysis_id,)).fetchone()
        if row and row[0]:
            rj = json.loads(row[0])
            shot_type = rj.get('shot_type') or rj.get('shotType') or 'unknown'
    except Exception:  # noqa: BLE001
        pass
    cache[analysis_id] = shot_type
    return shot_type


def _box_in_original_space(box, det):
    """Full box (not just centre) mapped out of a crop, mirroring
    _center_in_original_space's scale/offset convention."""
    scale = det.get('crop_scale', 1.0) or 1.0
    x0 = det.get('crop_x0', 0)
    y0 = det.get('crop_y0', 0)
    return [x0 + box[0] / scale, y0 + box[1] / scale,
            x0 + box[2] / scale, y0 + box[3] / scale]


def _ball_box_at(dets, frame):
    for d in dets:
        if d['frame'] == frame and d.get('ball_box'):
            return _box_in_original_space(d['ball_box'], d)
    return None


def _load_sparse():
    with open(BALL_LABEL_LOG, encoding='utf-8') as f:
        rows = [json.loads(line) for line in f if line.strip()]
    with open(CANDIDATE_META, encoding='utf-8') as f:
        meta = {m['file']: m for m in json.load(f)}
    joined = []
    for r in rows:
        m = meta.get(r['file'])
        if m and os.path.exists(m['source_clip']):
            joined.append({**r, **m})
    return joined


def eval_sparse(limit=None, roi_imgsz=None):
    labels = _load_sparse()
    if limit:
        labels = labels[:limit]
    print(f'{len(labels)} labelled rows joined + source clip present', file=sys.stderr)
    conn = sqlite3.connect(DB_PATH)
    st_cache = {}

    cells = {'pass1': _new_cell(), 'roi': _new_cell()}
    # "hard subset": rows whose pass-1 misses the ball entirely
    hard = {'pass1': _new_cell(), 'roi': _new_cell()}
    gated_swaps = 0
    fp_detail = []   # ball_visible:false rows where the ROI added a box pass-1 didn't have

    # group rows by (clip, analysis) so we detect each window once
    by_clip = {}
    for row in labels:
        by_clip.setdefault(row['source_clip'], []).append(row)

    done = 0
    for clip, rows in by_clip.items():
        for row in rows:
            frame = row['frame']
            lo, hi = max(0, frame - WINDOW_FRAMES), frame + WINDOW_FRAMES
            try:
                dets, fps = track_racket_and_ball(clip, frame_range=(lo, hi))
            except Exception as e:  # noqa: BLE001
                print(f'  skip {row["file"]}: {e}', file=sys.stderr)
                continue
            if not dets:
                continue
            res = refine_ball_track(clip, dets, fps, contact_frame=frame, roi_imgsz=roi_imgsz)

            cap = cv2.VideoCapture(clip)
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            shot_type = _shot_type_for_analysis(conn, row.get('analysis_id'), st_cache)
            is_positive = bool(row.get('ball_visible')) and row.get('box_norm') is not None
            gt = None
            if is_positive:
                bn = row['box_norm']
                gt = (bn['x1'] * w, bn['y1'] * h, bn['x2'] * w, bn['y2'] * h)

            p1_box = _ball_box_at(dets, frame)
            roi_box = _ball_box_at(res.augmented_dets, frame)

            for key, box in (('pass1', p1_box), ('roi', roi_box)):
                iou = _iou(box, gt) if (box and gt) else 0.0
                _record(cells[key], shot_type, is_positive, box is not None, iou, 0.0)

            if not is_positive and roi_box is not None and p1_box is None:
                rl = [e for e in res.redetect_log if e.get('frame') == frame]
                fp_detail.append({'file': row['file'], 'bucket': row['bucket'],
                                  'shot_type': shot_type, 'frame': frame,
                                  'redetect': rl})

            if is_positive and p1_box is None:
                for key, box in (('pass1', p1_box), ('roi', roi_box)):
                    iou = _iou(box, gt) if (box and gt) else 0.0
                    _record(hard[key], shot_type, True, box is not None, iou, 0.0)
                if roi_box is not None:
                    gated_swaps += 1

            done += 1
            if done % 25 == 0:
                print(f'  {done}/{len(labels)}', file=sys.stderr)

    conn.close()
    return {
        'n_rows': len(labels),
        'window_frames': WINDOW_FRAMES,
        'aggregate': {k: _finalize(v) for k, v in cells.items()},
        'hard_subset_pass1_misses': {k: _finalize(v) for k, v in hard.items()},
        'roi_recovered_on_pass1_miss': gated_swaps,
        'fp_detail': fp_detail,
    }


def _load_dense():
    if not os.path.exists(DENSE_LABELS):
        return None, None
    with open(DENSE_LABELS, encoding='utf-8') as f:
        rows = [json.loads(line) for line in f if line.strip()]
    clips = {}
    if os.path.exists(DENSE_CLIPS):
        with open(DENSE_CLIPS, encoding='utf-8') as f:
            clips = {c['clip_id']: c for c in json.load(f)}
    return rows, clips


def eval_dense(limit=None, roi_imgsz=None):
    rows, clips = _load_dense()
    if rows is None:
        print('dense label file not present -- run label_dense_ball_track.py first; skipping dense eval',
              file=sys.stderr)
        return None

    by_clip = {}
    for r in rows:
        by_clip.setdefault(r['clip_id'], []).append(r)
    clip_ids = list(by_clip)
    if limit:
        clip_ids = clip_ids[:limit]

    per_clip = []
    for cid in clip_ids:
        labelled = sorted(by_clip[cid], key=lambda r: r['frame'])
        meta = clips.get(cid, {})
        video = meta.get('video_rel')
        if video and not os.path.isabs(video):
            video = os.path.join(DATA_DIR, video)
        if not video or not os.path.exists(video):
            print(f'  {cid}: video missing ({video})', file=sys.stderr)
            continue
        frames = [r['frame'] for r in labelled]
        lo, hi = min(frames), max(frames)
        dets, fps = track_racket_and_ball(video, frame_range=(lo - 4, hi + 4))
        contact = meta.get('contact_frame')
        res = refine_ball_track(video, dets, fps, contact_frame=contact, roi_imgsz=roi_imgsz)

        cap = cv2.VideoCapture(video)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        def _continuity(track):
            tby = {f: p for f, p in track}
            hit = 0
            vis = [r for r in labelled if r.get('ball_visible')]
            for r in vis:
                bn = r['box_norm']
                gx = (bn['x1'] + bn['x2']) / 2 * w
                gy = (bn['y1'] + bn['y2']) / 2 * h
                p = tby.get(r['frame'])
                if p and (p[0] - gx) ** 2 + (p[1] - gy) ** 2 <= TOL_PX ** 2:
                    hit += 1
            return hit / len(vis) if vis else None

        p1_track = _ball_box_track(dets)
        per_clip.append({
            'clip_id': cid,
            'n_labelled_visible': sum(1 for r in labelled if r.get('ball_visible')),
            'continuity_pass1': _continuity(p1_track),
            'continuity_roi': _continuity(res.filled_track_dense),
            'bootstrapped': res.bootstrapped,
        })

    return {'per_clip': per_clip, 'tol_px': TOL_PX}


def _ball_box_track(dets):
    return [(d['frame'], _center_in_original_space(d['ball_box'], d))
            for d in dets if d.get('ball_box')]


def calibrate_roi_imgsz(limit=None):
    grid_imgsz = [96, 128, 160, 192, 224]
    grid_upscale = [None, 128, 160, 192]
    orig_upscale = ball_roi_tracker.ROI_UPSCALE_TARGET
    out = []
    for up in grid_upscale:
        ball_roi_tracker.ROI_UPSCALE_TARGET = up
        for sz in grid_imgsz:
            r = eval_dense(limit=limit, roi_imgsz=sz)
            if r is None:
                ball_roi_tracker.ROI_UPSCALE_TARGET = orig_upscale
                print('cannot calibrate without the dense set', file=sys.stderr)
                return None
            cont = [c['continuity_roi'] for c in r['per_clip'] if c['continuity_roi'] is not None]
            out.append({'roi_imgsz': sz, 'upscale_target': up,
                        'mean_continuity': round(sum(cont) / len(cont), 4) if cont else None})
    ball_roi_tracker.ROI_UPSCALE_TARGET = orig_upscale
    out.sort(key=lambda x: (x['mean_continuity'] or 0), reverse=True)
    return {'sweep': out, 'best': out[0] if out else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset', choices=['sparse', 'dense', 'both'], default='both')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--calibrate-roi-imgsz', action='store_true')
    args = ap.parse_args()

    result = {}
    if args.calibrate_roi_imgsz:
        result['roi_imgsz_calibration'] = calibrate_roi_imgsz(limit=args.limit)
    else:
        if args.dataset in ('sparse', 'both'):
            result['sparse'] = eval_sparse(limit=args.limit)
        if args.dataset in ('dense', 'both'):
            result['dense'] = eval_dense(limit=args.limit)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(f'\nwrote {OUT_PATH}')

    sp = result.get('sparse')
    if sp:
        print('\n=== sparse: WITH-ROI vs pass-1 ===')
        for key in ('pass1', 'roi'):
            a = sp['aggregate'][key]
            print(f'  {key:6}  detect_rate={a["detect_rate"]}  mean_iou={a["mean_iou"]}  '
                  f'fp_rate={a["fp_rate"]}  (n_pos={a["n_pos"]} n_neg={a["n_neg"]})')
        print('  -- hard subset (pass-1 misses the ball) --')
        for key in ('pass1', 'roi'):
            a = sp['hard_subset_pass1_misses'][key]
            print(f'  {key:6}  detect_rate={a["detect_rate"]}  mean_iou={a["mean_iou"]}  n_pos={a["n_pos"]}')
        p1_fp = sp['aggregate']['pass1']['fp_rate'] or 0.0
        roi_fp = sp['aggregate']['roi']['fp_rate'] or 0.0
        gate = 'PASS' if roi_fp - p1_fp <= 0.02 else 'FAIL'
        print(f'\n  FP-RATE HARD GATE: pass1={p1_fp:.4f} roi={roi_fp:.4f} delta={roi_fp - p1_fp:+.4f} -> {gate}')

    dn = result.get('dense')
    if dn and dn.get('per_clip'):
        print('\n=== dense: track continuity ===')
        for c in dn['per_clip']:
            print(f'  {c["clip_id"]:20}  pass1={c["continuity_pass1"]}  roi={c["continuity_roi"]}')


if __name__ == '__main__':
    main()
