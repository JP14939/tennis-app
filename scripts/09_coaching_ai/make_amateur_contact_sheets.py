"""
Tile a frame near each candidate amateur swing's peak into labeled contact
sheets for visual shot-type classification -- same pattern as
make_contact_sheets_v3.py (net-keypoint labeling), adapted to pull frames
directly from the cut clips (data/04_clips/amateur/) instead of
pre-extracted jpgs.

Each clip's window is peak-1.8s to peak+2.0s (see extract_amateur_clips.py),
so the peak frame sits ~1.8s into the clip regardless of shot type.
"""
import json
import math
import os

import cv2
import numpy as np

CLIPS_DIR = r'C:\Users\jackp\tennis_app\data\04_clips\amateur'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\09_coaching_ai_labeling\amateur_contact_sheets'
PER_SHEET = 12
THUMB_W = 320
PEAK_OFFSET_SEC = 1.8


def grab_peak_frame(clip_path, fps):
    cap = cv2.VideoCapture(clip_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target = min(int(PEAK_OFFSET_SEC * fps), max(0, total - 1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


LABELS_PATH = r'C:\Users\jackp\tennis_app\data\08_coaching_ai\amateur_swing_labels.json'


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest_path = os.path.join(CLIPS_DIR, 'manifest.json')
    with open(manifest_path) as f:
        manifest = json.load(f)

    already_labeled = set()
    if os.path.exists(LABELS_PATH):
        with open(LABELS_PATH, encoding='utf-8') as f:
            already_labeled = set(json.load(f)['labels'].keys())

    manifest = [e for e in manifest if f'{e["video_id"]}_{e["swing_id"]}' not in already_labeled]
    print(f'{len(manifest)} candidates not yet labeled — generating sheets for those.')

    thumbs = []
    labels = []
    for entry in manifest:
        frame = grab_peak_frame(entry['clip_path'], fps=30.0)
        if frame is None:
            print(f'  WARNING: could not read peak frame for {entry["clip_path"]}')
            continue
        h, w = frame.shape[:2]
        th = int(THUMB_W * h / w)
        thumb = cv2.resize(frame, (THUMB_W, th))
        cell_id = f'{entry["video_id"]}_{entry["swing_id"]}'
        cv2.putText(thumb, cell_id, (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        thumbs.append(thumb)
        labels.append(cell_id)

    n_sheets = math.ceil(len(thumbs) / PER_SHEET)
    cols = 4
    for s in range(n_sheets):
        batch = thumbs[s * PER_SHEET:(s + 1) * PER_SHEET]
        batch_ids = labels[s * PER_SHEET:(s + 1) * PER_SHEET]
        max_h = max(t.shape[0] for t in batch)
        rows = math.ceil(len(batch) / cols)
        sheet = np.zeros((rows * max_h, cols * THUMB_W, 3), dtype=np.uint8)
        for i, t in enumerate(batch):
            r, c = divmod(i, cols)
            sheet[r * max_h:r * max_h + t.shape[0], c * THUMB_W:(c + 1) * THUMB_W] = t

        out_path = os.path.join(OUT_DIR, f'sheet_{s:02d}.jpg')
        cv2.imwrite(out_path, sheet)
        print(f'{out_path}  [{", ".join(batch_ids)}]')

    print(f'\n{len(thumbs)} candidates tiled into {n_sheets} sheets.')


if __name__ == '__main__':
    main()
