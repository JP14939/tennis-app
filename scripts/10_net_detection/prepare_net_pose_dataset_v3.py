"""
Build the YOLO-pose net-keypoint dataset from the merged v2 + v3 label sets
(48 + 98 = 146 labeled frames, 24 + 83 = 107 usable). Same structure as
prepare_net_pose_dataset_v2.py -- this just reads two label files / frame
dirs instead of one.
"""
import json
import os
import random
import shutil

import cv2

SOURCES = [
    (r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_v2.json',
     r'C:\Users\jackp\tennis_app\data\10_net_detection\own_footage_frames_v2'),
    (r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_v3.json',
     r'C:\Users\jackp\tennis_app\data\10_net_detection\own_footage_frames_v3'),
]
DATASET_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_dataset_v3'

POINTS = ['net_top_left', 'net_top_right', 'left_post_base', 'right_post_base']
PAD_FRAC = 0.15
VAL_FRAC = 0.2

random.seed(9)


def main():
    for split in ['train', 'val']:
        os.makedirs(os.path.join(DATASET_DIR, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, 'labels', split), exist_ok=True)

    usable = []
    for labels_path, frames_dir in SOURCES:
        with open(labels_path) as f:
            data = json.load(f)
        for item in data['labels']:
            if item['usable']:
                usable.append((item, frames_dir))

    random.shuffle(usable)
    n_val = max(6, int(len(usable) * VAL_FRAC))
    splits = {'val': usable[:n_val], 'train': usable[n_val:]}

    counts = {}
    for split, items in splits.items():
        n = 0
        for item, frames_dir in items:
            img_path = os.path.join(frames_dir, item['frame_file'])
            img = cv2.imread(img_path)
            if img is None:
                continue
            h, w = img.shape[:2]

            present = {p: item['keypoints'][p] for p in POINTS if item['keypoints'].get(p) is not None}
            if 'net_top_left' not in present or 'net_top_right' not in present:
                continue

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

            out_img = os.path.join(DATASET_DIR, 'images', split, item['frame_file'])
            out_lbl = os.path.join(DATASET_DIR, 'labels', split, item['frame_file'].replace('.jpg', '.txt'))
            shutil.copy(img_path, out_img)
            with open(out_lbl, 'w') as f:
                f.write(line)
            n += 1
        counts[split] = n

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

    print(f'Train: {counts["train"]}, Val: {counts["val"]}')
    print(f'Dataset written to {DATASET_DIR}')


if __name__ == '__main__':
    main()
