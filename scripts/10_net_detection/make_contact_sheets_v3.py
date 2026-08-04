"""Tile v3 frames into labeled contact sheets for fast usable/unusable triage
before spending per-image labeling effort only on the ones worth it."""
import glob
import math
import os

import cv2
import numpy as np

FRAMES_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\own_footage_frames_v3'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\contact_sheets_v3'
PER_SHEET = 8
THUMB_W = 480


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(FRAMES_DIR, '*.jpg')))
    n_sheets = math.ceil(len(files) / PER_SHEET)

    for s in range(n_sheets):
        batch = files[s * PER_SHEET:(s + 1) * PER_SHEET]
        thumbs = []
        for fp in batch:
            img = cv2.imread(fp)
            h, w = img.shape[:2]
            th = int(THUMB_W * h / w)
            thumb = cv2.resize(img, (THUMB_W, th))
            cv2.putText(thumb, os.path.basename(fp), (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            thumbs.append(thumb)

        max_h = max(t.shape[0] for t in thumbs)
        cols = 2
        rows = math.ceil(len(thumbs) / cols)
        sheet = np.zeros((rows * max_h, cols * THUMB_W, 3), dtype=np.uint8)
        for i, t in enumerate(thumbs):
            r, c = divmod(i, cols)
            sheet[r * max_h:r * max_h + t.shape[0], c * THUMB_W:(c + 1) * THUMB_W] = t

        out_path = os.path.join(OUT_DIR, f'sheet_{s:02d}.jpg')
        cv2.imwrite(out_path, sheet)
        print(out_path)


if __name__ == '__main__':
    main()
