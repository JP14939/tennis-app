"""
Sample candidate racket crops for keypoint-labeling training data.

Runs the existing pretrained racket detector across a diverse sample of
clips/frames, crops tightly (with padding) around each confident detection,
and saves the crops + metadata for labeling (see label_racket_keypoints.py).
"""
import glob
import json
import os
import random

import cv2
from ultralytics import YOLO

RACKET_CLASS = 38
CONF_THRESHOLD = 0.35  # higher than racket_tracker's default — only confident boxes are worth labeling
PADDING_FRAC = 0.25    # extra margin around the box so keypoints near edges aren't cut off

CLIPS_ROOT = r'C:\Users\jackp\tennis_app\data\04_clips'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\crops'
META_PATH = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\crop_metadata.json'

random.seed(23)  # different seed from the first pass so we sample different clips


def sample_clips_per_shot(n_clips_per_shot=30, exclude=()):
    clips = {}
    for shot in ['forehand', 'backhand', 'serve']:
        all_clips = [c for c in glob.glob(os.path.join(CLIPS_ROOT, shot, '*.mp4')) if c not in exclude]
        clips[shot] = random.sample(all_clips, min(n_clips_per_shot, len(all_clips)))
    return clips


def crop_with_padding(frame, box, pad_frac):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    pad_x, pad_y = bw * pad_frac, bh * pad_frac
    cx1 = max(0, int(x1 - pad_x))
    cy1 = max(0, int(y1 - pad_y))
    cx2 = min(w, int(x2 + pad_x))
    cy2 = min(h, int(y2 + pad_y))
    return frame[cy1:cy2, cx1:cx2], (cx1, cy1)


def main(target_count=110, frames_per_clip=3):
    os.makedirs(OUT_DIR, exist_ok=True)
    model = YOLO('yolo11n.pt')

    existing_metadata = []
    if os.path.exists(META_PATH):
        with open(META_PATH) as f:
            existing_metadata = json.load(f)
    already_sampled_clips = {m['source_clip'] for m in existing_metadata}
    crop_idx = len(existing_metadata)  # filenames are contiguous (no gaps) since crops only saved on success

    clips = sample_clips_per_shot(n_clips_per_shot=45, exclude=already_sampled_clips)

    metadata = list(existing_metadata)
    target_count = crop_idx + target_count

    for shot, clip_paths in clips.items():
        for clip_path in clip_paths:
            if crop_idx >= target_count:
                break
            cap = cv2.VideoCapture(clip_path)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total < 10:
                cap.release()
                continue

            # Spread sampled frames across the clip for swing-phase diversity
            sample_frames = sorted(random.sample(range(5, total - 5), min(frames_per_clip, total - 10)))

            for target_frame in sample_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, frame = cap.read()
                if not ret:
                    continue

                results = model.predict(frame, classes=[RACKET_CLASS], conf=CONF_THRESHOLD, verbose=False)
                boxes = results[0].boxes
                if len(boxes) == 0:
                    continue

                best = max(boxes, key=lambda b: float(b.conf[0]))
                box = best.xyxy[0].tolist()
                conf = float(best.conf[0])

                crop, offset = crop_with_padding(frame, box, PADDING_FRAC)
                if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 20:
                    continue

                crop_name = f'{shot}_{crop_idx:04d}.jpg'
                cv2.imwrite(os.path.join(OUT_DIR, crop_name), crop)

                metadata.append({
                    'crop_file': crop_name,
                    'shot_type': shot,
                    'source_clip': clip_path,
                    'source_frame': target_frame,
                    'crop_offset_in_full_frame': offset,  # add this to labeled crop-local coords to get full-frame coords
                    'crop_size': [crop.shape[1], crop.shape[0]],  # w, h
                    'detection_conf': round(conf, 3),
                    'keypoints': None,  # filled in by the labeling step
                })
                crop_idx += 1
                if crop_idx >= target_count:
                    break

            cap.release()
        if crop_idx >= target_count:
            break

    with open(META_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f'Saved {crop_idx} crops to {OUT_DIR}')
    print(f'Metadata: {META_PATH}')
    by_shot = {}
    for m in metadata:
        by_shot[m['shot_type']] = by_shot.get(m['shot_type'], 0) + 1
    print(by_shot)


if __name__ == '__main__':
    main()
