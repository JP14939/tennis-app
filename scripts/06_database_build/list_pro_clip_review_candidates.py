"""
Lists pro-database entries for the Dev Page's Pro Clip Review tool -- a
manual data-quality pass (mismatched footage / slow-motion / clips
spanning two different swings or players), not a teacher-student ML loop.
Same free, no-Claude-cost, one-at-a-time pattern already established for
Swing Review / Rally Boundary Review / Tip Review.

Usage:
  python list_pro_clip_review_candidates.py [limit]

Output (stdout): {"candidates": [{id, shot_type, clip_url, camera_angle,
  confidence}, ...]}
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))

from paths import DATA_DIR  # noqa: E402
from clip_urls import to_url, PRO_CLIPS_DIR  # noqa: E402
from clip_review_log import get_reviewed_set  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')

DEFAULT_LIMIT = 20


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LIMIT

    reviewed = get_reviewed_set()
    with open(PRO_DB_PATH) as f:
        db = json.load(f)

    candidates = []
    for entry in db['entries']:
        if len(candidates) >= limit:
            break
        if entry['id'] in reviewed:
            continue
        clip_abs_path = os.path.join(PRO_CLIPS_DIR, entry['clip_path'])
        if not os.path.exists(clip_abs_path):
            continue  # clip missing on disk -- nothing to review
        candidates.append({
            'id': entry['id'],
            'shot_type': entry['shot_type'],
            'clip_url': to_url('/pro-clips', PRO_CLIPS_DIR, clip_abs_path),
            'camera_angle': entry.get('camera_angle'),
            'confidence': entry.get('confidence'),
        })

    print(json.dumps({'candidates': candidates}))


if __name__ == '__main__':
    main()
