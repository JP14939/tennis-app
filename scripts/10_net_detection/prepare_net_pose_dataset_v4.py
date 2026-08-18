"""
Build the YOLO-pose net-keypoint dataset from the v2+v3 positive label sets
PLUS, new in v4, real negative ("no tennis net here") examples confirmed by
Claude (net_presence_verifier.py / label_negatives_with_claude.py).

prepare_net_pose_dataset_v3.py has no path for a negative example at all --
it silently `continue`s past anything missing both net_top_left/net_top_right
(line 56-58), which is exactly what a genuine "no net" label looks like.
YOLO supports background images natively via an empty label .txt file (zero
object lines) -- this is the standard way to teach a detector "nothing here"
instead of forcing it to always guess a location. That's the actual fix:
without any negative examples, the model was proven this session to
false-positive on 100% of tested non-tennis images.
"""
import json
import os
import random
import shutil

import cv2

POSITIVE_SOURCES = [
    (r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_v2.json',
     r'C:\Users\jackp\tennis_app\data\10_net_detection\own_footage_frames_v2'),
    (r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_v3.json',
     r'C:\Users\jackp\tennis_app\data\10_net_detection\own_footage_frames_v3'),
]
NEGATIVE_SOURCE = (
    r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_negatives_v1.json',
    r'C:\Users\jackp\tennis_app\data\10_net_detection\net_negatives_v1\raw',
)
DATASET_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_dataset_v4'

POINTS = ['net_top_left', 'net_top_right', 'left_post_base', 'right_post_base']
PAD_FRAC = 0.15
VAL_FRAC = 0.2

random.seed(9)  # same seed as v3 -- positive train/val split stays identical, only negatives are new


def write_positive(item, frames_dir, out_img, out_lbl):
    img_path = os.path.join(frames_dir, item['frame_file'])
    img = cv2.imread(img_path)
    if img is None:
        return False
    h, w = img.shape[:2]

    present = {p: item['keypoints'][p] for p in POINTS if item['keypoints'].get(p) is not None}
    if 'net_top_left' not in present or 'net_top_right' not in present:
        return False

    clamped = {p: (min(max(pt[0], 0), w - 1), min(max(pt[1], 0), h - 1)) for p, pt in present.items()}
    xs = [pt[0] for pt in clamped.values()]
    ys = [pt[1] for pt in clamped.values()]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    pad_x, pad_y = (x2 - x1) * PAD_FRAC, max((y2 - y1) * PAD_FRAC, 10)
    x1, x2 = max(0, x1 - pad_x), min(w, x2 + pad_x)
    y1, y2 = max(0, y1 - pad_y), min(h, y2 + pad_y)

    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
    bw, bh = (x2 - x1) / w, (y2 - y1) / h

    kp_str = ''
    for p in POINTS:
        if p in clamped:
            kx, ky = clamped[p]
            kp_str += f' {kx / w:.6f} {ky / h:.6f} 2'
        else:
            kp_str += ' 0.000000 0.000000 0'

    line = f'0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}{kp_str}\n'
    shutil.copy(img_path, out_img)
    with open(out_lbl, 'w') as f:
        f.write(line)
    return True


def write_negative(item, frames_dir, out_img, out_lbl):
    """A confirmed no-net image: copy it in with an EMPTY label file (zero
    object lines) -- YOLO's standard background-image convention, teaching
    the model this image contains no instance of the 'net' class at all."""
    img_path = os.path.join(frames_dir, item['frame_file'])
    img = cv2.imread(img_path)
    if img is None:
        return False
    shutil.copy(img_path, out_img)
    open(out_lbl, 'w').close()
    return True


def main():
    for split in ['train', 'val']:
        os.makedirs(os.path.join(DATASET_DIR, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, 'labels', split), exist_ok=True)

    usable_positives = []
    for labels_path, frames_dir in POSITIVE_SOURCES:
        with open(labels_path) as f:
            data = json.load(f)
        for item in data['labels']:
            if item['usable']:
                usable_positives.append((item, frames_dir))

    neg_labels_path, neg_frames_dir = NEGATIVE_SOURCE
    with open(neg_labels_path) as f:
        neg_data = json.load(f)
    confirmed_negatives = [(item, neg_frames_dir) for item in neg_data['labels']
                            if item.get('has_tennis_net') is False]

    random.shuffle(usable_positives)
    random.shuffle(confirmed_negatives)

    n_val_pos = max(6, int(len(usable_positives) * VAL_FRAC))
    n_val_neg = max(2, int(len(confirmed_negatives) * VAL_FRAC))
    pos_splits = {'val': usable_positives[:n_val_pos], 'train': usable_positives[n_val_pos:]}
    neg_splits = {'val': confirmed_negatives[:n_val_neg], 'train': confirmed_negatives[n_val_neg:]}

    counts = {}
    for split in ['train', 'val']:
        n_pos = n_neg = 0
        for item, frames_dir in pos_splits[split]:
            out_img = os.path.join(DATASET_DIR, 'images', split, item['frame_file'])
            out_lbl = os.path.join(DATASET_DIR, 'labels', split, item['frame_file'].replace('.jpg', '.txt'))
            if write_positive(item, frames_dir, out_img, out_lbl):
                n_pos += 1
        for item, frames_dir in neg_splits[split]:
            out_img = os.path.join(DATASET_DIR, 'images', split, item['frame_file'])
            out_lbl = os.path.join(DATASET_DIR, 'labels', split, os.path.splitext(item['frame_file'])[0] + '.txt')
            if write_negative(item, frames_dir, out_img, out_lbl):
                n_neg += 1
        counts[split] = {'positive': n_pos, 'negative': n_neg}

    yaml_content = f"""path: {DATASET_DIR}
train: images/train
val: images/val

kpt_shape: [4, 3]
flip_idx: [1, 0, 3, 2]

names:
  0: net
"""
    with open(os.path.join(DATASET_DIR, 'data.yaml'), 'w') as f:
        f.write(yaml_content)

    print(f'Train: {counts["train"]["positive"]} positive + {counts["train"]["negative"]} negative')
    print(f'Val:   {counts["val"]["positive"]} positive + {counts["val"]["negative"]} negative')
    print(f'Dataset written to {DATASET_DIR}')


if __name__ == '__main__':
    main()
