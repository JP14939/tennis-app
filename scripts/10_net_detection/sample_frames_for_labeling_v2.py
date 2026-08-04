"""
Sample diverse frames (from short swing clips, not raw source videos) for
Claude to hand-label net keypoints on -- step 1 of training a YOLO-pose
net-keypoint model. Diversity across different source compilations matters
more than raw volume at this scale (same lesson as sample_racket_crops.py).

Swing IDs encode which source compilation a clip came from via
swing_id_offset (1000/2000/3000 per compilation, per build_pro_database.py) --
bucketing by the ID's leading digit is a cheap proxy for "different
compilation" without needing to trace exact source mapping.

Usage:
  python sample_frames_for_labeling_v2.py
"""
import glob
import os
import random
import re

import cv2

CLIPS_ROOT = r'C:\Users\jackp\tennis_app\data\04_clips'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\own_footage_frames_v2'
PER_BUCKET = 4
REAL_FOOTAGE = {
    'mark_vs_silas': r'C:\Users\jackp\tennis_app\data\04_clips\testing\mark_vs_silas',
    'nicolas_vs_florian': r'C:\Users\jackp\tennis_app\data\04_clips\testing\nicolas_vs_florian',
}
REAL_PER_VIDEO = 6

random.seed(11)


def bucket_of(clip_path):
    m = re.search(r'_swing_(\d+)_', os.path.basename(clip_path))
    if not m:
        return None
    return int(m.group(1)) // 1000


def sample_pro_clips():
    picks = []
    for shot in ['forehand', 'backhand', 'serve']:
        clips = glob.glob(os.path.join(CLIPS_ROOT, shot, '*.mp4'))
        buckets = {}
        for c in clips:
            b = bucket_of(c)
            if b is not None:
                buckets.setdefault(b, []).append(c)
        for b, items in buckets.items():
            picks.extend(random.sample(items, min(PER_BUCKET, len(items))))
    return picks


def sample_real_clips():
    picks = []
    for name, folder in REAL_FOOTAGE.items():
        clips = glob.glob(os.path.join(folder, '*.mp4'))
        picks.extend(random.sample(clips, min(REAL_PER_VIDEO, len(clips))))
    return picks


def save_mid_frame(clip_path, out_dir):
    cap = cv2.VideoCapture(clip_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    name = os.path.splitext(os.path.basename(clip_path))[0] + '.jpg'
    out_path = os.path.join(out_dir, name)
    cv2.imwrite(out_path, frame)
    return name


if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)
    picks = sample_pro_clips() + sample_real_clips()
    print(f'Sampling {len(picks)} clips...')

    saved = []
    for clip in picks:
        name = save_mid_frame(clip, OUT_DIR)
        if name:
            saved.append(name)
            print(f'  {name}')

    print(f'\nSaved {len(saved)} frames to {OUT_DIR}')
