"""Visualize predicted net-end keypoints vs ground truth on sample frames."""
import json
import os
import random

import cv2
import torch

from train_net_keypoints import build_model, IMG_SIZE, POINTS, IMAGENET_MEAN, IMAGENET_STD, FRAMES_DIR, LABELS_PATH, MODEL_OUT

COLORS = {'left_end': (255, 0, 0), 'right_end': (0, 255, 0)}
OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_keypoints\validation_viz'


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
    usable = [l for l in labels if l.get('usable')]

    random.seed(77)
    sample = random.sample(usable, 8)

    for item in sample:
        img = cv2.imread(os.path.join(FRAMES_DIR, item['local_file']))
        pred_points = predict(model, img)
        true_points = item['keypoints']

        vis = img.copy()
        for name, (x, y) in pred_points.items():
            cv2.circle(vis, (x, y), 12, COLORS[name], -1)
        for name, (x, y) in true_points.items():
            cv2.circle(vis, (int(x), int(y)), 8, COLORS[name], 3)
        cv2.line(vis, pred_points['left_end'], pred_points['right_end'], (0, 0, 255), 2)

        out_path = os.path.join(OUT_DIR, f'net_pred_{item["local_file"]}')
        cv2.imwrite(out_path, vis)
        print(f'{item["local_file"]} -> {out_path}')


if __name__ == '__main__':
    main()
