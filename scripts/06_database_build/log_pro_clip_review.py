"""
Logs Jack's manual data-quality verdict on one pro-database clip (Dev
Page's DevProClipReviewScreen.js).

Usage:
  echo '{"id": "forehand_0004", "verdict": "ok", "note": null}' \
      | python log_pro_clip_review.py

Output (stdout): {"logged": true}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip_review_log  # noqa: E402


def main():
    payload = json.loads(sys.stdin.read())
    clip_review_log.log_verdict(payload['id'], payload['verdict'], payload.get('note'))
    print(json.dumps({'logged': True}))


if __name__ == '__main__':
    main()
