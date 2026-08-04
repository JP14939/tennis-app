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
"""
import json
import math
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import FULL_NET_FRACTION

LABELS_PATH = r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_v2.json'
MODEL_PATH = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_run_v2\weights\best.pt'

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


def from_model(video_path):
    import cv2
    from ultralytics import YOLO

    model = YOLO(MODEL_PATH)
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print('Could not read frame')
        return

    h, w = frame.shape[:2]
    results = model.predict(frame, verbose=False)
    if len(results[0].keypoints) == 0 or results[0].keypoints.xy.shape[1] == 0:
        print('No net detected by model')
        return

    kpts = results[0].keypoints.xy[0].cpu().numpy()
    names = ['net_top_left', 'net_top_right', 'left_post_base', 'right_post_base']
    kp = {n: tuple(kpts[i]) for i, n in enumerate(names) if not (kpts[i][0] == 0 and kpts[i][1] == 0)}
    print(f'Predicted keypoints: {kp}')

    if 'net_top_left' in kp and 'net_top_right' in kp:
        h_angle = horizontal_angle(kp['net_top_left'], kp['net_top_right'], frame_w=w)
        print(f'Horizontal angle: {h_angle}')
        for base_key in ('left_post_base', 'right_post_base'):
            if base_key in kp:
                ratio = height_ratio(kp['net_top_left'], kp['net_top_right'], kp[base_key], frame_h=h)
                print(f'Height ratio ({base_key}): {ratio:.4f}')


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] == 'labels':
        from_labels()
    elif sys.argv[1] == 'model' and len(sys.argv) >= 3:
        from_model(sys.argv[2])
    else:
        print(__doc__)
