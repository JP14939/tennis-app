"""
Lists ball-label frames flagged needs_manual_review=true (from
label_ball_frames.py's output) for the Dev Page's manual ball-labeling
tool -- the fallback for frames the classical-detector-plus-Claude-confirm
pipeline couldn't resolve on its own (see the ball detector project plan).

Also serves a small sample of already-CONFIRMED labels (bucket
'spotcheck') so Jack can spot-check the automated pipeline's accuracy the
same way this project's own testing did before trusting it -- not just
label the hard cases blind.

Usage:
  python list_ball_label_candidates.py [limit]

Output (stdout): {"candidates": [{file, bucket, image_url, note}, ...]}
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '00_utils'))
from paths import DATA_DIR  # noqa: E402
from clip_urls import to_url  # noqa: E402

CANDIDATE_FRAMES_DIR = os.path.join(DATA_DIR, '10b_ball_detection', 'candidate_frames')
LABELS_PATH = os.path.join(DATA_DIR, '10b_ball_detection', 'ball_labels_v2.json')
REVIEWED_LOG_PATH = os.path.join(DATA_DIR, '10b_ball_detection', 'manual_ball_label_log.jsonl')

DEFAULT_LIMIT = 30
SPOTCHECK_FRACTION = 0.15  # small slice of already-confirmed labels mixed in for spot-checking


def _get_reviewed_set():
    if not os.path.exists(REVIEWED_LOG_PATH):
        return set()
    reviewed = set()
    with open(REVIEWED_LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            reviewed.add(json.loads(line)['file'])
    return reviewed


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LIMIT

    if not os.path.exists(LABELS_PATH):
        print(json.dumps({'candidates': [], 'error': 'ball_labels_v2.json not found -- run label_ball_frames.py first'}))
        return

    with open(LABELS_PATH) as f:
        labels = json.load(f)

    reviewed = _get_reviewed_set()
    needs_review = [l for l in labels if l['needs_manual_review'] and l['file'] not in reviewed]
    confirmed = [l for l in labels if not l['needs_manual_review'] and l['file'] not in reviewed]

    random.seed(42)
    random.shuffle(needs_review)
    random.shuffle(confirmed)

    n_spotcheck = min(len(confirmed), max(1, int(limit * SPOTCHECK_FRACTION)))
    n_review = limit - n_spotcheck

    selected = [(l, 'needs_review') for l in needs_review[:n_review]] + \
               [(l, 'spotcheck') for l in confirmed[:n_spotcheck]]
    random.shuffle(selected)

    candidates = []
    for label, purpose in selected:
        img_path = os.path.join(CANDIDATE_FRAMES_DIR, label['bucket'], label['file'])
        if not os.path.exists(img_path):
            continue
        candidates.append({
            'file': label['file'],
            'bucket': label['bucket'],
            'purpose': purpose,  # 'needs_review' (no confirmed label yet) or 'spotcheck' (already auto-labeled)
            'image_url': to_url('/ball-label-frames', CANDIDATE_FRAMES_DIR, img_path),
            'existing_box_norm': label.get('box_norm'),  # only set for spotcheck rows
            'note': label.get('note'),
        })

    print(json.dumps({'candidates': candidates}))


if __name__ == '__main__':
    main()
