"""
Re-enrichment pass: re-run infer_camera_angle() across every pro_database.json
entry's clip, updating camera_angle/angle_confidence in place and stamping
angle_model_version so a --resume can skip what's already done.

v10 (Section 8): infer_camera_angle now uses the v10 2-keypoint net model and
the 5-frame median-of-angles aggregation. The old height_ratio/elevation_status
vertical signal is RETIRED (v10 has no post-base keypoints) -- this pass no
longer writes those keys, and leaves any stale ones already on an entry alone.

Backs up pro_database.json first (to a v10-specific path, so the pre-v4 backup
is not clobbered).

Usage:
  python reenrich_camera_angle.py            # full pass
  python reenrich_camera_angle.py --resume   # skip entries already at v10

Coordinate the ~20-min DB-rewrite window with any parallel process that reads
pro_database.json live (see Section 8 item 6).
"""
import argparse
import json
import os
import shutil
import sys
import time

SCRIPTS_DIR = r'C:\Users\jackp\tennis_app\scripts'
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import infer_camera_angle, create_landmarker  # noqa: E402

DB_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'
BACKUP_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database_backup_pre_camera_angle_reenrichment_v10.json'

ANGLE_MODEL_VERSION = 'v10'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--resume', action='store_true',
                    help=f"skip entries already stamped angle_model_version == '{ANGLE_MODEL_VERSION}'")
    args = ap.parse_args()

    if not os.path.exists(BACKUP_PATH):
        shutil.copy(DB_PATH, BACKUP_PATH)
        print(f'Backed up to {BACKUP_PATH}')

    with open(DB_PATH) as f:
        db = json.load(f)

    entries = db['entries']
    landmarker = create_landmarker()

    n_ok = n_fail = n_missing_clip = n_skipped = 0
    n_keypoint_method = 0
    start = time.time()
    for i, entry in enumerate(entries):
        if args.resume and entry.get('angle_model_version') == ANGLE_MODEL_VERSION:
            n_skipped += 1
            continue

        clip_path = entry.get('clip_path')
        if not clip_path or not os.path.exists(clip_path):
            n_missing_clip += 1
            continue

        try:
            angle, conf, debug = infer_camera_angle(clip_path, landmarker=landmarker)
        except Exception as e:
            angle, conf, debug = None, 0.0, str(e)

        if angle is not None:
            entry['camera_angle'] = angle
            entry['angle_confidence'] = conf
            entry['angle_model_version'] = ANGLE_MODEL_VERSION
            if isinstance(debug, dict) and debug.get('net_detection_method') == 'keypoint_model':
                n_keypoint_method += 1
            n_ok += 1
        else:
            n_fail += 1

        if (i + 1) % 20 == 0:
            elapsed = time.time() - start
            done = i + 1 - n_skipped
            rate = done / elapsed if elapsed else 0.0
            eta_min = (len(entries) - i - 1) / rate / 60 if rate else 0.0
            print(f'  {i+1}/{len(entries)} | ok={n_ok} fail={n_fail} missing_clip={n_missing_clip} '
                  f'skipped={n_skipped} | keypoint_method={n_keypoint_method}/{n_ok if n_ok else 1} '
                  f'| {rate:.2f}/s | ETA {eta_min:.1f}min', flush=True)

    landmarker.close()

    # Write to a temp file and atomically replace -- a late failure (e.g. a
    # non-JSON-serializable value slipping through, as happened once already)
    # must never leave pro_database.json truncated/corrupted mid-write.
    tmp_path = DB_PATH + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(db, f)
    os.replace(tmp_path, DB_PATH)

    total = len(entries)
    processed = total - n_skipped
    print(f'\nDone. {n_ok}/{processed} processed entries got a real camera_angle, '
          f'{n_fail} net-not-detected, {n_missing_clip} missing clip file, {n_skipped} skipped (--resume).')
    if n_ok:
        print(f'{n_keypoint_method}/{n_ok} of successful detections used the keypoint model '
              f'({100*n_keypoint_method/n_ok:.1f}%); the rest fell back to the Hough heuristic.')


if __name__ == '__main__':
    main()
