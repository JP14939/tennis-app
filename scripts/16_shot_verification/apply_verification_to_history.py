"""
Applies shot-contact verification ground truth (from batch_verify_all.py's
checkpoint file) back onto Jack's existing saved analyses -- plan doc step 4.

For each `analyses` row with a `_batch_source` (rally_id/swing_index, but
no job_id -- the original overnight run predates that field; rally_id
ranges are disjoint across jobs 3/4, same resolution backfill_clip_urls.py
already uses):
  - Look up its verified result by (job_id, rally_id, swing_index).
  - Confirmed real shot: re-crop its user clip to a tight window --
    2 seconds before, 2 seconds after the verified contact frame
    (peak_frame from the checkpoint, which is what the teacher/student
    actually judged) -- replacing the wider/possibly-mistimed window the
    original save used. Reuses crop_to_subject.py's existing crop
    infrastructure (already fixed this session to stop clipping the
    racket) via the same clip_urls.attach_clip_urls() helper the backfill
    script uses, just re-run against a freshly re-extracted 4-second
    window instead of the original swing clip.
  - Confirmed NOT a real shot: left alone entirely -- no auto-delete. Jack
    (or any user) flags/deletes via the app.
  - No matching verification found yet: left alone, reported as unmatched.

Usage:
  python apply_verification_to_history.py [--dry-run] [--limit N]
"""
import argparse
import json
import os
import sqlite3
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))

from paths import DATA_DIR, BACKEND_DIR  # noqa: E402
from clip_urls import attach_clip_urls  # noqa: E402

DB_PATH = os.path.join(BACKEND_DIR, 'data', 'app.db')
HIGHLIGHT_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'highlight_clips', '13')
CHECKPOINT_PATH = os.path.join(DATA_DIR, 'runtime', 'shot_verification_batch', 'verified_swings.jsonl')

CROP_PAD_SEC = 2.0


def load_verifications():
    """{(job_id_str, rally_id, swing_index): record} from the batch checkpoint."""
    verified = {}
    if not os.path.exists(CHECKPOINT_PATH):
        raise RuntimeError(f'No checkpoint file at {CHECKPOINT_PATH} -- run batch_verify_all.py first')
    with open(CHECKPOINT_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if 'error' in rec:
                continue
            key = (str(rec['job_id']), rec['rally_id'], rec['swing_index'])
            verified[key] = rec
    return verified


def find_verification(verified, rally_id, swing_index):
    for job_id in ('3', '4'):
        rec = verified.get((job_id, rally_id, swing_index))
        if rec:
            return job_id, rec
    return None, None


def rally_clip_path(job_id, rally_id):
    return os.path.join(HIGHLIGHT_CLIPS_DIR, job_id, f'rally_{rally_id:03d}.mp4')


def extract_window_clip(rally_clip, peak_time_sec, out_path, pad_sec=CROP_PAD_SEC):
    """Cuts [peak_time_sec - pad_sec, peak_time_sec + pad_sec] out of the
    rally clip into out_path -- same OpenCV cut pattern used throughout
    this pipeline (no ffmpeg on this machine, see 00_utils/trim_video.py)."""
    cap = cv2.VideoCapture(rally_clip)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open {rally_clip}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    start_frame = max(0, int((peak_time_sec - pad_sec) * fps))
    end_frame = min(total_frames, int((peak_time_sec + pad_sec) * fps))

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
    for _ in range(end_frame - start_frame):
        ret, frame = cap.read()
        if not ret:
            break
        writer.write(frame)
    writer.release()
    cap.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--user-id', type=int, default=13)
    args = parser.parse_args()

    verified = load_verifications()
    print(f'{len(verified)} verified swings loaded from checkpoint', file=sys.stderr)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, result_json FROM analyses WHERE user_id = ? ORDER BY id ASC', (args.user_id,)
    ).fetchall()
    if args.limit:
        rows = rows[:args.limit]

    counts = {'confirmed_real_recropped': 0, 'confirmed_not_real': 0, 'unmatched': 0, 'error': 0}

    for row in rows:
        result = json.loads(row['result_json'])
        batch_source = result.get('_batch_source')
        if not batch_source:
            continue
        rally_id = batch_source.get('rally_id')
        swing_index = batch_source.get('swing_index')

        job_id, rec = find_verification(verified, rally_id, swing_index)
        if not rec:
            counts['unmatched'] += 1
            continue

        if not rec['is_real_shot']:
            counts['confirmed_not_real'] += 1
            print(f'  analysis {row["id"]} (rally{rally_id} swing{swing_index}): NOT a real shot '
                  f'({rec.get("reasoning", "")[:80]})')
            # Auto-flag Claude-confirmed-fake entries the same way a user's
            # own "not a real shot" flag would -- so Jack doesn't have to
            # manually redo what this batch already determined. Still never
            # deletes anything; he can review/delete flagged entries in the
            # app whenever he wants (see HistoryScreen.js's flag button).
            if not args.dry_run:
                conn.execute('UPDATE analyses SET flagged_not_shot = 1 WHERE id = ?', (row['id'],))
                conn.commit()
            continue

        counts['confirmed_real_recropped'] += 1
        if args.dry_run:
            print(f'  analysis {row["id"]} (rally{rally_id} swing{swing_index}): would re-crop '
                  f'around {rec["peak_time_sec"]}s')
            continue

        try:
            rally_clip = rally_clip_path(job_id, rally_id)
            dest_dir = os.path.join(DATA_DIR, 'runtime', 'user_clips', str(row['id']))
            os.makedirs(dest_dir, exist_ok=True)
            windowed_path = os.path.join(dest_dir, '_windowed_source.mp4')
            extract_window_clip(rally_clip, rec['peak_time_sec'], windowed_path)

            attach_clip_urls(result, windowed_path, dest_key=row['id'])
            conn.execute('UPDATE analyses SET result_json = ? WHERE id = ?', (json.dumps(result), row['id']))
            conn.commit()
            os.remove(windowed_path)
            print(f'  analysis {row["id"]} (rally{rally_id} swing{swing_index}): re-cropped OK')
        except Exception as e:
            counts['error'] += 1
            print(f'  analysis {row["id"]}: ERROR {e}', file=sys.stderr)

    conn.close()
    print(f'\nSummary ({"DRY RUN" if args.dry_run else "LIVE"}): {counts}')


if __name__ == '__main__':
    main()
