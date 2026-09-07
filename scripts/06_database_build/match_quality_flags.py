"""
Reader + summary for user "this doesn't look like my swing" flags on the DTW
pro-match result.

Written by the backend (backend/src/routes/history.js's logMatchQualityFlag)
when a user taps the flag on ResultsScreen. Deliberately NOT part of
clip_review_log.py: those verdicts drive a rebuild-and-exclude pass, and one
user's dislike is far weaker signal than a reviewed exclusion. This is a raw
match-quality signal -- the cheapest way to start answering "is the
comparison any good" before a labelled eval set exists (see
docs/future-ideas.md 2026-09-07).

Record shape (one JSON object per line):
  timestamp, source ('user_flag'), analysis_id, user_id,
  pro_entry_id, player_name, shot_type, similarity, angle_label

Usage:
  python match_quality_flags.py            # print a summary
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '06_pro_database', 'match_quality_flags.jsonl')


def load_flags():
    """All flag records, oldest first. [] if nothing's been flagged yet."""
    if not os.path.exists(LOG_PATH):
        return []
    out = []
    with open(LOG_PATH, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def summary(flags=None):
    flags = load_flags() if flags is None else flags
    if not flags:
        return {'total': 0}

    sims = [f['similarity'] for f in flags if isinstance(f.get('similarity'), (int, float))]
    return {
        'total': len(flags),
        'distinct_users': len({f.get('user_id') for f in flags}),
        'by_shot_type': dict(Counter(f.get('shot_type') for f in flags)),
        'by_angle_label': dict(Counter(f.get('angle_label') for f in flags)),
        # A pro entry flagged by several different people is a much stronger
        # "this clip is a bad match target" signal than one flagged once.
        'most_flagged_entries': Counter(f.get('pro_entry_id') for f in flags).most_common(10),
        'flagged_similarity': {
            'n': len(sims),
            'min': round(min(sims), 1) if sims else None,
            'median': round(sorted(sims)[len(sims) // 2], 1) if sims else None,
            'max': round(max(sims), 1) if sims else None,
        },
    }


if __name__ == '__main__':
    s = summary()
    if s['total'] == 0:
        print(f'No match-quality flags yet ({LOG_PATH}).')
    else:
        print(json.dumps(s, indent=2))
