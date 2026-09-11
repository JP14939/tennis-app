"""
Tags one pro-database clip's technique-quality tier (Dev Page's Pro Quality
Review tool, roadmap 1b B1.6). Writes to clip_review_log.QUALITY_LOG_PATH via
clip_review_log.log_quality_tier() -- a log fully separate from the existing
label-review verdict log (see that module's quality-tiering section for why).

Usage:
  echo '{"id": "forehand_0004", "tier": "gold"}' | python tag_pro_quality.py

Output (stdout): {"tagged": true, "id": ..., "tier": ...}
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA_DIR  # noqa: E402
import clip_review_log  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')


def main():
    payload = json.loads(sys.stdin.read())
    entry_id = payload['id']
    tier = payload['tier']

    with open(PRO_DB_PATH) as f:
        entries = json.load(f)['entries']
    if not any(e['id'] == entry_id for e in entries):
        print(json.dumps({'error': f'No pro database entry with id {entry_id!r}'}))
        sys.exit(1)

    try:
        clip_review_log.log_quality_tier(entry_id, tier)
    except ValueError as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

    print(json.dumps({'tagged': True, 'id': entry_id, 'tier': tier}))


if __name__ == '__main__':
    main()
