"""
Lists pro-database entries for the Dev Page's Pro Clip Review tool -- a
manual data-quality pass (mismatched footage / slow-motion / clips
spanning two different swings or players, plus contact-time/shot-type
label accuracy since Sprint 0 of the 2026-08-27 ML reliability plan), not a
teacher-student ML loop. Same free, no-Claude-cost, one-at-a-time pattern
already established for Swing Review / Rally Boundary Review / Tip Review.

Usage:
  python list_pro_clip_review_candidates.py [limit] [--practice]

  --practice: review ONLY the court-level practice-footage ingest
  (entry['ingest'] == 'practice_mvp'). Its shot-type labels came out badly
  skewed to 'forehand' and its contact frames land ~13f late, so it needs a
  relabel-and-recontact pass, not just an eyeball -- a separate review stream
  from the curated broadcast clips (which the default queue shows and this
  flag hides).

Output (stdout): {"candidates": [{id, shot_type, clip_url, camera_angle,
  confidence, clip_contact_time_sec, fps}, ...], "progress": {live_total,
  boundary_reviewed, label_reviewed, practice_total, practice_reviewed}}
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))

from paths import DATA_DIR  # noqa: E402
from clip_urls import to_url, PRO_CLIPS_DIR  # noqa: E402
from clip_review_log import (  # noqa: E402
    get_reviewed_set, get_label_reviewed_ids, latest_verdict_notes,
)
from source_footage_lookup import source_video_for, SOURCE_VIDEOS_DIR  # noqa: E402
from clip_trim import get_fps  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
AUDIT_PATH = os.path.join(DATA_DIR, '07_audits', 'ball_visibility_audit.json')

DEFAULT_LIMIT = 20


def _is_machine_contact_fill(verdict, note):
    """True when the only thing logged for an entry is a machine audio contact
    fill (predict_pro_clip_contact_from_audio.py -> rebuild). Its note ends
    '(audio)'; a real human contact correction's note is a plain 'a -> b'."""
    return verdict == 'contact_time_corrected' and bool(note) and note.rstrip().endswith('(audio)')


def _still_needs_review(eid, verdict_notes):
    """An entry is still a review candidate if it has no verdict at all, or its
    latest verdict is a machine audio contact fill (Jack hasn't eyeballed it)."""
    if eid not in verdict_notes:
        return True
    verdict, note = verdict_notes[eid]
    return _is_machine_contact_fill(verdict, note)


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
    verdict_notes = latest_verdict_notes()
    machine_fill = {eid for eid, (v, n) in verdict_notes.items() if _is_machine_contact_fill(v, n)}
    practice_ids = {e['id'] for e in db['entries'] if e.get('ingest') == 'practice_mvp'}
    return {
        'live_total': len(live_ids),
        'boundary_reviewed': len(live_ids & reviewed - machine_fill),
        'label_reviewed': len(live_ids & label_reviewed - machine_fill),
        'contact_fill_pending': len(live_ids & machine_fill),
        'practice_total': len(practice_ids),
        # a practice entry counts as done once it has any real (non-machine-fill) verdict
        'practice_reviewed': len(practice_ids & (reviewed | label_reviewed) - machine_fill),
    }


def main():
    argv = [a for a in sys.argv[1:] if a != '--practice']
    practice_only = '--practice' in sys.argv[1:]
    limit = int(argv[0]) if argv else DEFAULT_LIMIT

    verdict_notes = latest_verdict_notes()
    with open(PRO_DB_PATH) as f:
        db = json.load(f)

    candidates = []
    for entry in db['entries']:
        if len(candidates) >= limit:
            break
        if (entry.get('ingest') == 'practice_mvp') != practice_only:
            continue  # --practice shows only practice entries; default hides them
        if not _still_needs_review(entry['id'], verdict_notes):
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
        # practice-footage entries store their own source path; the curated
        # ones resolve it from the shot_type + swing_id // 1000 job bucket.
        if entry.get('source_video'):
            source_abs_path = os.path.join(SOURCE_VIDEOS_DIR, entry['source_video'])
        else:
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
