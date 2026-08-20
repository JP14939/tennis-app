"""
Logs Jack's manually-drawn ball box (or "no ball" verdict) from the Dev
Page's DevBallLabelScreen.js -- the fallback for frames the classical-
detector-plus-Claude-confirm pipeline couldn't resolve, plus spot-check
corrections when he disagrees with an already-confirmed automated label.

Usage:
  echo '{"file": "analysis534_f47_before.jpg", "bucket": "near_contact",
         "ball_visible": true, "box_norm": {"x1":0.1,"y1":0.2,"x2":0.15,"y2":0.25}}' \
      | python log_manual_ball_label.py

Output (stdout): {"logged": true}
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
    record = {
        'file': payload['file'],
        'bucket': payload.get('bucket'),
        'ball_visible': bool(payload.get('ball_visible')),
        'box_norm': payload.get('box_norm'),  # None if ball_visible is False
        'timestamp': time.time(),
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + '\n')
    print(json.dumps({'logged': True}))


if __name__ == '__main__':
    main()
