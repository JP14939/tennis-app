"""
One-time enrichment pass: run racket+body tracking (track_racket_in_clip.py)
across every pro_database.json entry's clip, storing a normalised average
racket-handle-to-hip-midpoint distance as entry['racket_body_distance'].
Entries where the racket is never confidently detected keep this field null
rather than a fabricated number -- the body-rotation phase falls back to
rotation-only scoring for those matches (see phase_breakdown.py).

Backs up pro_database.json first, same precedent as
pro_database_backup_pre_elevation_enrichment.json earlier this session.
"""
import json
import os
import shutil
import sys
import time

SCRIPTS_DIR = r'C:\Users\jackp\tennis_app\scripts'
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from track_racket_in_clip import track_racket_body, avg_racket_body_distance  # noqa: E402
from infer_angle import create_landmarker  # noqa: E402

DB_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'
BACKUP_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database_backup_pre_racket_body_enrichment.json'


def main():
    if not os.path.exists(BACKUP_PATH):
        shutil.copy(DB_PATH, BACKUP_PATH)
        print(f'Backed up to {BACKUP_PATH}')

    with open(DB_PATH) as f:
        db = json.load(f)

    entries = db['entries']
    landmarker = create_landmarker()

    n_ok = n_null = n_missing_clip = 0
    start = time.time()
    for i, entry in enumerate(entries):
        clip_path = entry.get('clip_path')
        if not clip_path or not os.path.exists(clip_path):
            entry['racket_body_distance'] = None
            n_missing_clip += 1
            continue

        try:
            frame_results = track_racket_body(clip_path, landmarker=landmarker, sample_every=4)
            dist = avg_racket_body_distance(frame_results)
        except Exception as e:
            dist = None
            print(f'  [{i}] {entry["id"]} error: {e}', file=sys.stderr)

        entry['racket_body_distance'] = dist
        if dist is None:
            n_null += 1
        else:
            n_ok += 1

        if (i + 1) % 20 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            eta_min = (len(entries) - i - 1) / rate / 60
            print(f'  {i+1}/{len(entries)} | ok={n_ok} null={n_null} missing_clip={n_missing_clip} '
                  f'| {rate:.2f}/s | ETA {eta_min:.1f}min', flush=True)

    landmarker.close()

    with open(DB_PATH, 'w') as f:
        json.dump(db, f)

    total = len(entries)
    print(f'\nDone. {n_ok}/{total} entries got a real racket_body_distance '
          f'({100*n_ok/total:.1f}%), {n_null} null (racket/pose not confidently detected), '
          f'{n_missing_clip} missing clip file.')


if __name__ == '__main__':
    main()
