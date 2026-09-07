"""
Calibrates the ball detector's YOLO `imgsz` inference parameter against real
hand-labelled ground truth, instead of relying on ultralytics' implicit
default (confirmed this session to be a real bug -- see racket_tracker.py's
detect_ball()/track_racket_and_ball() for the fix this informs).

Ground truth: data/10b_ball_detection/manual_ball_label_log_server.jsonl
(354 rows, 250 with a real hand-drawn box_norm), joined to
candidate_frames/candidate_metadata.json (frame/fps/source_clip/analysis_id)
and to backend/data/app.db's analyses.result_json.shot_type via analysis_id,
for a shot-type-stratified result. (The much smaller manual_ball_label_log.jsonl,
without the _server suffix, is a separate 18-row local stub -- not used here.)

Tests three regimes, since the model is scale-sensitive to matching its
training conditions (imgsz=320 on ~28x29px boxes), not simply "bigger image
= better" -- confirmed empirically inconsistent across naive choices:
  A  -- raw label frame as-is (native 1920x1080)
  A2 -- raw label frame downscaled to 640x360 (phone/amateur-style uploads)
  B  -- pose-cropped + upscaled, mirroring verify_shot_contact.py's
        _crop_and_upscale() exactly (crop_to_subject._frame_bbox + the same
        UPSCALE_TARGET_PX=640 target)

Metric: IoU against the real ground-truth box for ball_visible=True rows;
false-positive rate for ball_visible=False rows. Not a rate/confidence
proxy -- real boxes exist locally, so use them.

Usage:
  python calibrate_ball_inference_scale.py [--limit N]

Output: data/07_audits/ball_imgsz_calibration.json + a printed summary table.
"""
import argparse
import json
import os
import sqlite3
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
for sub in ('00_utils', '02_pose_extraction', '05_angle_detection', '12_video_crop'):
    p = os.path.join(SCRIPTS_DIR, sub)
    if p not in sys.path:
        sys.path.insert(0, p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from paths import DATA_DIR, BACKEND_DIR  # noqa: E402
from racket_tracker import get_ball_model, CONF_THRESHOLD  # noqa: E402
from crop_to_subject import _frame_bbox, MARGIN  # noqa: E402
from infer_angle import create_landmarker, _run_landmarker  # noqa: E402
import mediapipe as mp  # noqa: E402
from mediapipe.tasks import python as mp_python  # noqa: E402
from mediapipe.tasks.python import vision as mp_vision  # noqa: E402

BALL_LABEL_LOG = os.path.join(DATA_DIR, '10b_ball_detection', 'manual_ball_label_log_server.jsonl')
CANDIDATE_META = os.path.join(DATA_DIR, '10b_ball_detection', 'candidate_frames', 'candidate_metadata.json')
CANDIDATE_FRAMES_DIR = os.path.join(DATA_DIR, '10b_ball_detection', 'candidate_frames')
DB_PATH = os.path.join(BACKEND_DIR, 'data', 'app.db')
OUT_PATH = os.path.join(DATA_DIR, '07_audits', 'ball_imgsz_calibration.json')

UPSCALE_TARGET_PX = 640  # matches verify_shot_contact.py's UPSCALE_TARGET_PX exactly

REGIME_A_IMGSZ = [320, 640, 960, 1280, 1600, 1920]
REGIME_A2_IMGSZ = [320, 480, 640]
REGIME_B_IMGSZ = [160, 224, 320, 480, 640]
REGIME_A2_SIZE = (640, 360)  # (w, h)

MOST_DETECT_RATE_TOLERANCE = 0.02  # within 2 points of the best -> prefer the smaller/cheaper imgsz


def _load_labels():
    with open(BALL_LABEL_LOG, encoding='utf-8') as f:
        rows = [json.loads(line) for line in f if line.strip()]
    with open(CANDIDATE_META, encoding='utf-8') as f:
        meta = {m['file']: m for m in json.load(f)}
    joined = []
    for r in rows:
        m = meta.get(r['file'])
        if m is None:
            continue
        joined.append({**r, **m})
    return joined


def _shot_type_for_analysis(conn, analysis_id, cache):
    if analysis_id in cache:
        return cache[analysis_id]
    shot_type = 'unknown'
    try:
        row = conn.execute('SELECT result_json FROM analyses WHERE id = ?', (analysis_id,)).fetchone()
        if row and row[0]:
            rj = json.loads(row[0])
            shot_type = rj.get('shot_type') or rj.get('shotType') or 'unknown'
    except Exception:  # noqa: BLE001 -- best-effort enrichment, never fatal
        pass
    cache[analysis_id] = shot_type
    return shot_type


def _iou(box_a, box_b):
    ax0, ay0, ax1, ay1 = box_a
    bx0, by0, bx1, by1 = box_b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _predict_best_box(model, image, imgsz, conf=CONF_THRESHOLD):
    results = model.predict(image, conf=conf, imgsz=imgsz, verbose=False)
    best_box, best_conf = None, None
    for box in results[0].boxes:
        c = float(box.conf[0])
        if best_conf is None or c > best_conf:
            best_box, best_conf = box.xyxy[0].tolist(), c
    return best_box, best_conf


def _landmarks_for_frame(frame, landmarker):
    result = _run_landmarker(frame, landmarker)
    if result is None:
        return None
    return [
        {'name': None, 'x': lm.x, 'y': lm.y, 'z': lm.z, 'visibility': lm.visibility}
        for lm in result
    ]


def _crop_and_upscale(frame, landmarks):
    """Mirrors verify_shot_contact.py's _crop_and_upscale exactly (same
    MARGIN via crop_to_subject._frame_bbox, same UPSCALE_TARGET_PX) so
    regime B's numbers transfer directly to that code path."""
    h, w = frame.shape[:2]
    bbox = _frame_bbox(landmarks, w, h)
    if bbox is None:
        return None
    x0, y0, x1, y1 = [int(round(v)) for v in bbox]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = frame[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    scale = UPSCALE_TARGET_PX / max(cw, ch) if max(cw, ch) < UPSCALE_TARGET_PX else 1.0
    if scale != 1.0:
        crop = cv2.resize(crop, (max(1, int(cw * scale)), max(1, int(ch * scale))))
    return crop, scale, x0, y0


def _new_cell():
    return {'n_pos': 0, 'n_pos_evaluable': 0, 'detected': 0, 'iou_sum': 0.0, 'conf_sum': 0.0,
            'n_neg': 0, 'fp': 0, 'by_shot_type': {}}


def _record(cell, shot_type, is_positive, detected, iou, conf):
    st = cell['by_shot_type'].setdefault(shot_type, _new_cell())
    for c in (cell, st):
        if is_positive:
            c['n_pos'] += 1
            c['n_pos_evaluable'] += 1
            if detected:
                c['detected'] += 1
                c['iou_sum'] += iou
                c['conf_sum'] += conf
        else:
            c['n_neg'] += 1
            if detected:
                c['fp'] += 1


def _finalize(cell):
    out = {
        'n_pos': cell['n_pos'],
        'detect_rate': round(cell['detected'] / cell['n_pos_evaluable'], 4) if cell['n_pos_evaluable'] else None,
        'mean_iou': round(cell['iou_sum'] / cell['detected'], 4) if cell['detected'] else None,
        'mean_conf': round(cell['conf_sum'] / cell['detected'], 4) if cell['detected'] else None,
        'n_neg': cell['n_neg'],
        'fp_rate': round(cell['fp'] / cell['n_neg'], 4) if cell['n_neg'] else None,
    }
    out['by_shot_type'] = {st: _finalize(c) for st, c in cell['by_shot_type'].items()}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None, help='cap on labelled rows processed, for a quick run')
    args = ap.parse_args()

    labels = _load_labels()
    if args.limit:
        labels = labels[:args.limit]
    print(f'{len(labels)} labelled rows joined to metadata', file=sys.stderr)

    model = get_ball_model()
    if model is None:
        sys.exit('No fine-tuned ball model found -- run train_ball_detector.py first.')

    landmarker = create_landmarker()
    conn = sqlite3.connect(DB_PATH)
    shot_type_cache = {}

    cells = {
        'A': {sz: _new_cell() for sz in REGIME_A_IMGSZ},
        'A2': {sz: _new_cell() for sz in REGIME_A2_IMGSZ},
        'B': {sz: _new_cell() for sz in REGIME_B_IMGSZ},
    }
    skipped_no_pose = 0
    skipped_gt_outside_crop = 0

    for i, row in enumerate(labels):
        path = os.path.join(CANDIDATE_FRAMES_DIR, row['bucket'], row['file'])
        frame = cv2.imread(path)
        if frame is None:
            continue
        h, w = frame.shape[:2]
        shot_type = _shot_type_for_analysis(conn, row.get('analysis_id'), shot_type_cache)
        is_positive = bool(row.get('ball_visible')) and row.get('box_norm') is not None

        gt_box_native = None
        if is_positive:
            bn = row['box_norm']
            gt_box_native = (bn['x1'] * w, bn['y1'] * h, bn['x2'] * w, bn['y2'] * h)

        # -- Regime A: raw frame, native resolution --
        for sz in REGIME_A_IMGSZ:
            box, conf = _predict_best_box(model, frame, sz)
            iou = _iou(box, gt_box_native) if (box and gt_box_native) else 0.0
            _record(cells['A'][sz], shot_type, is_positive, box is not None, iou, conf or 0.0)

        # -- Regime A2: downscaled frame (box_norm still applies unchanged --
        # aspect ratio preserved, normalized coords are resolution-independent) --
        frame_small = cv2.resize(frame, REGIME_A2_SIZE)
        sw, sh = REGIME_A2_SIZE
        gt_box_small = None
        if is_positive:
            bn = row['box_norm']
            gt_box_small = (bn['x1'] * sw, bn['y1'] * sh, bn['x2'] * sw, bn['y2'] * sh)
        for sz in REGIME_A2_IMGSZ:
            box, conf = _predict_best_box(model, frame_small, sz)
            iou = _iou(box, gt_box_small) if (box and gt_box_small) else 0.0
            _record(cells['A2'][sz], shot_type, is_positive, box is not None, iou, conf or 0.0)

        # -- Regime B: pose-cropped + upscaled --
        landmarks = _landmarks_for_frame(frame, landmarker)
        cropped = _crop_and_upscale(frame, landmarks) if landmarks else None
        if cropped is None:
            skipped_no_pose += 1
        else:
            crop, scale, x0, y0 = cropped
            gt_box_crop = None
            gt_outside = False
            if is_positive:
                gx0, gy0, gx1, gy1 = gt_box_native
                gt_box_crop = ((gx0 - x0) * scale, (gy0 - y0) * scale, (gx1 - x0) * scale, (gy1 - y0) * scale)
                ch, cw = crop.shape[:2]
                if gx1 < x0 or gy1 < y0 or gx0 > x0 + cw / scale or gy0 > y0 + ch / scale:
                    gt_outside = True
                    skipped_gt_outside_crop += 1
            if not gt_outside:
                for sz in REGIME_B_IMGSZ:
                    box, conf = _predict_best_box(model, crop, sz)
                    iou = _iou(box, gt_box_crop) if (box and gt_box_crop) else 0.0
                    _record(cells['B'][sz], shot_type, is_positive, box is not None, iou, conf or 0.0)

        if (i + 1) % 50 == 0:
            print(f'  {i + 1}/{len(labels)} processed', file=sys.stderr)

    conn.close()
    print(f'skipped (no pose found, regime B only): {skipped_no_pose}', file=sys.stderr)
    print(f'skipped (ground-truth ball outside crop, regime B only): {skipped_gt_outside_crop}', file=sys.stderr)

    results = {regime: {sz: _finalize(cell) for sz, cell in by_sz.items()} for regime, by_sz in cells.items()}

    # -- Recommendation: best detect_rate per regime, then the smallest
    # imgsz within tolerance of it (avoid paying latency for a marginal gain) --
    recommendation = {}
    for regime, by_sz in results.items():
        rated = [(sz, r['detect_rate']) for sz, r in by_sz.items() if r['detect_rate'] is not None]
        if not rated:
            continue
        best_rate = max(r for _, r in rated)
        candidates = [sz for sz, r in rated if r >= best_rate - MOST_DETECT_RATE_TOLERANCE]
        recommendation[regime] = {
            'chosen_imgsz': min(candidates),
            'best_detect_rate': round(best_rate, 4),
            'within_tolerance_candidates': sorted(candidates),
        }

    out = {'results': results, 'recommendation': recommendation,
           'skipped_no_pose': skipped_no_pose, 'skipped_gt_outside_crop': skipped_gt_outside_crop,
           'n_rows': len(labels)}
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    print(f'\nwrote {OUT_PATH}')

    print('\n=== Recommendation ===')
    for regime, rec in recommendation.items():
        print(f'  regime {regime}: imgsz={rec["chosen_imgsz"]} '
              f'(detect_rate={rec["best_detect_rate"]}, candidates={rec["within_tolerance_candidates"]})')

    print('\n=== Summary (aggregate, not per-shot-type) ===')
    for regime, by_sz in results.items():
        print(f'-- regime {regime} --')
        for sz, r in by_sz.items():
            print(f'  imgsz={sz:<5} detect_rate={r["detect_rate"]}  mean_iou={r["mean_iou"]}  '
                  f'mean_conf={r["mean_conf"]}  fp_rate={r["fp_rate"]}  n_pos={r["n_pos"]} n_neg={r["n_neg"]}')


if __name__ == '__main__':
    main()
