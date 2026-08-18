"""
Build the YOLO-pose net-keypoint dataset from v2+v3 positives + v1 negatives
(same as v4) PLUS, new in v5, a batch of manually-labeled "empty court, no
player" positives (net_geometry_labels_stock_v1.json).

Why: v4 fixed the false-positive bug (retrained on real negatives) but a
follow-up test (this session, user's own Downloads photos: 9 real tennis
nets, no player in any of them) found the model only reliably recognizes a
net directly when a PLAYER is also in frame -- because every existing
positive label (own_footage_frames_v2/v3) comes from real swing footage,
which always has one. 13 new positives (4 from previously-unused sourced
stock photos, 9 from the user's own test images) specifically target that
gap: empty courts, stock/architectural photography, no swinging player.

Also fixes a latent bug in v3/v4's label-filename derivation
(`.replace('.jpg', '.txt')`) which silently produces a wrong label filename
for any .jpeg source (two of the new stock images are .jpeg) -- switched to
os.path.splitext, like write_negative() already correctly does.
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
    (r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_stock_v1.json',
     r'C:\Users\jackp\tennis_app\data\10_net_detection\stock_frames_v1'),
]
NEGATIVE_SOURCE = (
    r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_negatives_v1.json',
    r'C:\Users\jackp\tennis_app\data\10_net_detection\net_negatives_v1\raw',
)
DATASET_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_dataset_v5'

POINTS = ['net_top_left', 'net_top_right', 'left_post_base', 'right_post_base']
PAD_FRAC = 0.15
VAL_FRAC = 0.2

random.seed(9)


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
            out_lbl = os.path.join(DATASET_DIR, 'labels', split, os.path.splitext(item['frame_file'])[0] + '.txt')
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
