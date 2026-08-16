"""
One-time (resumable) batch job: crop every pro database clip onto a solid
backdrop and write it to a separate directory. Does NOT touch
pro_database.json or the original files in data/04_clips/ -- purely
additive, parallel copies.

Any entry this misses (interrupted run, a clip that fails to crop) is
lazily cropped and cached by the backend on first real request, using the
exact same output-path convention -- see backend/src/routes/analyse.js.

Usage:
  python precrop_pro_database.py [--limit N]
"""
import sys
import os
import json
import argparse

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paths import DATA_DIR
from crop_to_subject import crop_to_subject

DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
CROPPED_DIR = os.path.join(DATA_DIR, '04_clips_cropped')


def cropped_path_for(clip_path, shot_type):
    return os.path.join(CROPPED_DIR, shot_type, os.path.basename(clip_path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None, help='Only process the first N entries (for a quick test run)')
    parser.add_argument('--force', action='store_true', help='Re-crop even if an output file already exists (e.g. after a crop-parameter change)')
    args = parser.parse_args()

    with open(DB_PATH) as f:
        db = json.load(f)

    entries = db['entries']
    if args.limit:
        entries = entries[:args.limit]

    total = len(entries)
    done = skipped = failed = 0

    for i, entry in enumerate(entries, 1):
        clip_path = entry.get('clip_path')
        shot_type = entry.get('shot_type')
        if not clip_path or not shot_type or not os.path.exists(clip_path):
            print(f'  [{i}/{total}] SKIP {entry.get("id")} -- clip_path missing on disk')
            skipped += 1
            continue

        out_path = cropped_path_for(clip_path, shot_type)
        if os.path.exists(out_path) and not args.force:
            skipped += 1
            continue

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            result = crop_to_subject(clip_path, out_path)
            if result.get('cropped'):
                done += 1
            else:
                print(f'  [{i}/{total}] FAILED {entry.get("id")}: {result.get("reason")}')
                failed += 1
        except Exception as e:
            print(f'  [{i}/{total}] ERROR {entry.get("id")}: {e}')
            failed += 1

        if i % 10 == 0 or i == total:
            print(f'  [{i}/{total}] cropped={done} skipped={skipped} failed={failed}')

    print(f'\nDone. cropped={done} skipped={skipped} failed={failed} total={total}')


if __name__ == '__main__':
    main()
