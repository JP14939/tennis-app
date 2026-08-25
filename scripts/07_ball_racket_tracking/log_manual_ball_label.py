"""
Logs Jack's manually-drawn ball box (or "no ball" verdict) from the Dev
Page's DevBallLabelScreen.js -- the fallback for frames the classical-
detector-plus-Claude-confirm pipeline couldn't resolve, plus spot-check
corrections when he disagrees with an already-confirmed automated label.

Usage:
  echo '{"file": "analysis534_f47_before.jpg", "bucket": "near_contact",
         "ball_visible": true, "box_norm": {"x1":0.1,"y1":0.2,"x2":0.15,"y2":0.25},
         "is_live_ball": true}' \
      | python log_manual_ball_label.py

Output (stdout): {"logged": true}

`is_live_ball` (only meaningful when ball_visible is true): whether the
boxed ball is the one actually being played, vs. a static decoy Jack boxed
because the real in-play ball wasn't visible in that frame. Labels logged
before this field existed have no way to distinguish the two after the
fact -- see scripts/07_ball_racket_tracking/audit_ball_label_motion.py,
which flags likely-decoy sequences in that older data via a motion check.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '10b_ball_detection', 'manual_ball_label_log.jsonl')


def main():
    payload = json.loads(sys.stdin.read())
    ball_visible = bool(payload.get('ball_visible'))
    record = {
        'file': payload['file'],
        'bucket': payload.get('bucket'),
        'ball_visible': ball_visible,
        'box_norm': payload.get('box_norm'),  # None if ball_visible is False
        # None when ball_visible is False (the field is meaningless there);
        # otherwise defaults True (the common case) unless the labeler
        # explicitly flagged the boxed ball as a static decoy, not the one
        # actually in play.
        'is_live_ball': (payload.get('is_live_ball', True) if ball_visible else None),
        'timestamp': time.time(),
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + '\n')
    print(json.dumps({'logged': True}))


if __name__ == '__main__':
    main()
