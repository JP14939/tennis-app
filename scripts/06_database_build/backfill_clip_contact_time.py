"""
One-off backfill: add 'clip_contact_time_sec' to every existing
pro_database.json entry, without re-running the full (slow, angle-inference-
heavy) build_database().

Bug this fixes: entries only stored 'peak_time' (contact time within the
SOURCE compilation video), but compare_swing.py / the frontend seek into
'clip_path' -- a separately cut ~3s clip file whose own frame 0 is
sw['start_frame'] in the source, not frame 0 of the source. Seeking to
'peak_time' on the clip file lands on the wrong frame (or gets clamped).
'clip_contact_time_sec' = (peak_frame - start_frame) / fps is the value that
actually lines up with clip_path's own timeline.

Usage: python backfill_clip_contact_time.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_pro_database import JOBS, MIN_CONFIDENCE  # noqa: E402

DB_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'


def main():
    with open(DB_PATH, encoding='utf-8') as f:
        db = json.load(f)

    print('Indexing swings across all JOBS...')
    lookup = {}  # (shot_type, swing_id) -> (fps, peak_frame, start_frame)
    for job in JOBS:
        with open(job['poses'], encoding='utf-8') as f:
            fps = json.load(f)['fps']
        with open(job['swings_validated'], encoding='utf-8') as f:
            swing_data = json.load(f)
        for sw in swing_data['swings']:
            if sw.get('confidence', 0) < MIN_CONFIDENCE:
                continue
            lookup[(job['shot_type'], sw['swing_id'])] = (fps, sw['peak_frame'], sw['start_frame'])

    patched = missing = 0
    for entry in db['entries']:
        found = lookup.get((entry['shot_type'], entry['swing_id']))
        if not found:
            missing += 1
            continue
        fps, peak_frame, start_frame = found
        entry['clip_contact_time_sec'] = round((peak_frame - start_frame) / fps, 3)
        patched += 1

    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f)

    print(f'Patched {patched}/{len(db["entries"])} entries ({missing} swing_id not found)')
    print(f'Saved to {DB_PATH}')


if __name__ == '__main__':
    main()
