"""
Run the real net-detection pipeline (infer_angle.py's _angle_from_frame --
the same function check_camera_setup.py's video path calls per-sampled-frame)
against a labeled set of net/no-net STATIC IMAGES, to measure false positives
like the one a friend hit: a street photo with no net at all coming back
"net detected OK".

Positives: sampled from the v3 YOLO-pose validation set (real swing frames,
all contain a net) -- data/10_net_detection/yolo_pose_dataset_v3/images/val.
Negatives: street/urban photos with no tennis net anywhere --
data/10_net_detection/streettest_negatives (see source_street_negatives.py).

For a static image there's no "3 sampled frames" to median across the way
infer_camera_angle() does for a real video -- this script treats each image
as if it were a video made of 3 identical copies of that one frame (the
natural degenerate case: width_spread = 0), which lets it reuse the exact
same confidence formula check_camera_setup.py's video path uses instead of
reimplementing it.

Usage:
  python test_net_detector_labeled_set.py
"""
import glob
import math
import os
import random
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
import infer_angle
from infer_angle import _angle_from_frame, angle_label, FULL_NET_FRACTION  # noqa: E402

POS_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_dataset_v3\images\val'
NEG_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\streettest_negatives'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\streettest_results'
N_POSITIVES = 12
MIN_CONFIDENCE = 0.5  # mirrors check_camera_setup.py's MIN_CONFIDENCE


def evaluate_image(path):
    """Mirrors infer_camera_angle()'s single-video decision, degenerate case
    of one distinct frame (spread=0). Returns a dict shaped like
    check_camera_setup()'s result, plus debug fields."""
    frame = cv2.imread(path)
    if frame is None:
        return {'ok': False, 'angle': None, 'confidence': 0.0, 'method': 'unreadable', 'message': 'unreadable image'}

    result = _angle_from_frame(frame, landmarker=None)
    if result is None:
        return {'ok': False, 'angle': None, 'confidence': 0.0, 'method': 'none',
                'message': "Couldn't find the net in your video — try the fence-mount guide for a clearer shot."}

    (net_width, net_center_x, net_y, player_x, player_vis, post_height_frac, ankle_y,
     used_keypoints, height_ratio, stance_width_ratio, shoulder_tilt_deg, _net_roll) = result

    apparent_ratio = min(net_width / FULL_NET_FRACTION, 1.0)
    net_angle = math.degrees(math.acos(max(apparent_ratio, 0.001)))
    net_angle = max(0.0, min(90.0, net_angle))

    player_angle = None
    if player_x is not None:
        offset = abs(player_x - net_center_x)
        MAX_SIDE_OFFSET = 0.40
        offset_ratio = min(offset / MAX_SIDE_OFFSET, 1.0)
        player_angle = math.degrees(math.asin(offset_ratio))
        player_angle = max(0.0, min(90.0, player_angle))

    net_weight = 2.0
    player_weight = player_vis if player_angle is not None else 0.0
    if player_angle is not None and player_weight > 0:
        angle_deg = (net_angle * net_weight + player_angle * player_weight) / (net_weight + player_weight)
    else:
        angle_deg = net_angle
    angle_deg = round(max(0.0, min(90.0, angle_deg)), 1)

    # Degenerate single-frame case of infer_camera_angle()'s formula:
    # width_spread = 0 across the (identical) "3 samples", so spread_penalty = 0.
    # Mirrors infer_camera_angle()'s current formula (base 0.35 for the Hough
    # fallback, lowered this session -- see infer_angle.py).
    base_confidence = 0.85 if used_keypoints else 0.35
    confidence = round(min(base_confidence + player_vis * 0.3, 1.0), 3)

    method = 'keypoint_model' if used_keypoints else 'hough_heuristic'

    if confidence < MIN_CONFIDENCE:
        return {'ok': False, 'angle': angle_deg, 'confidence': confidence, 'method': method,
                'message': f"Camera setup looks uncertain ({angle_label(angle_deg)}, low confidence) — see the fence-mount guide.",
                'net_box': (net_center_x - net_width / 2, net_y, net_center_x + net_width / 2, net_y)}

    return {'ok': True, 'angle': angle_deg, 'confidence': confidence, 'method': method,
            'message': f'Net detected OK ({angle_label(angle_deg)}).',
            'net_box': (net_center_x - net_width / 2, net_y, net_center_x + net_width / 2, net_y)}


def annotate_and_save(path, result, out_path):
    img = cv2.imread(path)
    h, w = img.shape[:2]
    if result.get('net_box'):
        lx, y, rx, _ = result['net_box']
        cv2.line(img, (int(lx * w), int(y * h)), (int(rx * w), int(y * h)), (0, 0, 255), 3)
    label = f"ok={result['ok']} conf={result['confidence']:.2f} method={result['method']}"
    cv2.putText(img, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.imwrite(out_path, img)


def main():
    if len(sys.argv) > 1:
        # Point the shared infer_angle module at a different net-keypoint
        # model run (e.g. yolo_pose_run_v4) instead of its hardcoded
        # default -- lets this script A/B two model versions without
        # duplicating any of the detection logic itself.
        override_path = sys.argv[1]
        infer_angle.NET_KEYPOINT_MODEL_PATH = override_path
        infer_angle._net_kp_model = None  # drop any cached model from a prior run
        print(f'Using net-keypoint model: {override_path}\n')
        run_out_dir = OUT_DIR + '_' + os.path.basename(os.path.dirname(os.path.dirname(override_path)))
    else:
        print(f'Using default net-keypoint model: {infer_angle.NET_KEYPOINT_MODEL_PATH}\n')
        run_out_dir = OUT_DIR + '_default'

    os.makedirs(run_out_dir, exist_ok=True)

    all_positives = sorted(glob.glob(os.path.join(POS_DIR, '*.jpg')))
    random.seed(42)
    positives = random.sample(all_positives, min(N_POSITIVES, len(all_positives)))
    negatives = sorted(glob.glob(os.path.join(NEG_DIR, '*.jpg'))) + sorted(glob.glob(os.path.join(NEG_DIR, '*.jpeg')))

    print(f'{len(positives)} positive (has-net) images, {len(negatives)} negative (no-net) images\n')

    rows = []
    for label, paths in (('net', positives), ('no_net', negatives)):
        for path in paths:
            result = evaluate_image(path)
            rows.append((label, os.path.basename(path), result))

    print(f'{"label":8} {"file":45} {"ok":6} {"conf":6} {"method":16} message')
    print('-' * 110)
    tp = fp = tn = fn = 0
    misclassified = []
    for label, fname, r in rows:
        print(f'{label:8} {fname:45} {str(r["ok"]):6} {r["confidence"]:<6.2f} {r["method"]:16} {r["message"][:50]}')
        is_net_truth = (label == 'net')
        predicted_net = r['ok']
        if is_net_truth and predicted_net:
            tp += 1
        elif is_net_truth and not predicted_net:
            fn += 1
            misclassified.append((label, fname, r))
        elif not is_net_truth and predicted_net:
            fp += 1
            misclassified.append((label, fname, r))
        else:
            tn += 1

    total = len(rows)
    print('\n--- Summary ---')
    print(f'Total: {total}  |  True positives: {tp}  True negatives: {tn}  '
          f'False positives (no-net image reported as net!): {fp}  False negatives: {fn}')
    if (tp + fp) > 0 or fp > 0 or len([r for l, f, r in rows if l == 'no_net']) > 0:
        neg_total = len([1 for l, _, _ in rows if l == 'no_net'])
        if neg_total:
            print(f'False positive rate on no-net images: {fp}/{neg_total} = {fp / neg_total:.1%}')
    pos_total = len([1 for l, _, _ in rows if l == 'net'])
    if pos_total:
        print(f'True positive rate on net images: {tp}/{pos_total} = {tp / pos_total:.1%}')

    if misclassified:
        print(f'\nSaving {len(misclassified)} misclassified images to {run_out_dir}...')
        src_dirs = {'net': POS_DIR, 'no_net': NEG_DIR}
        for label, fname, r in misclassified:
            src_path = os.path.join(src_dirs[label], fname)
            out_path = os.path.join(run_out_dir, f'MISCLASSIFIED_{label}_{fname}')
            annotate_and_save(src_path, r, out_path)
            print(f'  {out_path}')
    else:
        print('\nNo misclassifications.')


if __name__ == '__main__':
    main()
