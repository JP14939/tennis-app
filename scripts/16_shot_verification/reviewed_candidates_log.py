"""
Identity log of which swing candidates Jack has already reviewed in the Dev
Page's Swing Review tool (DevSwingReviewScreen.js) -- distinct from the
three training logs log_manual_review.py also writes to
(shot_contact_training_log.py etc.), which only store anonymous
student/teacher prediction pairs for trust-rate math and have no notion of
"which candidate" a verdict belonged to.

Without this, list_swing_candidates.py has no way to know a candidate was
already labeled, so reopening the Swing Review screen for a job (a reload,
navigating away and back, re-running the job) re-served the exact same full
candidate list every time -- forcing a full re-review of everything already
done. This log lets the listing script filter those out.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '16_shot_verification', 'reviewed_candidates_log.jsonl')


def log_reviewed(job_id, rally_id, swing_index):
    """Records that (job_id, rally_id, swing_index) has been given a verdict."""
    record = {
        'job_id': str(job_id),
        'rally_id': rally_id,
        'swing_index': swing_index,
        'timestamp': time.time(),
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + '\n')


def get_reviewed_set(job_id):
    """Returns a set of (rally_id, swing_index) tuples already reviewed for this job_id."""
    if not os.path.exists(LOG_PATH):
        return set()
    job_id = str(job_id)
    reviewed = set()
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get('job_id') == job_id:
                reviewed.add((r['rally_id'], r['swing_index']))
    return reviewed
