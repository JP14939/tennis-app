"""
Convert our vision-labeled racket keypoints (labels.json) into YOLO-pose
training format: images/{train,val}/*.jpg + labels/{train,val}/*.txt (one
box + 5 keypoints per line, all normalised 0-1) + data.yaml.

Bounding box is derived from the keypoints themselves (min/max + padding)
since we don't have a separate box annotation — the crops are already
tightly framed around the racket.
"""
import json
import os
import random
import shutil

import cv2

LABELS_PATH = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\labels.json'
CROPS_DIR = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\crops'
DATASET_DIR = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\yolo_pose_dataset'

POINTS = ['handle', 'throat', 'tip', 'left_edge', 'right_edge']
PAD_FRAC = 0.12
VAL_FRAC = 0.15

random.seed(9)


def main():
    for split in ['train', 'val']:
        os.makedirs(os.path.join(DATASET_DIR, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, 'labels', split), exist_ok=True)

    with open(LABELS_PATH) as f:
        data = json.load(f)
    usable = [item for item in data['labels'] if item['usable']]
    random.shuffle(usable)
    n_val = max(10, int(len(usable) * VAL_FRAC))
    splits = {'val': usable[:n_val], 'train': usable[n_val:]}

    counts = {}
    for split, items in splits.items():
        n = 0
        for item in items:
            img_path = os.path.join(CROPS_DIR, item['crop_file'])
            img = cv2.imread(img_path)
            if img is None:
                continue
            h, w = img.shape[:2]

            # Clamp keypoints into the image bounds first — some labeled
            # points were extrapolated slightly past the crop edge for
            # partially cut-off features, which YOLO rejects outright as
            # corrupt labels (silently dropping ~1/3 of examples otherwise)
            clamped = {p: (min(max(item['keypoints'][p][0], 0), w - 1),
                           min(max(item['keypoints'][p][1], 0), h - 1)) for p in POINTS}

            xs = [clamped[p][0] for p in POINTS]
            ys = [clamped[p][1] for p in POINTS]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            pad_x, pad_y = (x2 - x1) * PAD_FRAC, (y2 - y1) * PAD_FRAC
            x1, x2 = max(0, x1 - pad_x), min(w, x2 + pad_x)
            y1, y2 = max(0, y1 - pad_y), min(h, y2 + pad_y)

            cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
            bw, bh = (x2 - x1) / w, (y2 - y1) / h

            kp_str = ''
            for p in POINTS:
                kx, ky = clamped[p]
                kp_str += f' {kx / w:.6f} {ky / h:.6f} 2'  # visibility=2 (visible)

            line = f'0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}{kp_str}\n'

            out_img = os.path.join(DATASET_DIR, 'images', split, item['crop_file'])
            out_lbl = os.path.join(DATASET_DIR, 'labels', split, item['crop_file'].replace('.jpg', '.txt'))
            shutil.copy(img_path, out_img)
            with open(out_lbl, 'w') as f:
                f.write(line)
            n += 1
        counts[split] = n

    yaml_content = f"""path: {DATASET_DIR}
train: images/train
val: images/val

kpt_shape: [5, 3]
flip_idx: [0, 1, 2, 4, 3]

names:
  0: racket
"""
    with open(os.path.join(DATASET_DIR, 'data.yaml'), 'w') as f:
        f.write(yaml_content)

    print(f'Train: {counts["train"]}, Val: {counts["val"]}')
    print(f'Dataset written to {DATASET_DIR}')


if __name__ == '__main__':
    main()
