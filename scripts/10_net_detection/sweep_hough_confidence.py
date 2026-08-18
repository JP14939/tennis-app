"""
The single fixed 'base_confidence = 0.35 + player_vis * 0.3' fallback fix
turned out to be a false economy: it fixed the street-photo false-positive
bug perfectly (0/12 FP) but broke 8/9 real net photos that happen to have
no player in frame (Downloads test, this session). Since a Hough-detected
line alone can't be told apart from a street rooflines/curb within a single
frame -- player-pose corroboration was the only extra signal being used --
there's no single fixed confidence value that can win on both suites AT
ONCE if player_vis is the only lever. This sweeps a range of base_confidence
values against BOTH held-out suites combined (this session's street/hard-negative
set + the Downloads ad hoc set) and reports the real tradeoff, instead of
guessing another single number.

Detection is run ONCE per image (expensive: model + MediaPipe), then the
confidence formula is recomputed cheaply for each candidate base value --
this is what makes a full sweep fast enough to run interactively.

Usage:
  python sweep_hough_confidence.py
"""
import glob
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '05_angle_detection'))
from infer_angle import _angle_from_frame  # noqa: E402

POS_DIR_LABELED = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_dataset_v3\images\val'
NEG_DIR_STREET = r'C:\Users\jackp\tennis_app\data\10_net_detection\streettest_negatives'
POS_DIR_DOWNLOADS = os.path.expanduser('~/Downloads')
NEG_DIR_DOWNLOADS = r'C:\Users\jackp\tennis_app\data\10_net_detection\downloads_test_negatives'

MIN_CONFIDENCE = 0.5
CANDIDATE_BASES = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]


def collect_images():
    import random
    all_pos_labeled = sorted(glob.glob(os.path.join(POS_DIR_LABELED, '*.jpg')))
    random.seed(42)
    positives = random.sample(all_pos_labeled, min(12, len(all_pos_labeled)))
    negatives = sorted(glob.glob(os.path.join(NEG_DIR_STREET, '*.jpg')))
    positives += sorted(glob.glob(os.path.join(POS_DIR_DOWNLOADS, 'tennis_net*.jpg'))) + \
        sorted(glob.glob(os.path.join(POS_DIR_DOWNLOADS, 'tennis_net*.jpeg')))
    negatives += sorted(glob.glob(os.path.join(NEG_DIR_DOWNLOADS, '*.jpg')))
    return positives, negatives


def detect(path):
    frame = cv2.imread(path)
    if frame is None:
        return None
    return _angle_from_frame(frame, landmarker=None)


def main():
    positives, negatives = collect_images()
    print(f'{len(positives)} positive (has-net), {len(negatives)} negative (no-net) images, single detection pass...\n')

    cached = []  # (is_positive, used_keypoints, player_vis) for method=='hough' rows only + all keypoint rows for reference
    for is_pos, paths in ((True, positives), (False, negatives)):
        for path in paths:
            result = detect(path)
            if result is None:
                cached.append((is_pos, os.path.basename(path), None, None))
                continue
            used_keypoints = result[7]
            player_vis = result[4]
            cached.append((is_pos, os.path.basename(path), used_keypoints, player_vis))

    print(f'{"base":6} {"TP":4} {"FP":4} {"TN":4} {"FN":4} {"accuracy":9} {"FP rate":9} {"TN rate (positives=Down+street)":10}')
    print('-' * 80)
    for base in CANDIDATE_BASES:
        tp = fp = tn = fn = 0
        for is_pos, fname, used_kp, player_vis in cached:
            if used_kp is None:
                predicted_ok = False  # no detection at all -- always counted as "no net"
            elif used_kp:
                predicted_ok = True  # keypoint_model path always 0.85+, unaffected by this sweep
            else:
                conf = min(base + player_vis * 0.3, 1.0)
                predicted_ok = conf >= MIN_CONFIDENCE
            if is_pos and predicted_ok:
                tp += 1
            elif is_pos and not predicted_ok:
                fn += 1
            elif not is_pos and predicted_ok:
                fp += 1
            else:
                tn += 1
        total = tp + fp + tn + fn
        acc = (tp + tn) / total if total else 0
        fp_rate = fp / (fp + tn) if (fp + tn) else 0
        tp_rate = tp / (tp + fn) if (tp + fn) else 0
        print(f'{base:<6.2f} {tp:<4} {fp:<4} {tn:<4} {fn:<4} {acc:<9.1%} {fp_rate:<9.1%} {tp_rate:<9.1%}')


if __name__ == '__main__':
    main()
