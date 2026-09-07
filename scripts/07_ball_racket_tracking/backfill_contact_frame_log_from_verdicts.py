"""
One-off: turn Jack's 137+ Pro Clip Review contact-time corrections into
contact-frame training examples.

Each 'contact_time_corrected' verdict in
data/06_pro_database/clip_review_log.jsonl has a note "<old>s -> <new>s"
(clip-relative contact times). old = the original automated wrist-velocity
peak, new = Jack's corrected frame. Logged as:
  student_frame  = round(old * fps)   (clip-relative)
  teacher_frame  = round(new * fps)
  student_method = 'swing_detector_wrist_peak'   (NOT find_contact_frame --
                   flagged with a distinct method so the trainer's one-hot
                   can weight this source separately)
  source         = 'pro_clip_review'

For entries corrected more than once, student = the earliest "old", teacher
= the latest "new" (the final agreed frame).

Idempotent: refuses to run if pro_clip_review rows already exist, unless
--force.

Usage:  python backfill_contact_frame_log_from_verdicts.py [--force] [--dry-run]
"""
import argparse
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))

import clip_review_log  # noqa: E402
import contact_frame_training_log as frame_log  # noqa: E402
from rebuild_helpers import build_swing_lookup  # noqa: E402


def _parse_note(note):
    """'1.001 -> 1.068' (with or without trailing 's') -> (1.001, 1.068), or None."""
    if not note or '->' not in note:
        return None
    left, right = note.split('->', 1)
    try:
        return float(left.strip().rstrip('s')), float(right.strip().rstrip('s'))
    except ValueError:
        return None


def _id_parts(entry_id):
    shot_type, _, sid = entry_id.rpartition('_')
    try:
        return shot_type, int(sid)
    except ValueError:
        return None, None


def backfill(force=False, dry_run=False):
    if not os.path.exists(clip_review_log.LOG_PATH):
        print(f'No review log at {clip_review_log.LOG_PATH}')
        return

    existing = [r for r in frame_log.read_log() if r.get('source') == 'pro_clip_review']
    if existing and not force:
        print(f'{len(existing)} pro_clip_review rows already logged -- pass --force to add more.')
        return

    # earliest "old" and latest "new" per entry
    first_old, last_new = {}, {}
    with open(clip_review_log.LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r['verdict'] != 'contact_time_corrected':
                continue
            parsed = _parse_note(r.get('note'))
            if not parsed:
                continue
            old, new = parsed
            first_old.setdefault(r['entry_id'], old)
            last_new[r['entry_id']] = new

    lookup = build_swing_lookup()
    logged = skipped_note = skipped_lookup = 0
    for entry_id, old in first_old.items():
        shot_type, swing_id = _id_parts(entry_id)
        if swing_id is None:
            skipped_note += 1
            continue
        found = lookup.get((shot_type, swing_id))
        if not found:
            skipped_lookup += 1
            continue
        fps = found['fps']
        student_frame = round(old * fps)
        teacher_frame = round(last_new[entry_id] * fps)
        if not dry_run:
            frame_log.log_example(
                student_frame, None, 'swing_detector_wrist_peak', teacher_frame, fps,
                source='pro_clip_review',
                student_meta={'contact_method': 'swing_detector_wrist_peak'},
            )
        logged += 1

    print(f'{"would log" if dry_run else "logged"}: {logged}')
    print(f'skipped (unparseable id/note): {skipped_note}')
    print(f'skipped (no swings_validated lookup): {skipped_lookup}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    backfill(force=args.force, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
