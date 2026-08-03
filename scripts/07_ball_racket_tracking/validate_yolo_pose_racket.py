"""Visualize YOLO-pose racket keypoint predictions on validation images."""
import glob
import os
import random

import cv2
from ultralytics import YOLO

MODEL_PATH = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\yolo_pose_run\weights\best.pt'
VAL_IMAGES_DIR = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\yolo_pose_dataset\images\val'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\yolo_pose_validation_viz'

POINTS = ['handle', 'throat', 'tip', 'left_edge', 'right_edge']
COLORS = [(0, 0, 255), (0, 165, 255), (0, 255, 0), (255, 0, 0), (255, 0, 255)]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    model = YOLO(MODEL_PATH)

    val_images = glob.glob(os.path.join(VAL_IMAGES_DIR, '*.jpg'))
    random.seed(3)
    sample = random.sample(val_images, min(10, len(val_images)))

    for img_path in sample:
        img = cv2.imread(img_path)
        results = model.predict(img, verbose=False)
        vis = img.copy()

        if len(results[0].keypoints) > 0:
            kpts = results[0].keypoints.xy[0].cpu().numpy()
            for i, (x, y) in enumerate(kpts):
                cv2.circle(vis, (int(x), int(y)), 6, COLORS[i % len(COLORS)], -1)

        out_path = os.path.join(OUT_DIR, f'pred_{os.path.basename(img_path)}')
        cv2.imwrite(out_path, vis)
        print(f'{os.path.basename(img_path)} -> {out_path}')


if __name__ == '__main__':
    main()
