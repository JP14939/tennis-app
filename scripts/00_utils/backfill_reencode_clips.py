"""
One-off backfill: every clip written before video_io.reencode_to_h264() was
wired into the pipeline is still old MPEG-4 Part 2 ('FMP4' fourcc),
unplayable in a browser. Walks every clip directory in the app, re-encoding
every .mp4 that isn't already real H.264 in place. Job 8's rally clips are
already h264 (manually fixed earlier) and get skipped; their .mp4v.bak
backups are left alone entirely (not this script's business to clean up).

Extended 2026-08-19 to also cover the pro database (data/04_clips,
data/04_clips_cropped) and leftover raw-footage-ingest staging clips --
confirmed live these were NEVER swept by the original backfill (which only
covered highlight_clips/user_clips), meaning every pro clip shown anywhere
in the app (analysis results, SyncCompareScreen, Versus comparisons) has
been unplayable in-browser this whole time.

Usage:
  python backfill_reencode_clips.py [--dry-run]
"""
import argparse
import glob
import os
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
from paths import DATA_DIR  # noqa: E402
from video_io import is_real_h264, reencode_to_h264  # noqa: E402

TARGET_DIRS = [
    os.path.join(DATA_DIR, 'runtime', 'highlight_clips'),
    os.path.join(DATA_DIR, 'runtime', 'user_clips'),
    os.path.join(DATA_DIR, '04_clips'),
    os.path.join(DATA_DIR, '04_clips_cropped'),
    os.path.join(DATA_DIR, 'runtime', 'raw_footage_ingest'),
]


def find_candidates():
    for base in TARGET_DIRS:
        if not os.path.isdir(base):
            continue
        for path in glob.glob(os.path.join(base, '**', '*.mp4'), recursive=True):
            yield path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    candidates = list(find_candidates())
    print(f'{len(candidates)} .mp4 files found under {TARGET_DIRS}')

    fixed, skipped, failed = 0, 0, 0
    for path in candidates:
        if is_real_h264(path):
            skipped += 1
            continue

        if args.dry_run:
            print(f'  would re-encode: {path}')
            fixed += 1
            continue

        t0 = time.time()
        try:
            reencode_to_h264(path)
            print(f'  re-encoded ({time.time() - t0:.1f}s): {path}')
            fixed += 1
        except Exception as e:
            print(f'  FAILED: {path} -- {e}', file=sys.stderr)
            failed += 1

    print(f'\nDone. {fixed} re-encoded, {skipped} already h264, {failed} failed.')


if __name__ == '__main__':
    main()
