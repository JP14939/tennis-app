"""Visualize YOLO-pose net keypoint predictions on validation images."""
import glob
import os

import cv2
from ultralytics import YOLO

MODEL_PATH = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_run_v2\weights\best.pt'
VAL_IMAGES_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_dataset_v2\images\val'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_validation_viz_v2'

POINTS = ['net_top_left', 'net_top_right', 'left_post_base', 'right_post_base']
COLORS = [(0, 255, 0), (0, 165, 255), (255, 0, 0), (0, 0, 255)]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    model = YOLO(MODEL_PATH)

    val_images = glob.glob(os.path.join(VAL_IMAGES_DIR, '*.jpg'))
    for img_path in val_images:
        img = cv2.imread(img_path)
        results = model.predict(img, verbose=False)
        vis = img.copy()

        if len(results[0].keypoints) > 0 and results[0].keypoints.xy.shape[1] > 0:
            kpts = results[0].keypoints.xy[0].cpu().numpy()
            confs = results[0].keypoints.conf[0].cpu().numpy() if results[0].keypoints.conf is not None else None
            for i, (x, y) in enumerate(kpts):
                if x == 0 and y == 0:
                    continue
                cv2.circle(vis, (int(x), int(y)), 10, COLORS[i % len(COLORS)], -1)
                label = POINTS[i] + (f' {confs[i]:.2f}' if confs is not None else '')
                cv2.putText(vis, label, (int(x) + 12, int(y)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS[i % len(COLORS)], 2)

        out_path = os.path.join(OUT_DIR, f'pred_{os.path.basename(img_path)}')
        cv2.imwrite(out_path, vis)
        print(f'{os.path.basename(img_path)} -> {out_path}')


if __name__ == '__main__':
    main()
