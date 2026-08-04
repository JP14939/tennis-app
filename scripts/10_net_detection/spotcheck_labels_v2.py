"""
Draw Claude's hand-labeled net keypoints back onto their frames so they can
be visually verified before becoming YOLO-pose training data -- same
"verify before trusting" discipline used throughout today's session.
"""
import json
import os
import random

import cv2

LABELS_PATH = r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_v2.json'
FRAMES_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\own_footage_frames_v2'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\label_spotcheck_v2'

COLORS = {
    'net_top_left': (0, 255, 0),
    'net_top_right': (0, 165, 255),
    'left_post_base': (255, 0, 0),
    'right_post_base': (0, 0, 255),
}

if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(LABELS_PATH) as f:
        data = json.load(f)
    usable = [item for item in data['labels'] if item['usable']]
    random.seed(3)
    sample = random.sample(usable, min(8, len(usable)))

    for item in sample:
        img_path = os.path.join(FRAMES_DIR, item['frame_file'])
        img = cv2.imread(img_path)
        if img is None:
            continue
        for name, pt in item['keypoints'].items():
            if pt is None:
                continue
            cv2.circle(img, (int(pt[0]), int(pt[1])), 10, COLORS[name], -1)
        out_path = os.path.join(OUT_DIR, item['frame_file'])
        cv2.imwrite(out_path, img)
        print(f"{item['frame_file']} -> {out_path}")
