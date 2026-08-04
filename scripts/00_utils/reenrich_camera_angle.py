"""
One-time re-enrichment pass: re-run infer_camera_angle() (now keypoint-model-
first, Hough-heuristic-fallback) across every pro_database.json entry's clip,
updating camera_angle/angle_confidence in place, and adding the new
height_ratio/elevation_status vertical signal alongside them (computed for
free in the same pass -- infer_camera_angle already runs the keypoint model
for the horizontal angle).

Backs up pro_database.json first, same precedent as the other enrichment
passes this session.
"""
import json
import os
import shutil
import sys
import time

SCRIPTS_DIR = r'C:\Users\jackp\tennis_app\scripts'
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import infer_camera_angle, create_landmarker  # noqa: E402

DB_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'
BACKUP_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database_backup_pre_camera_angle_reenrichment.json'


def main():
    if not os.path.exists(BACKUP_PATH):
        shutil.copy(DB_PATH, BACKUP_PATH)
        print(f'Backed up to {BACKUP_PATH}')

    with open(DB_PATH) as f:
        db = json.load(f)

    entries = db['entries']
    landmarker = create_landmarker()

    n_ok = n_fail = n_missing_clip = 0
    n_keypoint_method = 0
    start = time.time()
    for i, entry in enumerate(entries):
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
            entry['height_ratio'] = debug.get('height_ratio')
            entry['elevation_status'] = debug.get('elevation_status')
            if debug.get('net_detection_method') == 'keypoint_model':
                n_keypoint_method += 1
            n_ok += 1
        else:
            n_fail += 1

        if (i + 1) % 20 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            eta_min = (len(entries) - i - 1) / rate / 60
            print(f'  {i+1}/{len(entries)} | ok={n_ok} fail={n_fail} missing_clip={n_missing_clip} '
                  f'| keypoint_method={n_keypoint_method}/{n_ok if n_ok else 1} | {rate:.2f}/s | ETA {eta_min:.1f}min', flush=True)

    landmarker.close()

    # Write to a temp file and atomically replace -- a late failure (e.g. a
    # non-JSON-serializable value slipping through, as happened once already)
    # must never leave pro_database.json truncated/corrupted mid-write.
    tmp_path = DB_PATH + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(db, f)
    os.replace(tmp_path, DB_PATH)

    total = len(entries)
    print(f'\nDone. {n_ok}/{total} entries got a real camera_angle ({100*n_ok/total:.1f}%), '
          f'{n_fail} net-not-detected, {n_missing_clip} missing clip file.')
    print(f'{n_keypoint_method}/{n_ok} of successful detections used the keypoint model '
          f'({100*n_keypoint_method/n_ok:.1f}%); the rest fell back to the Hough heuristic.')


if __name__ == '__main__':
    main()
