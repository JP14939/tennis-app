"""
Backfill user_clip_url/pro_clip_url onto analyses saved by the overnight
batch pipeline (scripts/15_batch_analysis/analyze_rallies_parallel.py and
its predecessor), which posted straight to /api/history and never went
through analyse.js's persistAndCrop()/croppedProClipPath() logic the live
/api/analyse upload path uses -- so every batch-saved row is missing the
clip data ResultsScreen.js needs to show the synced "Watch & compare" view.

The per-swing source clips still exist on disk at
data/runtime/batch_swings/<job_id>/rally{rally_id:03d}_swing{swing_index:02d}.mp4
-- job_id isn't stored on the analysis row itself, but rally_id ranges are
disjoint across jobs (job 3: up to ~075, job 4: 076+), so trying both
folders and taking whichever exists resolves it without needing job_id.

Pro clips are already pre-cropped for the whole database
(data/04_clips_cropped/<shot_type>/<filename>, confirmed 631 files already
present) -- this only crops the user's own clip, matching the live path's
behavior of cropping just the upload, not the pro side (which is a shared,
already-precomputed cache).

Usage:
  python backfill_clip_urls.py --dry-run [--limit N]
  python backfill_clip_urls.py                      # full run
"""
import argparse
import json
import os
import sqlite3
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))  # crop_to_subject imports extract_poses

from paths import DATA_DIR, BACKEND_DIR  # noqa: E402
from clip_urls import attach_clip_urls  # noqa: E402

DB_PATH = os.path.join(BACKEND_DIR, 'data', 'app.db')
BATCH_SWINGS_DIR = os.path.join(DATA_DIR, 'runtime', 'batch_swings')


def find_source_swing_clip(rally_id, swing_index):
    filename = f'rally{rally_id:03d}_swing{swing_index:02d}.mp4'
    for job_dir in ('3', '4'):
        candidate = os.path.join(BATCH_SWINGS_DIR, job_dir, filename)
        if os.path.exists(candidate):
            return candidate
    return None


def backfill_one(conn, row, dry_run):
    result = json.loads(row['result_json'])
    batch_source = result.get('_batch_source')
    if not batch_source:
        return 'skip-not-batch'
    if result.get('user_clip_url'):
        return 'skip-already-has-url'

    rally_id = batch_source.get('rally_id')
    swing_index = batch_source.get('swing_index')
    src = find_source_swing_clip(rally_id, swing_index)
    if not src:
        return f'skip-missing-source (rally{rally_id}_swing{swing_index})'

    analysis_id = row['id']
    top = (result.get('matches') or [None])[0]

    if dry_run:
        pro_id = top and top.get('pro_id')
        return f'would-backfill (src={os.path.basename(src)}, top={pro_id})'

    try:
        attach_clip_urls(result, src, dest_key=analysis_id)
    except Exception as e:
        return f'error: {e}'

    conn.execute('UPDATE analyses SET result_json = ? WHERE id = ?', (json.dumps(result), analysis_id))
    return 'backfilled'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--user-id', type=int, default=13)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, result_json FROM analyses WHERE user_id = ? ORDER BY id ASC',
        (args.user_id,),
    ).fetchall()
    if args.limit:
        rows = rows[:args.limit]

    counts = {}
    for i, row in enumerate(rows, 1):
        status = backfill_one(conn, row, args.dry_run)
        key = status.split(' ')[0].split('(')[0]
        counts[key] = counts.get(key, 0) + 1
        print(f'  analysis {row["id"]}: {status}')
        # Commit periodically rather than one giant end-of-run transaction --
        # the Node backend has this same file open concurrently (serving
        # live requests), so a long-held write lock would block it the
        # whole run. Frequent small commits keep that window short, and
        # make an interrupted run resumable (already-backfilled rows are
        # skipped on the next pass via the user_clip_url check).
        if not args.dry_run and i % 10 == 0:
            conn.commit()

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f'\nSummary ({"DRY RUN" if args.dry_run else "LIVE"}): {counts}')


if __name__ == '__main__':
    main()
