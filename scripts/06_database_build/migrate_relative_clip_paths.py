"""
One-off migration: rewrite pro_database.json's clip_path entries from a
machine-specific absolute path to a path relative to 04_clips.

Why: build_pro_database.py used to store the raw absolute path
extract_clips.py wrote (e.g. C:\\Users\\jackp\\...\\04_clips\\forehand\\
forehand_swing_0004_conf75.mp4). backend/src/utils/videoCrop.js's toUrl()
does path.relative() against that string on whatever OS is actually serving
the file -- fine on the machine that built the database, broken the moment
it's deployed elsewhere (confirmed live: every pro-clip video 404'd as
"Video unavailable" on the Linux server, since Node's POSIX path module
doesn't parse "C:\\..." as absolute). build_pro_database.py now stores a
relative path going forward; this script fixes the already-built file
in place (a full rebuild is far more expensive and unnecessary).

Usage:
  python migrate_relative_clip_paths.py

Safe to re-run: entries that don't contain a "04_clips" path segment are
left untouched (covers already-migrated entries).
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
BACKUP_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database_backup_pre_relative_clip_path.json')


def make_relative(clip_path):
    if not clip_path:
        return clip_path
    normalized = clip_path.replace('\\', '/')
    marker = '04_clips/'
    idx = normalized.find(marker)
    if idx == -1:
        # No 04_clips segment found -- already relative (idempotent re-run),
        # leave untouched rather than guess.
        return normalized
    return normalized[idx + len(marker):]


def main():
    if not os.path.exists(BACKUP_PATH):
        shutil.copyfile(DB_PATH, BACKUP_PATH)
        print(f'Backed up to {BACKUP_PATH}')
    else:
        print(f'Backup already exists at {BACKUP_PATH}, not overwriting')

    with open(DB_PATH, encoding='utf-8') as f:
        db = json.load(f)

    changed = 0
    for entry in db.get('entries', []):
        old = entry.get('clip_path')
        new = make_relative(old)
        if new != old:
            entry['clip_path'] = new
            changed += 1

    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f)

    print(f'{changed} of {len(db.get("entries", []))} entries updated')


if __name__ == '__main__':
    main()
