"""Visualize predicted keypoints on a few crops to sanity-check the trained model."""
import json
import os

import cv2
import numpy as np
import torch

from train_racket_keypoints import build_model, IMG_SIZE, POINTS, IMAGENET_MEAN, IMAGENET_STD, CROPS_DIR, LABELS_PATH, MODEL_OUT

COLORS = {
    'handle': (0, 0, 255), 'throat': (0, 165, 255), 'tip': (0, 255, 0),
    'left_edge': (255, 0, 0), 'right_edge': (255, 0, 255),
}
OUT_DIR = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\validation_viz'


def predict(model, img):
    resized = cv2.resize(img, (IMG_SIZE, IMG_SIZE))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    t = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
    for c in range(3):
        t[c] = (t[c] - IMAGENET_MEAN[c]) / IMAGENET_STD[c]
    with torch.no_grad():
        pred = model(t.unsqueeze(0))[0].numpy()
    h, w = img.shape[:2]
    points = {}
    for i, name in enumerate(POINTS):
        points[name] = (int(pred[i * 2] * w), int(pred[i * 2 + 1] * h))
    return points


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    model = build_model()
    model.load_state_dict(torch.load(MODEL_OUT))
    model.eval()

    with open(LABELS_PATH) as f:
        labels = json.load(f)['labels']
    usable = [l for l in labels if l['usable']]

    import random
    random.seed(99)
    sample = random.sample(usable, 10)

    for item in sample:
        img = cv2.imread(os.path.join(CROPS_DIR, item['crop_file']))
        pred_points = predict(model, img)
        true_points = item['keypoints']

        vis = img.copy()
        for name, (x, y) in pred_points.items():
            cv2.circle(vis, (x, y), 5, COLORS[name], -1)
        for name, (x, y) in true_points.items():
            cv2.circle(vis, (int(x), int(y)), 3, COLORS[name], 1)
            cv2.circle(vis, (int(x), int(y)), 1, (255, 255, 255), -1)

        out_path = os.path.join(OUT_DIR, f'pred_{item["crop_file"]}')
        cv2.imwrite(out_path, vis)
        print(f'{item["crop_file"]} -> {out_path}')


if __name__ == '__main__':
    main()
