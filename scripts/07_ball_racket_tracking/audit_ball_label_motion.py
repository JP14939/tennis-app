"""
Audit manual_ball_label_log.jsonl for likely static-decoy contamination.

Before the `is_live_ball` field existed (see log_manual_ball_label.py),
Jack's labeling practice for a frame where the real in-play ball wasn't
visible was sometimes to box a *static* ball instead (one sitting on
court, not being played) rather than leave the frame unlabeled -- logged
identically to a real label (`ball_visible: true` + a box), with no way to
tell the two apart after the fact.

Jack's own disambiguating rule -- "if it isn't moving, it's not the ball
being played" -- is directly checkable: group labels by source clip
(`analysisNNN_fNN_<bucket>.jpg` filenames identify both), and measure
pixel displacement between consecutive same-clip labels. A single
near-zero pair right at the contact frame is expected real physics (a
ball's apparent motion bottoms out at the instant of contact) and isn't
flagged; a clip whose *entire* labeled sequence shows near-zero motion is
a strong signal that a static object was boxed throughout, not the real
ball.

Does NOT modify or delete anything in the log -- just produces a report
(flagged clip list) for Jack to make the keep/exclude call on, same
spirit as audit_ball_visibility.py's report-only pattern.

Usage:
  python audit_ball_label_motion.py [path/to/manual_ball_label_log.jsonl]

  Defaults to data/10b_ball_detection/manual_ball_label_log.jsonl (where
  log_manual_ball_label.py writes) -- pass an explicit path when auditing a
  copy pulled from the hosted server, since that's currently the only place
  real label data lives (local dev's copy is empty).

Output (stdout): JSON report; also written to
  data/10b_ball_detection/ball_label_motion_audit.json
"""
import collections
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

DEFAULT_LOG_PATH = os.path.join(DATA_DIR, '10b_ball_detection', 'manual_ball_label_log.jsonl')
OUT_PATH = os.path.join(DATA_DIR, '10b_ball_detection', 'ball_label_motion_audit.json')

FILE_PATTERN = re.compile(r'^(analysis\d+)_f(\d+)_')

# Normalised units/frame -- ~4px on a 1920px-wide source frame. Below this,
# two consecutive labels are treated as "the same object didn't move."
STATIONARY_THRESHOLD_PER_FRAME = 0.004


def box_center(box_norm):
    return (box_norm['x1'] + box_norm['x2']) / 2, (box_norm['y1'] + box_norm['y2']) / 2


def load_records(log_path):
    if not os.path.exists(log_path):
        raise FileNotFoundError(
            f'{log_path} not found -- pass the path to a local copy of the real log '
            '(local dev\'s own copy is typically empty; the real data lives on the hosted server).'
        )
    with open(log_path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def group_by_clip(records):
    """Only labels already carrying a real box, grouped by source clip
    (analysisNNN) in ascending frame order. Records with a filename that
    doesn't match the analysisNNN_fNN_ pattern (e.g. the negative_candidates
    bucket's raw-source-video frames) aren't part of a comparable sequence
    and are skipped."""
    groups = collections.defaultdict(list)
    for r in records:
        if not r.get('ball_visible') or not r.get('box_norm'):
            continue
        m = FILE_PATTERN.match(r['file'])
        if not m:
            continue
        clip_id, frame = m.group(1), int(m.group(2))
        groups[clip_id].append((frame, r))
    for clip_id in groups:
        groups[clip_id].sort(key=lambda pair: pair[0])
    return groups


def audit(log_path=None):
    log_path = log_path or DEFAULT_LOG_PATH
    records = load_records(log_path)
    visible_count = sum(1 for r in records if r.get('ball_visible'))
    groups = group_by_clip(records)

    fully_static, partially_flagged, clean = [], [], []
    for clip_id, items in groups.items():
        if len(items) < 2:
            continue
        pair_flags = []
        for (f0, r0), (f1, r1) in zip(items, items[1:]):
            gap = f1 - f0
            if gap <= 0:
                continue
            (x0, y0), (x1, y1) = box_center(r0['box_norm']), box_center(r1['box_norm'])
            per_frame = math.hypot(x1 - x0, y1 - y0) / gap
            pair_flags.append(per_frame < STATIONARY_THRESHOLD_PER_FRAME)
        if not pair_flags:
            continue
        entry = {'clip_id': clip_id, 'files': [r['file'] for _, r in items]}
        if all(pair_flags):
            fully_static.append(entry)
        elif any(pair_flags):
            partially_flagged.append(entry)
        else:
            clean.append(entry)

    report = {
        'log_path': log_path,
        'total_records': len(records),
        'ball_visible_records': visible_count,
        'comparable_clips': len(groups),
        # Whole sequence near-zero motion -- likely a static decoy labeled
        # throughout. These are the ones worth a manual keep/exclude call.
        'fully_static_flagged': fully_static,
        # Near-zero only in one pair (usually before->contact) -- expected
        # physics, not flagged for review.
        'partially_flagged_not_concerning': partially_flagged,
        'clean_clip_count': len(clean),
    }
    return report


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else None
    result = audit(path)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
