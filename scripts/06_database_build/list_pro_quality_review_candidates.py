"""
Lists pro-database entries for the Dev Page's Pro Quality Review tool
(roadmap 1b B1.6) -- tags each clip's TECHNIQUE quality (gold / ok / exclude),
orthogonal to Pro Clip Review's label-accuracy verdicts. Same free,
no-Claude-cost, one-at-a-time pattern as Amateur Clip Review, applied to the
pro database this time: no cut/split/contact-time correction here, just a tag.

Why: the technique-score rubric compares a user's swing against the pro
database's OWN distribution per axis -- how tight/discriminating that
distribution is directly gates how well the score can separate good from bad
technique. A gold-tagged subset (Jack's manual "this is textbook" call) lets
`redesign_similarity.py`/`build_technique_axis_stats.py` optionally score
against a tighter reference pool. See clip_review_log.py's quality-tiering
section for why this is a SEPARATE log from the label-review one.

Usage:
  python list_pro_quality_review_candidates.py [--shot-type forehand] [limit]

Output (stdout): {"candidates": [{id, shot_type, clip_url, camera_angle,
  view_direction}, ...], "progress": {total, by_shot_type: {shot: {tagged, total}},
  by_tier: {tier: count}}}
"""
import argparse
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paths import DATA_DIR  # noqa: E402
from clip_urls import to_url, PRO_CLIPS_DIR  # noqa: E402
import clip_review_log  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')


def list_candidates(shot_type=None, limit=None):
    with open(PRO_DB_PATH) as f:
        entries = json.load(f)['entries']

    tiers = clip_review_log.get_quality_tiers()

    by_shot_type = {}
    by_tier = {}
    candidates = []
    for e in entries:
        st = e['shot_type']
        bucket = by_shot_type.setdefault(st, {'tagged': 0, 'total': 0})
        bucket['total'] += 1
        tier = tiers.get(e['id'])
        if tier:
            bucket['tagged'] += 1
            by_tier[tier] = by_tier.get(tier, 0) + 1
            continue
        if shot_type and st != shot_type:
            continue
        candidates.append({
            'id': e['id'],
            'shot_type': st,
            'clip_url': to_url('/pro-clips', PRO_CLIPS_DIR, os.path.join(PRO_CLIPS_DIR, e['clip_path'])),
            'camera_angle': e.get('camera_angle'),
            'view_direction': e.get('view_direction'),
        })

    # untagged-first is implicit (tagged entries are excluded entirely, same
    # "server-side filtering means already-reviewed clips don't come back"
    # convention as list_pro_clip_review_candidates.py / the amateur tool).
    candidates.sort(key=lambda c: (c['shot_type'], c['id']))

    if limit:
        candidates = candidates[:int(limit)]

    return {
        'candidates': candidates,
        'progress': {
            'total': len(entries),
            'by_shot_type': by_shot_type,
            'by_tier': by_tier,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shot-type', default=None, choices=('forehand', 'backhand', 'serve'))
    ap.add_argument('limit', nargs='?', default=None)
    args = ap.parse_args()
    print(json.dumps(list_candidates(args.shot_type, args.limit)))


if __name__ == '__main__':
    main()
