"""
Phase 0a re-slice: regenerate EVERY pro_database.json entry's `trajectory` +
skeleton `overlay` from the (now stride-1) on-disk pose data, around each
entry's CURRENT clip_contact_time_sec.

Run this AFTER 02_pose_extraction/reextract_pro_poses.py has rebuilt the pose
files at sample_every=1. Passes yaw_enabled=True so the denser trajectories
bake in the pro-side viewpoint (yaw) correction in the same pass -- safe to run
before the re-extract too (build_world_pose_index returns {} for stride-3 pose
files lacking world_landmarks -> identity, byte-identical to yaw off).

Pure pose-slice math -- NO video decode, NO MediaPipe, NO ffmpeg. Uses the same
shared rebuild_helpers.reextract_for_entry() that correct_contact_time.py /
rebuild_pro_database_from_verdicts.py / reanchor_pro_serves.py use, so it only
rewrites `trajectory` / `peak_time` / overlay and never touches camera_angle,
racket_body_*, view_direction, ingest, or the practice-review holdout metadata.
The prior serve apex re-anchor is preserved too (it lives in
clip_contact_time_sec, which is what we re-slice around).

Entries whose pose/swings data can't be located (missing_lookup: split entries,
unresolved relabels) or whose window is too sparse (too_few_points) are left
exactly as they are and counted.

Drop verdicts are NOT applied here -- that's rebuild_pro_database_from_verdicts
.py's job. This script is density-only; it re-slices whatever entries are
currently in the DB.

Usage:
  python reslice_all_trajectories.py --dry-run   # report, write nothing
  python reslice_all_trajectories.py
  python reslice_all_trajectories.py --limit 20  # first N entries (smoke test)
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
from rebuild_helpers import build_swing_lookup, reextract_for_entry  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
OVERLAY_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'overlay_trajectories.json')


def _mean_points(entries):
    n = sum(len(e.get('trajectory') or []) for e in entries)
    return n / len(entries) if entries else 0.0


def reslice(dry_run=False, limit=None):
    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    try:
        with open(OVERLAY_DB_PATH) as f:
            overlays = json.load(f)
        overlays_usable = True
    except (FileNotFoundError, json.JSONDecodeError):
        overlays, overlays_usable = {}, False
        print('  note: overlay_trajectories.json missing/corrupt -- overlays NOT rewritten '
              '(delete it and run build_pro_overlay_trajectories.py after, or restore it first)')

    entries = db['entries'][:limit] if limit else db['entries']
    lookup = build_swing_lookup()
    print(f'{len(entries)} entries. mean trajectory points before: {_mean_points(entries):.1f}\n')

    ok, missing, sparse = [], [], []
    t0 = time.time()
    for i, entry in enumerate(entries, 1):
        eid = entry['id']
        orig_st = clip_review_log.original_shot_type_for(eid)
        res = reextract_for_entry(entry, lookup=lookup, original_shot_type=orig_st,
                                  yaw_enabled=True)
        if res['status'] == 'ok':
            entry['trajectory'] = res['trajectory']
            entry['peak_time'] = res['new_peak_time']
            # stride-1 trajectory. traj_version 4 = z is metric world-derived on
            # every joint (redesign_similarity._entry_metric_z gates the depth
            # axes on >=4); 3 = dense but no world landmarks (image-z), excluded.
            # traj_yaw_deg = x/y rotation (float when the hard >=deadband
            # estimate fired, else None); traj_z_yaw_deg = rotation baked into
            # the z channel (hard yaw, soft sub-deadband yaw, or None=unrotated
            # but still metric). Only the 'ok' branch: missing_lookup /
            # too_few_points entries keep their old trajectory and stay unstamped.
            entry['traj_version'] = 4 if res.get('z_metric') else 3
            entry['traj_yaw_deg'] = res.get('traj_yaw_deg')
            entry['traj_z_yaw_deg'] = res.get('traj_z_yaw_deg')
            if overlays_usable:
                overlays[eid] = res['overlay']
            ok.append(eid)
        elif res['status'] == 'missing_lookup':
            missing.append(eid)
        else:
            sparse.append(eid)
        if i % 100 == 0:
            print(f'  {i}/{len(entries)}  ({time.time() - t0:.0f}s)')

    print('\n' + '=' * 50)
    print(f'  re-sliced ok          : {len(ok)}')
    print(f'  missing_lookup (as-is): {len(missing)}  {missing[:20]}{" ..." if len(missing) > 20 else ""}')
    print(f'  too_few_points (as-is): {len(sparse)}  {sparse[:20]}{" ..." if len(sparse) > 20 else ""}')
    print(f'  mean trajectory points after: {_mean_points(entries):.1f}')
    if overlays_usable:
        kept_ids = {e['id'] for e in db['entries']}
        overlays = {k: v for k, v in overlays.items() if k in kept_ids}
        print(f'  overlays: {len(overlays)} entries')

    if dry_run:
        print('\n  --dry-run: nothing written.')
        return
    if limit:
        print('\n  --limit set: refusing to write a partial DB. Drop --limit for the real run.')
        return

    ts = time.strftime('%Y%m%d_%H%M%S')
    db_backup = os.path.join(os.path.dirname(PRO_DB_PATH),
                             f'pro_database_backup_pre_stride1_reslice_{ts}.json')
    with open(PRO_DB_PATH) as f, open(db_backup, 'w') as bf:
        bf.write(f.read())
    db['traj_version'] = 4  # top-level marker; per-entry traj_version is what scoring reads
    with open(PRO_DB_PATH, 'w') as f:
        json.dump(db, f)
    print(f'\n  backup: {db_backup}')
    print(f'  wrote:  {PRO_DB_PATH}')

    if overlays_usable:
        ov_backup = os.path.join(os.path.dirname(OVERLAY_DB_PATH),
                                 f'overlay_trajectories_backup_pre_stride1_reslice_{ts}.json')
        with open(OVERLAY_DB_PATH) as f, open(ov_backup, 'w') as bf:
            bf.write(f.read())
        with open(OVERLAY_DB_PATH, 'w') as f:
            json.dump(overlays, f)
        print(f'  backup: {ov_backup}')
        print(f'  wrote:  {OVERLAY_DB_PATH}')

    print('\nNext: reanchor_pro_serves.py, then '
          'scripts/17_amateur_eval/evaluate_amateur_dataset.py (regression gate).')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='compute + report, write nothing')
    ap.add_argument('--limit', type=int, default=None,
                    help='only process the first N entries (smoke test; never writes)')
    args = ap.parse_args()
    reslice(dry_run=args.dry_run, limit=args.limit)


if __name__ == '__main__':
    main()
