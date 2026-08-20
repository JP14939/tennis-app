"""
Logs Jack's own manual verdict on a tip-review candidate (from the Dev
Page's DevTipReviewScreen.js) -- the free, no-Claude-cost substitute for
tip_verifier.py, same pattern log_manual_review.py already established for
shot verification/classification.

Usage:
  echo '{"analysis_id": 123, "shot_type": "forehand",
         "deviation_features": [...], "shown_tip_ids": ["fh_wrist_collapse"],
         "reviewer_pick_ids": ["fh_wrist_collapse", "fh_hip_rotation"]}' \
      | python log_manual_tip_review.py

Output (stdout): {"logged": true, "agreed": bool}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tip_training_log  # noqa: E402
import tip_reviewed_log  # noqa: E402


def main():
    payload = json.loads(sys.stdin.read())

    shown_tip_ids = payload.get('shown_tip_ids') or []
    reviewer_pick_ids = payload.get('reviewer_pick_ids') or []
    agreed = sorted(shown_tip_ids) == sorted(reviewer_pick_ids)

    tip_training_log.log_example(
        payload['shot_type'],
        payload.get('deviation_features'),
        shown_tip_ids,
        reviewer_pick_ids,
        agreed,
        source='user_flag',
    )
    tip_reviewed_log.log_reviewed(payload['analysis_id'])

    print(json.dumps({'logged': True, 'agreed': agreed}))


if __name__ == '__main__':
    main()
