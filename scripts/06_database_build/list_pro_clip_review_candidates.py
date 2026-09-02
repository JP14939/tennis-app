"""
Lists pro-database entries for the Dev Page's Pro Clip Review tool -- a
manual data-quality pass (mismatched footage / slow-motion / clips
spanning two different swings or players, plus contact-time/shot-type
label accuracy since Sprint 0 of the 2026-08-27 ML reliability plan), not a
teacher-student ML loop. Same free, no-Claude-cost, one-at-a-time pattern
already established for Swing Review / Rally Boundary Review / Tip Review.

Usage:
  python list_pro_clip_review_candidates.py [limit]

Output (stdout): {"candidates": [{id, shot_type, clip_url, camera_angle,
  confidence, clip_contact_time_sec, fps}, ...], "progress": {live_total,
  boundary_reviewed, label_reviewed}}
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))

from paths import DATA_DIR  # noqa: E402
from clip_urls import to_url, PRO_CLIPS_DIR  # noqa: E402
from clip_review_log import get_reviewed_set, get_label_reviewed_ids  # noqa: E402
from source_footage_lookup import source_video_for, SOURCE_VIDEOS_DIR  # noqa: E402
from clip_trim import get_fps  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
AUDIT_PATH = os.path.join(DATA_DIR, '07_audits', 'ball_visibility_audit.json')

DEFAULT_LIMIT = 20


def _live_entry_ids():
    """Ids of entries that pass the ball-visibility filter compare_swing.py's
    candidate pool is meant to be scoped to -- 631 of pro_database.json's 914
    entries as of this audit file (filter_by_ball_visibility.py hasn't
    actually been run to drop the other 283 from disk yet). Returns None if
    the audit file is missing, so a missing side file doesn't hard-fail the
    candidate list -- callers should treat None as "count everything"."""
    if not os.path.exists(AUDIT_PATH):
        return None
    with open(AUDIT_PATH) as f:
        audit = json.load(f)
    return {r['id'] for r in audit if r['ball_visible']}


def _progress(db):
    all_ids = {e['id'] for e in db['entries']}
    live_ids = _live_entry_ids()
    live_ids = live_ids & all_ids if live_ids is not None else all_ids
    reviewed = get_reviewed_set()
    label_reviewed = get_label_reviewed_ids()
    return {
        'live_total': len(live_ids),
        'boundary_reviewed': len(live_ids & reviewed),
        'label_reviewed': len(live_ids & label_reviewed),
    }


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LIMIT

    reviewed = get_reviewed_set()
    with open(PRO_DB_PATH) as f:
        db = json.load(f)

    candidates = []
    for entry in db['entries']:
        if len(candidates) >= limit:
            break
        if entry['id'] in reviewed:
            continue
        clip_abs_path = os.path.join(PRO_CLIPS_DIR, entry['clip_path'])
        if not os.path.exists(clip_abs_path):
            continue  # clip missing on disk -- nothing to review

        # "View in source footage" (Sprint 0): lets Jack jump straight to
        # this shot's exact moment in the full, uncut compilation video for
        # broader context, instead of just the isolated ~3s cut clip -- only
        # attached when the source file actually exists on disk, so a moved
        # or never-transferred source video degrades to no button rather
        # than a dead link.
        source_abs_path = source_video_for(entry['shot_type'], entry['swing_id'])
        source_video_url = None
        if source_abs_path and os.path.exists(source_abs_path):
            source_video_url = to_url('/source-footage', SOURCE_VIDEOS_DIR, source_abs_path)

        candidates.append({
            'id': entry['id'],
            'shot_type': entry['shot_type'],
            'clip_url': to_url('/pro-clips', PRO_CLIPS_DIR, clip_abs_path),
            'camera_angle': entry.get('camera_angle'),
            'confidence': entry.get('confidence'),
            'clip_contact_time_sec': entry.get('clip_contact_time_sec'),
            'source_video_url': source_video_url,
            'source_peak_time_sec': entry.get('peak_time'),
            # Lets the frontend show/step by frame number in the "Fix contact
            # time" UI instead of only raw seconds -- neither web <video> nor
            # expo-av expose a clip's fps client-side, so it has to come from
            # here.
            'fps': get_fps(clip_abs_path),
        })

    print(json.dumps({'candidates': candidates, 'progress': _progress(db)}))


if __name__ == '__main__':
    main()
