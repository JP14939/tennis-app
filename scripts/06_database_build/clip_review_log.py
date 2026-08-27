"""
Log of Jack's manual data-quality verdicts on pro-database clips (Dev
Page's Pro Clip Review tool, DevProClipReviewScreen.js) -- mismatched
footage, slow-motion clips, clips spanning the tail of one swing/player
into the start of another. Mirrors tip_reviewed_log.py's identity-log
pattern exactly (append-only JSONL, get_reviewed_set() for "don't re-serve
this one"), plus the verdict itself so a later pass can rebuild
pro_database.json excluding flagged entries (same shape as
filter_by_ball_visibility.py's audit-then-filter pattern) -- not a
teacher-student training log, this is data-quality curation, not an ML loop.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '06_pro_database', 'clip_review_log.jsonl')

# 'excluded' is a catch-all "don't use this clip" verdict for clips that are
# bad but don't cleanly fit the more specific reasons below. 'cut' is logged
# automatically by cut_pro_clip.py, not chosen directly in the review UI --
# it means the clip was fixed by trimming rather than flagged for exclusion.
# 'shot_type_corrected' is likewise logged automatically, by
# correct_shot_type.py -- the clip was fixed by relabeling/moving it to the
# right shot type, not excluded.
VERDICTS = ('ok', 'mismatched', 'slow_motion', 'wrong_boundary', 'excluded', 'cut', 'shot_type_corrected')


def log_verdict(entry_id, verdict, note=None, name=None):
    if verdict not in VERDICTS:
        raise ValueError(f'Unknown verdict {verdict!r}, expected one of {VERDICTS}')
    record = {'entry_id': entry_id, 'verdict': verdict, 'note': note, 'name': name, 'timestamp': time.time()}
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + '\n')


def get_reviewed_set():
    """Returns a set of already-reviewed entry_ids."""
    if not os.path.exists(LOG_PATH):
        return set()
    reviewed = set()
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            reviewed.add(json.loads(line)['entry_id'])
    return reviewed


def get_latest_verdicts():
    """Returns {entry_id: verdict} using each id's most recent logged line
    (in case of a re-review) -- what a later filter-and-rebuild pass would
    read to decide which entries to drop."""
    if not os.path.exists(LOG_PATH):
        return {}
    verdicts = {}
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            verdicts[r['entry_id']] = r['verdict']
    return verdicts
