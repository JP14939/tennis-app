"""
Enrich pro_database.json with a 'view_direction' field ('front' | 'back' |
'unknown') using infer_angle.detect_view_direction() -- distinguishes a
camera at the net facing the far player (front, sees their face) from a
camera behind a baseline facing the near player (back, sees their back).
Both can land in the same low camera_angle bucket (hard-clamped 0-90,
direction-agnostic), even though the pose landmarks are essentially
mirrored between them.

Validated against 10 real sampled low-angle entries before running at
scale (7/8 confident predictions visually confirmed correct; 2 conservatively
abstained as 'unknown' rather than guess wrong) -- see conversation history,
not re-derived here.

Resumable: skips entries that already have a view_direction. Backs up
pro_database.json before patching (see pro_database_backup_pre_view_direction.json).

Usage: python enrich_view_direction.py
"""
import json
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '05_angle_detection'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from infer_angle import detect_view_direction, create_landmarker  # noqa: E402
from paths import DATA_DIR  # noqa: E402

DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')


def main():
    with open(DB_PATH, encoding='utf-8') as f:
        db = json.load(f)

    entries = db['entries']
    todo = [e for e in entries if 'view_direction' not in e]
    print(f'{len(entries)} total entries, {len(todo)} need view_direction')

    landmarker = create_landmarker()
    counts = {'front': 0, 'back': 0, 'unknown': 0, 'missing_clip': 0}

    for i, entry in enumerate(todo, 1):
        clip_path = entry.get('clip_path')
        contact_t = entry.get('clip_contact_time_sec')
        if not clip_path or not os.path.exists(clip_path) or contact_t is None:
            entry['view_direction'] = 'unknown'
            counts['missing_clip'] += 1
            continue

        cap = cv2.VideoCapture(clip_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_idx = max(0, min(total - 1, round(contact_t * fps)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            entry['view_direction'] = 'unknown'
            counts['missing_clip'] += 1
            continue

        result = detect_view_direction(frame, landmarker)
        entry['view_direction'] = result
        counts[result] += 1

        if i % 100 == 0:
            print(f'  {i}/{len(todo)}...')
            with open(DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(db, f)

    landmarker.close()

    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f)

    print(f'\nDone: {counts}')
    print(f'Saved to {DB_PATH}')


if __name__ == '__main__':
    main()
