"""
Lists recent saved analyses for the Dev Page's Tip Review tool, re-deriving
the full scored issue candidate list (tip_selector.score_issues()) for
each so Jack can see not just which tip was shown but the full "why" --
every issue that was scored, its deviation/severity/phase -- and judge
which ones should actually have been flagged. Free, no-Claude-cost manual
review substitute for tip_verifier.py, same pattern already established
for shot verification (scripts/16_shot_verification/list_swing_candidates.py).

Re-derives the user's trajectory fresh (pose extraction + build_user_trajectory
on the persisted user clip, same functions compare_swing.compare() itself
uses) rather than trusting anything precomputed, since result_json only
stores the FINAL tips shown, not the full scored-issue list. The matched
pro's trajectory needs no re-extraction -- pro_database.json already has
it, keyed by pro_id.

Usage:
  python list_tip_review_candidates.py [limit]

Output (stdout): {"candidates": [{analysis_id, shot_type, user_clip_url,
  pro_clip_url, pro_player_name, shown_tip_ids, shown_tips,
  candidate_issues}, ...]}
"""
import json
import os
import sqlite3
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '08_comparison_engine'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '09_coaching_ai'))

from paths import DATA_DIR, BACKEND_DIR  # noqa: E402
from clip_urls import to_url, USER_CLIPS_DIR, PRO_CLIPS_DIR  # noqa: E402
from compare_swing import extract_user_poses, build_user_trajectory  # noqa: E402
from tip_selector import score_issues  # noqa: E402
from tip_reviewed_log import get_reviewed_set  # noqa: E402

DB_PATH = os.path.join(BACKEND_DIR, 'data', 'app.db')
PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
PLAYER_NAMES_PATH = os.path.join(DATA_DIR, '06_pro_database', 'player_names.json')

DEFAULT_LIMIT = 20
# Fetch more rows than `limit` up front since some get skipped (already
# reviewed, missing clip on disk, no matches, etc.) -- avoids serving a
# short list just because the most-recent N rows happened to skip a lot.
OVERFETCH_FACTOR = 4


def _load_pro_trajectories():
    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    return {e['id']: e['trajectory'] for e in db['entries']}


def _load_player_names():
    if not os.path.exists(PLAYER_NAMES_PATH):
        return {}
    with open(PLAYER_NAMES_PATH) as f:
        return json.load(f)


def _user_clip_path(user_clip_url):
    """user_clip_url is like '/user-clips/<dest_key>/original.mp4' -- resolve
    back to a real filesystem path under USER_CLIPS_DIR."""
    if not user_clip_url or not user_clip_url.startswith('/user-clips/'):
        return None
    rel = user_clip_url[len('/user-clips/'):]
    return os.path.join(USER_CLIPS_DIR, *rel.split('/'))


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LIMIT

    reviewed = get_reviewed_set()
    pro_trajectories = _load_pro_trajectories()
    player_names = _load_player_names()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, result_json FROM analyses ORDER BY id DESC LIMIT ?', (limit * OVERFETCH_FACTOR,)
    ).fetchall()
    conn.close()

    candidates = []
    for row in rows:
        if len(candidates) >= limit:
            break
        analysis_id = row['id']
        if analysis_id in reviewed:
            continue

        try:
            result = json.loads(row['result_json'])
        except (json.JSONDecodeError, TypeError):
            continue

        matches = result.get('matches') or []
        if not matches:
            continue
        top = matches[0]
        shot_type = result.get('shot_type') or top.get('shot_type')
        pro_id = top.get('pro_id')
        pro_trajectory = pro_trajectories.get(pro_id)
        if not shot_type or pro_trajectory is None:
            continue

        user_clip_path = _user_clip_path(result.get('user_clip_url'))
        if not user_clip_path or not os.path.exists(user_clip_path):
            continue  # clip no longer on disk -- can't re-derive a trajectory, skip rather than error

        try:
            frames, fps = extract_user_poses(user_clip_path)
            user_trajectory, _peak_frame = build_user_trajectory(frames, fps, result.get('contact_time_sec'))
            if not user_trajectory:
                continue
            candidate_issues = score_issues(user_trajectory, pro_trajectory, shot_type)
        except Exception as e:
            print(f'  analysis {analysis_id}: FAILED -- {e}', file=sys.stderr)
            continue

        shown_tips = top.get('tips') or []
        shown_tip_ids = [t.get('id') for t in shown_tips if t.get('id')]

        pro_clip_url = None
        if top.get('clip_path'):
            pro_clip_url = to_url('/pro-clips', PRO_CLIPS_DIR, os.path.join(PRO_CLIPS_DIR, top['clip_path']))

        candidates.append({
            'analysis_id': analysis_id,
            'shot_type': shot_type,
            'user_clip_url': result.get('user_clip_url'),
            'pro_clip_url': pro_clip_url,
            'pro_player_name': player_names.get(pro_id),
            'shown_tip_ids': shown_tip_ids,
            'shown_tips': [{'id': t.get('id'), 'tip_text': t.get('tip_text')} for t in shown_tips],
            'candidate_issues': candidate_issues,
        })

    print(json.dumps({'candidates': candidates}))


if __name__ == '__main__':
    main()
