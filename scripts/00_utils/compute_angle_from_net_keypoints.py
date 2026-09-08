"""
Compute horizontal + vertical camera angle from net keypoints (4 points:
net_top_left, net_top_right, left_post_base, right_post_base) -- either
straight from hand labels (sanity-checking the geometry itself) or from the
trained YOLO-pose net-keypoint model's predictions on a video (the actual
production path).

Horizontal: reuses infer_angle.py's exact existing formula/constant
(net_angle = degrees(acos(net_width / FULL_NET_FRACTION))) -- only the point
source changes (verified points instead of a heuristic-guessed line).

Vertical: same style of foreshortening ratio, calibrated from whichever
labeled examples are visually confirmed level (the Court-Level-Tennis-style
ones), the same way FULL_NET_FRACTION itself was originally calibrated.

Usage:
  python compute_angle_from_net_keypoints.py labels   # sanity-check against hand labels
  python compute_angle_from_net_keypoints.py model <video_path>  # run trained model on a video
  python compute_angle_from_net_keypoints.py angle-error --labels <testset_labels.json>
      # per-frame |horizontal_angle(GT corners) - horizontal_angle(v10 corners)|,
      # median / p90 overall and by predicted angle_label bucket. Isolates the
      # corner-localisation error's contribution to the angle from the
      # FULL_NET_FRACTION calibration error (the constant is the same on both
      # sides of the subtraction). Target: median <= 5 deg, p90 <= 12 deg.
"""
import argparse
import json
import math
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import (
    FULL_NET_FRACTION, NET_KEYPOINT_IMGSZ, NET_KEYPOINT_NAMES, angle_label,
)

LABELS_PATH = r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_v2.json'
MODEL_PATH = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_run_v10\weights\best.pt'
TESTSET_LABELS_PATH = r'C:\Users\jackp\tennis_app\data\10_net_detection\net_keypoint_testset_v1\net_keypoint_testset_v1_labels.json'

# Frame files whose source is one of the 2 known-elevated real videos --
# everything else in the labeled set comes from pro source footage.
KNOWN_ELEVATED_PREFIXES = ('mark_vs_silas', 'nicolas_vs_florian')

FRAME_W, FRAME_H = 1920, 1080


def horizontal_angle(net_top_left, net_top_right, frame_w=FRAME_W):
    net_width = abs(net_top_right[0] - net_top_left[0]) / frame_w
    apparent_ratio = min(net_width / FULL_NET_FRACTION, 1.0)
    return round(math.degrees(math.acos(max(apparent_ratio, 0.001))), 1)


def height_ratio(net_top_left, net_top_right, post_base, frame_h=FRAME_H):
    """Post height as a fraction of frame height, measured from the net-top
    line down to the post base -- the raw vertical signal, not yet an angle."""
    net_top_y = (net_top_left[1] + net_top_right[1]) / 2
    return abs(post_base[1] - net_top_y) / frame_h


def from_labels():
    with open(LABELS_PATH) as f:
        data = json.load(f)
    usable = [item for item in data['labels'] if item['usable']]

    pro_ratios, elevated_ratios = [], []
    print(f"{'frame':<40} {'h_angle':>8} {'height_ratio':>13}  group")
    for item in usable:
        kp = item['keypoints']
        if kp['net_top_left'] is None or kp['net_top_right'] is None:
            continue
        h_angle = horizontal_angle(kp['net_top_left'], kp['net_top_right'])

        ratios = []
        for base_key in ('left_post_base', 'right_post_base'):
            if kp[base_key] is not None:
                ratios.append(height_ratio(kp['net_top_left'], kp['net_top_right'], kp[base_key]))
        ratio = sum(ratios) / len(ratios) if ratios else None

        is_elevated = item['frame_file'].startswith(KNOWN_ELEVATED_PREFIXES)
        group = 'ELEVATED' if is_elevated else 'pro'
        if ratio is not None:
            (elevated_ratios if is_elevated else pro_ratios).append(ratio)
        print(f"{item['frame_file']:<40} {h_angle:>8} {ratio if ratio is None else round(ratio,4):>13}  {group}")

    print('\n=== Height-ratio distributions (ground truth labels) ===')
    if pro_ratios:
        print(f'pro group:      n={len(pro_ratios)} mean={sum(pro_ratios)/len(pro_ratios):.4f} '
              f'min={min(pro_ratios):.4f} max={max(pro_ratios):.4f}')
    if elevated_ratios:
        print(f'elevated group: n={len(elevated_ratios)} mean={sum(elevated_ratios)/len(elevated_ratios):.4f} '
              f'min={min(elevated_ratios):.4f} max={max(elevated_ratios):.4f}')
    if pro_ratios and elevated_ratios:
        pro_mean = sum(pro_ratios) / len(pro_ratios)
        gap = (pro_mean - sum(elevated_ratios) / len(elevated_ratios)) / pro_mean * 100
        print(f'\nElevated group height-ratio is {gap:.1f}% {"lower" if gap > 0 else "higher"} than pro mean.')


_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        from ultralytics import YOLO
        _MODEL = YOLO(MODEL_PATH)
    return _MODEL


def predict_keypoints(frame):
    """v10-aware: returns {name: (x, y)} in pixels for whichever of
    NET_KEYPOINT_NAMES the loaded checkpoint emits (2 for v10, 4 for v4)."""
    model = _get_model()
    results = model.predict(frame, verbose=False, imgsz=NET_KEYPOINT_IMGSZ)
    if len(results[0].keypoints) == 0 or results[0].keypoints.xy.shape[1] == 0:
        return {}
    kpts = results[0].keypoints.xy[0].cpu().numpy()
    return {n: (float(kpts[i][0]), float(kpts[i][1]))
            for i, n in enumerate(NET_KEYPOINT_NAMES[:kpts.shape[0]])
            if not (kpts[i][0] == 0 and kpts[i][1] == 0)}


def from_model(video_path):
    import cv2

    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print('Could not read frame')
        return

    h, w = frame.shape[:2]
    kp = predict_keypoints(frame)
    if not kp:
        print('No net detected by model')
        return
    print(f'Predicted keypoints: {kp}')

    if 'net_top_left' in kp and 'net_top_right' in kp:
        h_angle = horizontal_angle(kp['net_top_left'], kp['net_top_right'], frame_w=w)
        print(f'Horizontal angle: {h_angle}')
        for base_key in ('left_post_base', 'right_post_base'):
            if base_key in kp:
                ratio = height_ratio(kp['net_top_left'], kp['net_top_right'], kp[base_key], frame_h=h)
                print(f'Height ratio ({base_key}): {ratio:.4f}')


def _pctl(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, int(round(q * (len(xs) - 1))))
    return xs[i]


def angle_error_mode(labels_path):
    """Per-frame |horizontal_angle(GT) - horizontal_angle(v10 pred)|."""
    import cv2

    with open(labels_path) as f:
        data = json.load(f)
    rows = data['labels'] if isinstance(data, dict) else data
    frames_dir = os.path.join(os.path.dirname(labels_path), 'frames')

    per_bucket = {}          # predicted angle_label -> [ |dAngle| ]
    all_errs = []
    n_gt_missing = n_pred_missing = n_frame_missing = 0

    for r in rows:
        if not r.get('usable') or r.get('no_net'):
            continue
        kp = r['keypoints']
        if not kp.get('net_top_left') or not kp.get('net_top_right'):
            n_gt_missing += 1
            continue
        fp = os.path.join(frames_dir, r['frame_file'])
        frame = cv2.imread(fp)
        if frame is None:
            n_frame_missing += 1
            continue
        w = r.get('img_w') or frame.shape[1]

        pred = predict_keypoints(frame)
        if 'net_top_left' not in pred or 'net_top_right' not in pred:
            n_pred_missing += 1
            continue

        gt_a = horizontal_angle(kp['net_top_left'], kp['net_top_right'], frame_w=w)
        pred_a = horizontal_angle(pred['net_top_left'], pred['net_top_right'], frame_w=w)
        err = abs(gt_a - pred_a)
        all_errs.append(err)
        per_bucket.setdefault(angle_label(gt_a), []).append(err)

    print(f'\n=== angle-error: |horizontal_angle(GT) - horizontal_angle(v10)| ===')
    print(f'frames scored: {len(all_errs)}   '
          f'(GT corners missing: {n_gt_missing}, v10 no-detect: {n_pred_missing}, frame file missing: {n_frame_missing})')
    if all_errs:
        med, p90 = _pctl(all_errs, 0.5), _pctl(all_errs, 0.9)
        print(f'  overall   n={len(all_errs):>3}  median={med:5.1f} deg   p90={p90:5.1f} deg   '
              f'max={max(all_errs):5.1f}   [target: median<=5, p90<=12]')
    print('  by GT angle_label bucket:')
    for label, errs in sorted(per_bucket.items()):
        print(f'    {label:<18} n={len(errs):>3}  median={_pctl(errs,0.5):5.1f}   p90={_pctl(errs,0.9):5.1f}')
    print('\n  NOTE: no per-view bucket -- the testset has no view_direction label. '
          'Coarse-view-bucketed eval waits on 0c fence footage (item 7.2).')


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'labels'
    if mode == 'labels':
        from_labels()
    elif mode == 'model' and len(sys.argv) >= 3:
        from_model(sys.argv[2])
    elif mode == 'angle-error':
        ap = argparse.ArgumentParser()
        ap.add_argument('--labels', default=TESTSET_LABELS_PATH)
        args = ap.parse_args(sys.argv[2:])
        labels = args.labels
        if not os.path.isabs(labels) and not os.path.exists(labels):
            # allow a bare filename living next to the default testset
            cand = os.path.join(os.path.dirname(TESTSET_LABELS_PATH), labels)
            labels = cand if os.path.exists(cand) else labels
        angle_error_mode(labels)
    else:
        print(__doc__)
