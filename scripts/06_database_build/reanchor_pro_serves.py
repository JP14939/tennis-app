"""
Re-anchor the SERVE entries in pro_database.json from the stored
wrist-velocity peak to the overhead apex (serve-anchor Phase 1b).

Phase 1a shipped serve_anchor.serve_contact_anchor_frame() on the LIVE path
(compare_swing.auto_contact_anchor_frame): a serve's contact is the frame the
hitting wrist reaches maximum height above the head, not the wrist-velocity
peak (which lands on the toss release / follow-through, ~median 38f off). See
HANDOVER.md "Session 2026-09-06 (later) -- serve contact anchor". This script
is the offline half: the pro side of a serve DTW comparison is still anchored
to the old wrist-velocity peak, so re-anchor it the same way.

Pure pose-slice math -- NO video decode, NO MediaPipe, NO ffmpeg. Modelled on
rebuild_pro_database_from_verdicts.py: for each serve entry it recomputes the
apex frame from on-disk pose data, sets clip_contact_time_sec, and calls
rebuild_helpers.reextract_for_entry to regenerate trajectory + overlay around
it (window / scale / t-values all shift). Idempotent: a re-run recomputes the
same apex, so unchanged entries report a 0-frame move and get no new verdict.

A real human contact mark always wins -- entries whose latest verdict is a
hand 'contact_time_corrected' (note NOT ending '(audio)' / '(serve apex
reanchor)') or 'label_confirmed' are left untouched. Audio-filled entries ARE
re-anchored (the apex beats the audio guess for serves). Drop verdicts
(excluded / mismatched / slow_motion / wrong_boundary) are skipped.

Usage:
  python reanchor_pro_serves.py --dry-run            # report old->new deltas, write nothing
  python reanchor_pro_serves.py [--limit N] [--only ID]
  python reanchor_pro_serves.py --min-move-frames 2  # only rewrite entries that move >= N frames

Gate before a real run (plan): --dry-run, then re-run
scripts/07_ball_racket_tracking/eval_pro_clip_contact.py and confirm serve
median |err| improves-or-holds and forehand/backhand rows are unchanged.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '00_utils'))

import clip_review_log  # noqa: E402
from paths import DATA_DIR  # noqa: E402
from rebuild_helpers import build_swing_lookup, reextract_for_entry, _load_pose_index  # noqa: E402
from serve_anchor import serve_contact_anchor_frame, APEX_SEARCH_RADIUS_SEC  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
OVERLAY_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'overlay_trajectories.json')

DROP_VERDICTS = {'excluded', 'mismatched', 'slow_motion', 'wrong_boundary'}
REANCHOR_NOTE_SUFFIX = '(serve apex reanchor)'


def _human_marked(verdict, note):
    """True when a real person set this entry's contact time / confirmed its
    labels -- those are never overridden."""
    if verdict == 'label_confirmed':
        return True
    if verdict == 'contact_time_corrected' and note:
        n = note.strip()
        return not (n.endswith('(audio)') or n.endswith(REANCHOR_NOTE_SUFFIX))
    return False


def _pose_context(entry, orig_st, lookup):
    """(fps, pose_index, clip_start_frame, center_frame) or None if the pose
    data for this serve entry can't be located."""
    # practice-footage entries carry their own source pose file + clip offset
    if entry.get('poses_path') and entry.get('clip_start_frame') is not None:
        poses_abs = entry['poses_path']
        if not os.path.isabs(poses_abs):
            poses_abs = os.path.join(DATA_DIR, entry['poses_path'])
        if not os.path.exists(poses_abs):
            return None
        fps, pose_index = _load_pose_index(poses_abs)
        clip_start = entry['clip_start_frame']
        center = clip_start + round((entry.get('clip_contact_time_sec') or 0.0) * fps)
        return fps, pose_index, clip_start, center

    found = lookup.get((orig_st, entry['swing_id']))
    if not found:
        return None
    fps, pose_index = _load_pose_index(found['poses_path'])
    return fps, pose_index, found['start_frame'], found['orig_peak_frame']


def reanchor(dry_run=False, limit=None, only=None, min_move_frames=0):
    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    try:
        with open(OVERLAY_DB_PATH) as f:
            overlays = json.load(f)
        overlays_usable = True
    except (FileNotFoundError, json.JSONDecodeError):
        overlays, overlays_usable = {}, False
        print('  note: overlay_trajectories.json missing/corrupt -- overlays NOT rewritten')

    notes = clip_review_log.latest_verdict_notes()
    lookup = build_swing_lookup()

    serves = [e for e in db['entries'] if e['shot_type'] == 'serve']
    if only:
        serves = [e for e in serves if e['id'] == only]
    if limit:
        serves = serves[:limit]
    print(f'{len(serves)} serve entries considered\n')

    moved, unchanged, skipped_human, skipped_nopose, apex_unmeasurable = [], [], [], [], []
    verdict_writes = []

    for entry in serves:
        eid = entry['id']
        verdict, note = notes.get(eid, (None, None))
        if verdict in DROP_VERDICTS:
            continue
        if _human_marked(verdict, note):
            skipped_human.append(eid)
            continue

        orig_st = clip_review_log.original_shot_type_for(eid) or 'serve'
        ctx = _pose_context(entry, orig_st, lookup)
        if ctx is None:
            skipped_nopose.append(eid)
            continue
        fps, pose_index, clip_start, center = ctx

        new_peak_frame = serve_contact_anchor_frame(
            pose_index, fps, center_frame=center, radius_sec=APEX_SEARCH_RADIUS_SEC)
        if new_peak_frame is None:
            apex_unmeasurable.append(eid)
            continue

        old = entry.get('clip_contact_time_sec')
        new = round(max(0.0, (new_peak_frame - clip_start) / fps), 4)
        move_f = abs(round((new - (old or 0.0)) * fps))

        if move_f < max(1, min_move_frames):
            unchanged.append((eid, move_f))
            continue

        entry['clip_contact_time_sec'] = new
        res = reextract_for_entry(entry, lookup=lookup, original_shot_type=orig_st)
        if res['status'] != 'ok':
            entry['clip_contact_time_sec'] = old  # revert -- couldn't propagate
            skipped_nopose.append(f'{eid} ({res["status"]})')
            continue
        entry['trajectory'] = res['trajectory']
        entry['peak_time'] = res['new_peak_time']
        if overlays_usable:
            overlays[eid] = res['overlay']
        moved.append((eid, old, new, move_f))
        verdict_writes.append((eid, f'{old} -> {new} {REANCHOR_NOTE_SUFFIX}'))

    # ── Summary ──────────────────────────────────────────────────────────
    print(f'  re-anchored (moved >= {max(1, min_move_frames)}f) : {len(moved)}')
    for eid, old, new, mv in sorted(moved, key=lambda r: -r[3])[:40]:
        print(f'      {eid:<22} {old} -> {new}   ({mv}f)')
    if len(moved) > 40:
        print(f'      ... and {len(moved) - 40} more')
    print(f'  within tolerance (left as-is)      : {len(unchanged)}')
    print(f'  skipped, human-marked             : {len(skipped_human)}')
    print(f'  skipped, pose data not found      : {len(skipped_nopose)}')
    for x in skipped_nopose:
        print(f'      {x}')
    print(f'  apex unmeasurable (left as-is)    : {len(apex_unmeasurable)}')

    if dry_run:
        print('\n  --dry-run: nothing written.')
        return

    if not moved:
        print('\n  no entries moved -- nothing to write.')
        return

    ts = time.strftime('%Y%m%d_%H%M%S')
    db_backup = os.path.join(os.path.dirname(PRO_DB_PATH),
                             f'pro_database_backup_pre_serve_reanchor_{ts}.json')
    with open(PRO_DB_PATH) as f, open(db_backup, 'w') as bf:
        bf.write(f.read())
    with open(PRO_DB_PATH, 'w') as f:
        json.dump(db, f)
    print(f'\n  backup: {db_backup}')
    print(f'  wrote:  {PRO_DB_PATH}')

    if overlays_usable:
        ov_backup = os.path.join(os.path.dirname(OVERLAY_DB_PATH),
                                 f'overlay_trajectories_backup_pre_serve_reanchor_{ts}.json')
        with open(OVERLAY_DB_PATH) as f, open(ov_backup, 'w') as bf:
            bf.write(f.read())
        with open(OVERLAY_DB_PATH, 'w') as f:
            json.dump(overlays, f)
        print(f'  backup: {ov_backup}')
        print(f'  wrote:  {OVERLAY_DB_PATH}')

    for eid, vnote in verdict_writes:
        clip_review_log.log_verdict(eid, 'contact_time_corrected', note=vnote)
    print(f'  logged {len(verdict_writes)} contact_time_corrected verdicts')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--only', default=None, help='a single entry id')
    ap.add_argument('--min-move-frames', type=int, default=1,
                    help='only rewrite entries whose apex moves the contact by >= this many frames')
    args = ap.parse_args()
    reanchor(dry_run=args.dry_run, limit=args.limit, only=args.only,
             min_move_frames=args.min_move_frames)


if __name__ == '__main__':
    main()
