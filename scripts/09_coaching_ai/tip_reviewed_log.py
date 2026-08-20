"""
Identity log of which saved analyses Jack has already reviewed in the Dev
Page's Tip Review tool (DevTipReviewScreen.js) -- mirrors
scripts/16_shot_verification/reviewed_candidates_log.py exactly (same
reasoning: without this, list_tip_review_candidates.py would re-serve the
same already-reviewed analyses every time the tool is reopened).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'tip_reviewed_log.jsonl')


def log_reviewed(analysis_id):
    record = {'analysis_id': analysis_id, 'timestamp': time.time()}
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + '\n')


def get_reviewed_set():
    """Returns a set of already-reviewed analysis_ids."""
    if not os.path.exists(LOG_PATH):
        return set()
    reviewed = set()
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            reviewed.add(r['analysis_id'])
    return reviewed
