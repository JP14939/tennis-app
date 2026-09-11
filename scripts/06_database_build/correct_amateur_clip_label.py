"""
Corrects a shot-type label on one amateur swing candidate from Jack's
Amateur Clip Review tool (DevAmateurClipReviewScreen.js). Two sources, two
storage locations (see list_amateur_clip_review_candidates.py):

  - amateur_eval (id "<video_id>_<swing_id>"): writes into
    data/08_coaching_ai/amateur_swing_labels.json's `labels` dict. No clip
    file to move -- every amateur candidate clip lives flat in
    data/04_clips/amateur/ regardless of label, so this is a pure JSON relabel.
  - raw_ingest (id "raw:<video_id>:<index>"): the older raw-footage-ingest
    batches (IMG_5822/5823) -- relabels that video's own ingest_report.json
    in place ('review-only' stream, not wired into the real eval set; see
    list_amateur_clip_review_candidates.py's module docstring). The original
    automated-classifier guess is preserved as `auto_shot_type` the first
    time an entry is touched, and `manually_reviewed` is set so the review
    queue stops resurfacing it.

Usage:
  echo '{"id": "rNMc9tpWWZ0_100001", "new_label": "backhand"}' \
      | python correct_amateur_clip_label.py
  echo '{"id": "raw:IMG_5822:1", "new_label": "backhand"}' \
      | python correct_amateur_clip_label.py

Output (stdout): {"corrected": true, "id": ..., "old_label": ..., "new_label": ...}

Every call also appends one line to REVIEW_LOG_PATH (amateur_clip_review_log.jsonl)
-- an actual audit trail, added 2026-09-11 after a real gap: the `reviewed`
list on its own says WHETHER an id has been looked at, but nothing recorded
WHEN or in what order, so there was no way to answer "which ones did I
already do" for anything reviewed before this log existed. Going forward
this is queryable; it can't retroactively reconstruct anything from before it.
"""
import json
import os
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
from paths import DATA_DIR  # noqa: E402

LABELS_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'amateur_swing_labels.json')
RAW_INGEST_DIR = os.path.join(DATA_DIR, 'runtime', 'raw_footage_ingest')
REVIEW_LOG_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'amateur_clip_review_log.jsonl')

VALID_LABELS = ('forehand', 'backhand', 'serve', 'skip')


def _log_review(cid, source, old_label, new_label):
    os.makedirs(os.path.dirname(REVIEW_LOG_PATH), exist_ok=True)
    with open(REVIEW_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'id': cid,
            'source': source,
            'old_label': old_label,
            'new_label': new_label,
            'changed': old_label != new_label,
        }) + '\n')


def _correct_amateur_eval_label(cid, new_label):
    with open(LABELS_PATH, encoding='utf-8') as f:
        data = json.load(f)

    if cid not in data['labels']:
        raise ValueError(f'No amateur swing candidate with id {cid!r}')

    old_label = data['labels'][cid]
    data['labels'][cid] = new_label

    # `reviewed`: ids Jack has looked at THIS re-review pass, independent of
    # whether the label actually changed -- confirming an already-correct
    # label must still count, or that candidate would keep resurfacing at
    # the front of the queue forever (2026-09-11 fix: "why has my other
    # progress not registered" -- it HAD registered on disk, the tool just
    # had no memory of what was already seen, so navigating back into the
    # screen re-fetched the same unfiltered list and restarted at 1).
    reviewed = set(data.get('reviewed', []))
    reviewed.add(cid)
    data['reviewed'] = sorted(reviewed)

    with open(LABELS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    _log_review(cid, 'amateur_eval', old_label, new_label)
    return {'old_label': old_label, 'new_label': new_label}


def _correct_raw_ingest_label(cid, new_label):
    _prefix, video_id, index_str = cid.split(':', 2)
    index = int(index_str)
    report_path = os.path.join(RAW_INGEST_DIR, video_id, 'ingest_report.json')
    if not os.path.isfile(report_path):
        raise ValueError(f'No raw-ingest report for video {video_id!r}')

    with open(report_path, encoding='utf-8') as f:
        entries = json.load(f)
    entry = next((e for e in entries if e.get('index') == index), None)
    if entry is None:
        raise ValueError(f'No raw-ingest candidate with id {cid!r}')

    old_label = entry.get('shot_type')
    if 'auto_shot_type' not in entry:
        entry['auto_shot_type'] = old_label
    entry['shot_type'] = new_label
    entry['manually_reviewed'] = True

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f)

    _log_review(cid, 'raw_ingest', old_label, new_label)
    return {'old_label': old_label, 'new_label': new_label}


def correct_label(cid, new_label):
    """Core logic, separate from main()'s stdin plumbing (unit-testable).
    Raises ValueError with a user-facing message on any rejected input."""
    if new_label not in VALID_LABELS:
        raise ValueError(f'Unknown label {new_label!r}, expected one of {VALID_LABELS}')

    if cid.startswith('raw:'):
        return _correct_raw_ingest_label(cid, new_label)
    return _correct_amateur_eval_label(cid, new_label)


def main():
    payload = json.loads(sys.stdin.read())
    try:
        result = correct_label(payload['id'], payload['new_label'])
    except (KeyError, ValueError) as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

    print(json.dumps({'corrected': True, 'id': payload['id'], **result}))


if __name__ == '__main__':
    main()
