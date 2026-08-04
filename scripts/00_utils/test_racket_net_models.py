"""Run the trained racket-keypoint and net-keypoint models against frames pulled
from the new real-footage clips, instead of their own held-out validation sets.
Ad hoc — no existing script runs these models on an arbitrary new frame."""
import argparse
import glob
import os
import random
import sys

import cv2
import torch
from ultralytics import YOLO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '10_net_detection'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '07_ball_racket_tracking'))
from train_net_keypoints import build_model, IMG_SIZE, POINTS as NET_POINTS, IMAGENET_MEAN, IMAGENET_STD, MODEL_OUT
from sample_racket_crops import crop_with_padding, RACKET_CLASS, PADDING_FRAC

RACKET_MODEL_PATH = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\yolo_pose_run\weights\best.pt'
RACKET_DETECT_CONF = 0.15  # racket_tracker.py's threshold -- looser than sample_racket_crops.py's 0.35 labeling bar
RACKET_COLORS = [(0, 0, 255), (0, 165, 255), (0, 255, 0), (255, 0, 0), (255, 0, 255)]
NET_COLORS = {'left_end': (255, 0, 0), 'right_end': (0, 255, 0)}


def grab_frames(clip_dir, out_dir, n=6, seed=5):
    os.makedirs(out_dir, exist_ok=True)
    clips = glob.glob(os.path.join(clip_dir, '*.mp4'))
    random.seed(seed)
    sample = random.sample(clips, min(n, len(clips)))
    frame_paths = []
    for clip in sample:
        cap = cv2.VideoCapture(clip)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            continue
        name = os.path.splitext(os.path.basename(clip))[0]
        out_path = os.path.join(out_dir, f'{name}_mid.jpg')
        cv2.imwrite(out_path, frame)
        frame_paths.append(out_path)
    return frame_paths


def run_racket_model(frame_paths, out_dir):
    # Two-stage, matching the real pipeline: generic COCO YOLO finds+crops the
    # racket (sample_racket_crops.py's approach) before the fine-tuned 5-point
    # pose model runs on that crop -- running the pose model on a full frame
    # (as this script originally did) is out-of-distribution and meaningless.
    detector = YOLO('yolo11n.pt')
    pose_model = YOLO(RACKET_MODEL_PATH)
    for img_path in frame_paths:
        img = cv2.imread(img_path)
        det = detector.predict(img, classes=[RACKET_CLASS], conf=RACKET_DETECT_CONF, verbose=False)
        boxes = det[0].boxes
        vis = img.copy()
        if len(boxes) == 0:
            out_path = os.path.join(out_dir, f'racket_{os.path.basename(img_path)}')
            cv2.imwrite(out_path, vis)
            print(f'racket: {os.path.basename(img_path)} -> no racket detected')
            continue

        best = max(boxes, key=lambda b: float(b.conf[0]))
        box = best.xyxy[0].tolist()
        det_conf = float(best.conf[0])
        crop, (ox, oy) = crop_with_padding(img, box, PADDING_FRAC)

        results = pose_model.predict(crop, verbose=False)
        if len(results[0].keypoints) > 0 and results[0].keypoints.xy.shape[1] > 0:
            kpts = results[0].keypoints.xy[0].cpu().numpy()
            for i, (x, y) in enumerate(kpts):
                cv2.circle(vis, (int(x + ox), int(y + oy)), 6, RACKET_COLORS[i % len(RACKET_COLORS)], -1)
        cv2.rectangle(vis, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (0, 255, 255), 2)

        out_path = os.path.join(out_dir, f'racket_{os.path.basename(img_path)}')
        cv2.imwrite(out_path, vis)
        print(f'racket: {os.path.basename(img_path)} -> {out_path} (detect_conf={det_conf:.2f})')


def run_net_model(frame_paths, out_dir):
    model = build_model()
    model.load_state_dict(torch.load(MODEL_OUT))
    model.eval()
    for img_path in frame_paths:
        img = cv2.imread(img_path)
        h, w = img.shape[:2]
        resized = cv2.resize(img, (IMG_SIZE, IMG_SIZE))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        t = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        for c in range(3):
            t[c] = (t[c] - IMAGENET_MEAN[c]) / IMAGENET_STD[c]
        with torch.no_grad():
            pred = model(t.unsqueeze(0))[0].numpy()
        vis = img.copy()
        for i, name in enumerate(NET_POINTS):
            x, y = int(pred[i * 2] * w), int(pred[i * 2 + 1] * h)
            cv2.circle(vis, (x, y), 12, NET_COLORS[name], -1)
        out_path = os.path.join(out_dir, f'net_{os.path.basename(img_path)}')
        cv2.imwrite(out_path, vis)
        print(f'net: {os.path.basename(img_path)} -> {out_path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('clip_dir', help='Directory of extracted swing clips')
    parser.add_argument('--out-dir', default=r'C:\Users\jackp\tennis_app\data\runtime\testing_viz')
    parser.add_argument('-n', type=int, default=6)
    args = parser.parse_args()

    frames_dir = os.path.join(args.out_dir, 'frames')
    frame_paths = grab_frames(args.clip_dir, frames_dir, n=args.n)
    print(f'Grabbed {len(frame_paths)} mid-clip frames')

    run_racket_model(frame_paths, args.out_dir)
    run_net_model(frame_paths, args.out_dir)
