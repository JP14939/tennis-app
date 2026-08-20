"""
Phase 2 (labeling) of the fine-tuned ball detector project. Batch driver:
for every candidate frame sourced by sample_ball_frames.py, proposes
candidate ball blobs classically (find_ball_candidates.py, free/local),
crops around each and asks Claude to confirm/reject (ball_presence_
verifier.py's verify_ball_candidate_crop() -- binary judgment, not a
coordinate guess, see that module's docstring for why the original
freeform-localization approach was replaced).

Frames where NO candidate is confirmed (classical detector found nothing
plausible, or Claude rejected every candidate it did find) are flagged
needs_manual_review=true rather than silently dropped or force-labeled --
DevBallLabelScreen.js's Dev Page tool serves exactly those.

Usage:
  python label_ball_frames.py [limit]
"""
import json
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '00_utils'))

from paths import DATA_DIR  # noqa: E402
from find_ball_candidates import find_ball_candidates  # noqa: E402
from ball_presence_verifier import verify_ball_candidate_crop, cost_summary  # noqa: E402

CANDIDATE_DIR = os.path.join(DATA_DIR, '10b_ball_detection', 'candidate_frames')
META_PATH = os.path.join(CANDIDATE_DIR, 'candidate_metadata.json')
LABELS_PATH = os.path.join(DATA_DIR, '10b_ball_detection', 'ball_labels_v2.json')

# A confirmed candidate's circle -> box, padded slightly since a circle's
# enclosing box can clip the ball's true edges (fuzzy felt, motion blur).
BOX_PAD_FRAC = 0.25


def _candidate_to_box_norm(candidate, img_w, img_h):
    x, y, r = candidate['x'], candidate['y'], candidate['radius'] * (1 + BOX_PAD_FRAC)
    return {
        'x1': round(max(0, x - r) / img_w, 4), 'y1': round(max(0, y - r) / img_h, 4),
        'x2': round(min(img_w, x + r) / img_w, 4), 'y2': round(min(img_h, y + r) / img_h, 4),
    }


def label_one(img):
    """Returns (ball_visible, box_norm, needs_manual_review, note)."""
    h, w = img.shape[:2]
    candidates = find_ball_candidates(img)
    if not candidates:
        return False, None, True, 'no classical candidates found'

    for c in candidates:
        result = verify_ball_candidate_crop(img, c)
        if result.get('is_ball'):
            return True, _candidate_to_box_norm(c, w, h), False, result.get('reasoning')

    return False, None, True, 'classical candidates found but Claude rejected all of them'


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    with open(META_PATH) as f:
        candidates_meta = json.load(f)
    if limit:
        candidates_meta = candidates_meta[:limit]
    print(f'{len(candidates_meta)} candidate frames to label\n', file=sys.stderr)

    labels = []
    confirmed = needs_review = errors = 0
    for i, cand in enumerate(candidates_meta, 1):
        img_path = os.path.join(CANDIDATE_DIR, cand['bucket'], cand['file'])
        if not os.path.exists(img_path):
            continue
        img = cv2.imread(img_path)
        if img is None:
            continue

        try:
            ball_visible, box_norm, needs_manual_review, note = label_one(img)
        except Exception as e:
            print(f'  [{i}/{len(candidates_meta)}] ERROR {cand["file"]}: {e}', file=sys.stderr)
            errors += 1
            time.sleep(1)
            continue

        if needs_manual_review:
            needs_review += 1
            tag = f'NEEDS MANUAL REVIEW ({note})'
        else:
            confirmed += 1
            tag = f"confirmed ball at ({box_norm['x1']:.2f},{box_norm['y1']:.2f})-({box_norm['x2']:.2f},{box_norm['y2']:.2f})"
        print(f'  [{i}/{len(candidates_meta)}] {cand["file"]}: {tag}', file=sys.stderr)

        labels.append({
            'file': cand['file'], 'bucket': cand['bucket'],
            'source_clip': cand.get('source_clip'), 'source_frame': cand.get('frame'),
            'ball_visible': ball_visible, 'box_norm': box_norm,
            'needs_manual_review': needs_manual_review, 'note': note,
        })

        if i % 20 == 0:
            with open(LABELS_PATH, 'w') as f:
                json.dump(labels, f, indent=2)

    with open(LABELS_PATH, 'w') as f:
        json.dump(labels, f, indent=2)

    cost = cost_summary()
    print(f'\nDone. {confirmed} confirmed, {needs_review} need manual review, {errors} errors.', file=sys.stderr)
    print(f'Labels written to {LABELS_PATH}', file=sys.stderr)
    print(f'Cost so far: {cost["calls"]} calls, ${cost["estimated_cost_usd"]}', file=sys.stderr)


if __name__ == '__main__':
    main()
