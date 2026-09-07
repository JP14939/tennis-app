"""
One-time enrichment pass: measure each pro clip's in-plane camera roll (the
net-cord slope, see infer_angle.net_roll_deg) and, where it's in the
correctable band (infer_angle.usable_roll), rotate that entry's stored
trajectory level so DTW against a roll-corrected user swing compares
like-for-like.

Pattern mirrors scripts/00_utils/reenrich_camera_angle.py:
  - backs up pro_database.json first (skipped if the backup already exists),
  - atomic temp-file + os.replace write,
  - per-entry idempotency guard (`camera_roll_corrected`) so a re-run never
    double-rotates. To re-derive from scratch, restore the backup first.

overlay_trajectories.json is intentionally NOT touched -- those are raw
image-space coordinates that must stay pixel-aligned to the actual video.

Usage:
  python enrich_pro_camera_roll.py            # writes pro_database.json in place
  python enrich_pro_camera_roll.py --dry-run  # measure + report only, no write
"""
import argparse
import json
import os
import shutil
import sys
import time
from collections import Counter

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
from infer_angle import (  # noqa: E402
    infer_camera_angle, create_landmarker, usable_roll,
    ROLL_CORRECTION_MIN_DEG, ROLL_CORRECTION_MAX_DEG,
)
from trajectory_extraction import rotate_trajectory  # noqa: E402
from paths import DATA_DIR  # noqa: E402

DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
BACKUP_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database_backup_pre_camera_roll_enrichment.json')
PRO_CLIPS_DIR = os.path.join(DATA_DIR, '04_clips')


def resolve_clip(entry):
    """clip_path is stored relative to 04_clips (see relative_clip_path in
    build_pro_database.py). Older databases may still hold an absolute path."""
    cp = entry.get('clip_path')
    if not cp:
        return None
    cand = cp if os.path.isabs(cp) else os.path.join(PRO_CLIPS_DIR, cp)
    return cand if os.path.exists(cand) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='measure and report only, do not write')
    args = ap.parse_args()

    if not args.dry_run and not os.path.exists(BACKUP_PATH):
        shutil.copy(DB_PATH, BACKUP_PATH)
        print(f'Backed up to {BACKUP_PATH}')

    with open(DB_PATH) as f:
        db = json.load(f)
    entries = db['entries']

    landmarker = create_landmarker()

    n_ok = n_missing = n_no_roll = n_corrected = n_already = 0
    roll_hist = Counter()  # |roll| rounded to nearest degree, among readings
    start = time.time()

    for i, entry in enumerate(entries):
        if entry.get('camera_roll_corrected'):
            n_already += 1
            continue

        clip = resolve_clip(entry)
        if clip is None:
            n_missing += 1
            continue

        try:
            _angle, _conf, debug = infer_camera_angle(clip, landmarker=landmarker)
        except Exception as e:  # noqa: BLE001
            debug = {}
            print(f'  {entry["id"]}: angle inference failed ({e})', file=sys.stderr)

        raw_roll = debug.get('camera_roll_deg') if isinstance(debug, dict) else None
        entry['camera_roll_deg'] = raw_roll
        entry['camera_roll_source'] = debug.get('camera_roll_source') if isinstance(debug, dict) else None

        if raw_roll is None:
            n_no_roll += 1
        else:
            n_ok += 1
            roll_hist[round(abs(raw_roll))] += 1

        roll = usable_roll(raw_roll)
        if roll is not None:
            entry['trajectory'] = rotate_trajectory(entry['trajectory'], roll)
            entry['camera_roll_corrected'] = True
            n_corrected += 1

        if (i + 1) % 20 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            eta_min = (len(entries) - i - 1) / rate / 60
            print(f'  {i+1}/{len(entries)} | roll-read={n_ok} corrected={n_corrected} '
                  f'no-roll={n_no_roll} missing={n_missing} | {rate:.2f}/s | ETA {eta_min:.1f}min', flush=True)

    landmarker.close()

    total = len(entries)
    print(f'\n{"DRY RUN — " if args.dry_run else ""}Summary over {total} entries:')
    print(f'  roll measured:      {n_ok}')
    print(f'  no net-cord slope:  {n_no_roll}')
    print(f'  missing clip file:  {n_missing}')
    print(f'  already corrected:  {n_already}')
    print(f'  trajectories rotated: {n_corrected}  '
          f'(|roll| in [{ROLL_CORRECTION_MIN_DEG:.0f}, {ROLL_CORRECTION_MAX_DEG:.0f}]°)')
    if roll_hist:
        print('  |roll|° distribution among readings:')
        for deg in sorted(roll_hist):
            print(f'    {deg:>3}°  {"#" * roll_hist[deg]}  ({roll_hist[deg]})')
    print('\nSanity check: the large majority of broadcast pro clips should read '
          'within a few degrees of level. A high corrected count means the sign/scale '
          'or net-keypoint reliability needs a look BEFORE trusting this.')

    if args.dry_run:
        print('\n--dry-run: pro_database.json not modified.')
        return

    tmp_path = DB_PATH + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(db, f)
    os.replace(tmp_path, DB_PATH)
    print(f'\nWrote {DB_PATH}')


if __name__ == '__main__':
    main()
