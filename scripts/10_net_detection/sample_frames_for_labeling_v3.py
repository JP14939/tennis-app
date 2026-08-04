"""
Second labeling pass -- expand the net-keypoint training set before wiring
the model into the app. v2's results showed a clear pattern worth exploiting:
bucket 0 (swing_id < 1000, the Court-Level-Tennis-style compilation) was
100% usable (net visible, clean corners) while buckets 1000+ (broadcast-style
compilations) were 0% usable (tight shots, no net in frame). Real footage
(mark_vs_silas/nicolas_vs_florian) was also 100% usable and is the group the
vertical-elevation signal is actually calibrated against, so it's the
highest-value place to add more examples.

This pass over-samples bucket 0 + real footage (where labeling effort pays
off) and only lightly samples other buckets (to keep a few confirmed-
unusable negative examples, not to fish for more positives there).
Excludes any frame already labeled in v2 so the two label files can be
merged without duplicates.

Usage:
  python sample_frames_for_labeling_v3.py
"""
import glob
import json
import os
import random
import re

import cv2

CLIPS_ROOT = r'C:\Users\jackp\tennis_app\data\04_clips'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\own_footage_frames_v3'
EXISTING_LABELS = r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_v2.json'

BUCKET0_PER_SHOT = 14
OTHER_BUCKET_PER_SHOT = 2

REAL_FOOTAGE = {
    'mark_vs_silas': r'C:\Users\jackp\tennis_app\data\04_clips\testing\mark_vs_silas',
    'nicolas_vs_florian': r'C:\Users\jackp\tennis_app\data\04_clips\testing\nicolas_vs_florian',
}
REAL_PER_VIDEO = 22

random.seed(23)


def bucket_of(clip_path):
    m = re.search(r'_swing_(\d+)_', os.path.basename(clip_path))
    if not m:
        return None
    return int(m.group(1)) // 1000


def already_labeled_names():
    with open(EXISTING_LABELS) as f:
        data = json.load(f)
    return {item['frame_file'] for item in data['labels']}


def frame_name_for(clip_path):
    return os.path.splitext(os.path.basename(clip_path))[0] + '.jpg'


def sample_pro_clips(exclude_names):
    picks = []
    for shot in ['forehand', 'backhand', 'serve']:
        clips = glob.glob(os.path.join(CLIPS_ROOT, shot, '*.mp4'))
        clips = [c for c in clips if frame_name_for(c) not in exclude_names]
        buckets = {}
        for c in clips:
            b = bucket_of(c)
            if b is not None:
                buckets.setdefault(b, []).append(c)
        for b, items in buckets.items():
            n = BUCKET0_PER_SHOT if b == 0 else OTHER_BUCKET_PER_SHOT
            picks.extend(random.sample(items, min(n, len(items))))
    return picks


def sample_real_clips(exclude_names):
    picks = []
    for name, folder in REAL_FOOTAGE.items():
        clips = glob.glob(os.path.join(folder, '*.mp4'))
        clips = [c for c in clips if frame_name_for(c) not in exclude_names]
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
    name = frame_name_for(clip_path)
    out_path = os.path.join(out_dir, name)
    cv2.imwrite(out_path, frame)
    return name


if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)
    exclude = already_labeled_names()
    picks = sample_pro_clips(exclude) + sample_real_clips(exclude)
    print(f'Sampling {len(picks)} new clips (excluding {len(exclude)} already labeled)...')

    saved = []
    for clip in picks:
        name = save_mid_frame(clip, OUT_DIR)
        if name:
            saved.append(name)
            print(f'  {name}')

    print(f'\nSaved {len(saved)} frames to {OUT_DIR}')
