"""
Evaluate near-court cropped ball detection vs the current live config.

Three regimes on the 354 human-labelled phone frames
(`manual_ball_label_log_server.jsonl`, 250 with a box / 104 negatives):
  A@320 -- raw full frame at imgsz 320  (what the live path does today)
  B     -- crop to the player pose bbox + upscale to 640  (regime-B winner
           from calibrate_ball_inference_scale.py; measured but offline-only)
  C     -- near-court crop (player + racket + cone toward the net line),
           near_court_ball_tracker._near_court_crop_rect

Adds a NEAR / FAR split: a labelled ball is "near" if its box-centre y is
below the detected net line (image-y > net_y). The near side is the target;
the far side is left to physics (ball_speed extrapolation), not detection.

Output: data/07_audits/near_court_ball_detection.json + a printed table.
GO bar (near side): C detect_rate >= A@320 + 0.05, mean_iou >= 0.55,
fp_rate <= 0.12, near_side_coverage >= 0.95, crop_fallback_rate <= 0.20,
negative fp_rate <= A@320 + 0.03.

Usage: python eval_near_court_ball_detection.py [--limit N]
"""
import argparse
import json
import os
import sqlite3
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
for _sub in ('00_utils', '05_angle_detection'):
    _p = os.path.join(SCRIPTS_DIR, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from paths import DATA_DIR, BACKEND_DIR  # noqa: E402
from calibrate_ball_inference_scale import (  # noqa: E402
    _load_labels, _iou, _new_cell, _record, _finalize, _crop_and_upscale,
    _landmarks_for_frame, _shot_type_for_analysis, _predict_best_box, CANDIDATE_FRAMES_DIR,
)
from racket_tracker import get_ball_model  # noqa: E402
from infer_angle import create_landmarker, detect_net_endpoints_keypoints  # noqa: E402
from near_court_ball_tracker import (  # noqa: E402
    _near_court_crop_rect, _crop_and_upscale_rect, tight_player_bbox,
)

OUT_PATH = os.path.join(DATA_DIR, '07_audits', 'near_court_ball_detection.json')
DB_PATH = os.path.join(BACKEND_DIR, 'data', 'app.db')

A_IMGSZ = 320
SWEEP = [192, 224, 288, 384]


def _crop_gt(gt_native, scale, x0, y0):
    gx0, gy0, gx1, gy1 = gt_native
    return ((gx0 - x0) * scale, (gy0 - y0) * scale, (gx1 - x0) * scale, (gy1 - y0) * scale)


def _box_inside(gt_native, rect):
    gx0, gy0, gx1, gy1 = gt_native
    rx0, ry0, rx1, ry1 = rect
    return gx0 >= rx0 and gy0 >= ry0 and gx1 <= rx1 and gy1 <= ry1


def near_or_far(gt_center_y_norm, net_y_norm):
    """A labelled ball is NEAR when its centre is below the net line in the
    image (image-y increases downward, so a larger y == closer to the camera
    in a 'back' view). net_y_norm None -> 'near_unknownnet'."""
    if net_y_norm is None:
        return 'near_unknownnet'
    return 'near' if gt_center_y_norm > net_y_norm else 'far'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    labels = _load_labels()
    if args.limit:
        labels = labels[:args.limit]
    print(f'{len(labels)} labelled rows', file=sys.stderr)

    model = get_ball_model()
    if model is None:
        sys.exit('No fine-tuned ball model -- run train_ball_detector.py first.')
    landmarker = create_landmarker()
    conn = sqlite3.connect(DB_PATH)
    st_cache = {}

    # cells[regime][imgsz][side] -> _new_cell()
    cells = {'A': {A_IMGSZ: {}}, 'B': {sz: {} for sz in SWEEP}, 'C': {sz: {} for sz in SWEEP}}

    def cell(regime, sz, side):
        return cells[regime][sz].setdefault(side, _new_cell())

    net_undetected = 0
    c_fallback = 0
    c_attempts = 0
    coverage_hit = coverage_total = 0

    for i, row in enumerate(labels):
        path = os.path.join(CANDIDATE_FRAMES_DIR, row['bucket'], row['file'])
        frame = cv2.imread(path)
        if frame is None:
            continue
        h, w = frame.shape[:2]
        shot_type = _shot_type_for_analysis(conn, row.get('analysis_id'), st_cache)
        is_positive = bool(row.get('ball_visible')) and row.get('box_norm') is not None

        gt_native = None
        gt_cy_norm = None
        if is_positive:
            bn = row['box_norm']
            gt_native = (bn['x1'] * w, bn['y1'] * h, bn['x2'] * w, bn['y2'] * h)
            gt_cy_norm = (bn['y1'] + bn['y2']) / 2

        net = detect_net_endpoints_keypoints(frame)
        if net is None:
            net_undetected += 1
        side = 'neg'
        if is_positive:
            side = near_or_far(gt_cy_norm, net[2] if net is not None else None)

        landmarks = _landmarks_for_frame(frame, landmarker)

        # -- Regime A@320 --
        box, conf = _predict_best_box(model, frame, A_IMGSZ)
        iou = _iou(box, gt_native) if (box and gt_native) else 0.0
        _record(cell('A', A_IMGSZ, side), shot_type, is_positive, box is not None, iou, conf or 0.0)

        # -- Regime B: pose-bbox crop --
        cropped = _crop_and_upscale(frame, landmarks) if landmarks else None
        if cropped is not None:
            crop, scale, x0, y0 = cropped
            gt_crop = _crop_gt(gt_native, scale, x0, y0) if gt_native else None
            for sz in SWEEP:
                b, c = _predict_best_box(model, crop, sz)
                iou = _iou(b, gt_crop) if (b and gt_crop) else 0.0
                _record(cell('B', sz, side), shot_type, is_positive, b is not None, iou, c or 0.0)

        # -- Regime C: near-court crop --
        rect = None
        if landmarks:
            pbb = tight_player_bbox(landmarks, w, h)
            net_y_px = net[2] * h if net is not None else None
            net_l = net[0] * w if net is not None else None
            net_r = net[1] * w if net is not None else None
            rect = _near_court_crop_rect(pbb, net_y_px, net_l, net_r, 'back', w, h)
        c_attempts += 1
        if rect is None:
            c_fallback += 1
        else:
            if is_positive and side == 'near':
                coverage_total += 1
                if _box_inside(gt_native, rect):
                    coverage_hit += 1
            cu = _crop_and_upscale_rect(frame, rect)
            if cu is not None:
                crop, scale, x0, y0 = cu
                gt_crop = _crop_gt(gt_native, scale, x0, y0) if gt_native else None
                for sz in SWEEP:
                    b, c = _predict_best_box(model, crop, sz)
                    iou = _iou(b, gt_crop) if (b and gt_crop) else 0.0
                    _record(cell('C', sz, side), shot_type, is_positive, b is not None, iou, c or 0.0)

        if (i + 1) % 50 == 0:
            print(f'  {i + 1}/{len(labels)}', file=sys.stderr)

    conn.close()

    results = {
        r: {sz: {side: _finalize(c) for side, c in by_side.items()}
            for sz, by_side in by_sz.items()}
        for r, by_sz in cells.items()
    }
    out = {
        'results': results,
        'net_undetected': net_undetected,
        'n_rows': len(labels),
        'crop_fallback_rate': round(c_fallback / c_attempts, 4) if c_attempts else None,
        'near_side_coverage': round(coverage_hit / coverage_total, 4) if coverage_total else None,
        'near_side_coverage_n': coverage_total,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    print(f'\nwrote {OUT_PATH}')

    def line(regime, sz, side):
        r = results.get(regime, {}).get(sz, {}).get(side)
        if not r:
            return f'  {regime}@{sz:<4} {side:18} (no data)'
        return (f'  {regime}@{sz:<4} {side:18} detect={r["detect_rate"]}  iou={r["mean_iou"]}  '
                f'fp={r["fp_rate"]}  n_pos={r["n_pos"]} n_neg={r["n_neg"]}')

    print('\n=== NEAR side ===')
    print(line('A', A_IMGSZ, 'near'))
    for sz in SWEEP:
        print(line('B', sz, 'near'))
    for sz in SWEEP:
        print(line('C', sz, 'near'))
    print('\n=== FAR side ===')
    print(line('A', A_IMGSZ, 'far'))
    for sz in SWEEP:
        print(line('C', sz, 'far'))
    print('\n=== negatives (fp_rate) ===')
    print(line('A', A_IMGSZ, 'neg'))
    for sz in SWEEP:
        print(line('C', sz, 'neg'))
    print(f'\ncrop_fallback_rate={out["crop_fallback_rate"]}  '
          f'near_side_coverage={out["near_side_coverage"]} (n={coverage_total})  '
          f'net_undetected={net_undetected}/{len(labels)}')


if __name__ == '__main__':
    main()
