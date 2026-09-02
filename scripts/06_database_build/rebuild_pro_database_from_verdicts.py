"""
Apply the accumulated Pro Clip Review verdicts to pro_database.json (+ the
skeleton overlay file) in one pass. This is the "filter-and-rebuild" step
clip_review_log.py's docstring always referred to but that never existed.

What it does, reading data/06_pro_database/clip_review_log.jsonl (latest
verdict per entry):

  contact_time_corrected  -> re-extract entry['trajectory'] + its overlay
                             around the corrected clip_contact_time_sec, from
                             on-disk pose data. The scalar was already applied
                             live by correct_contact_time.py; before this
                             script (and before correct_contact_time.py was
                             taught to do it inline) the trajectory was left
                             anchored to the original automated peak_frame, so
                             the DTW comparison used stale pose motion.
  excluded / mismatched / slow_motion / wrong_boundary
                          -> drop the entry entirely (still served to users
                             today -- compare_swing.py does no filtering).

NO video decode, NO MediaPipe, NO ffmpeg -- pure JSON + pose-slice math, runs
in seconds. Idempotent: re-running re-derives the same trajectories and the
dropped ids simply never re-match.

  --contact-predictions <json>
                          -> for every KEPT entry with no hand-marked
                             contact_time_corrected verdict, apply the audio
                             onset detector's CONFIDENT clip_contact_time_sec
                             (from predict_pro_clip_contact_from_audio.py),
                             re-anchor its trajectory + overlay, and log a
                             contact_time_corrected verdict so re-runs are
                             idempotent. Non-confident entries are listed for
                             a targeted human contact-mark pass.

Usage:
  python rebuild_pro_database_from_verdicts.py [--dry-run] [--drop-ball-invisible]
      [--contact-predictions data/06_pro_database/pro_clip_contact_predictions.json]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
import clip_review_log  # noqa: E402
from paths import DATA_DIR  # noqa: E402
from rebuild_helpers import build_swing_lookup, reextract_for_entry  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
OVERLAY_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'overlay_trajectories.json')
BALL_AUDIT_PATH = os.path.join(DATA_DIR, '07_audits', 'ball_visibility_audit.json')

DROP_VERDICTS = {'excluded', 'mismatched', 'slow_motion', 'wrong_boundary'}
REEXTRACT_VERDICTS = {'contact_time_corrected'}


def _recount_shots(entries):
    shots = {'forehand': 0, 'backhand': 0, 'serve': 0}
    for e in entries:
        if e['shot_type'] in shots:
            shots[e['shot_type']] += 1
    return shots


def _load_overlays():
    """Returns (overlays_dict, usable_bool). usable=False when the file is
    missing OR corrupt -- in that case we leave it completely alone and tell
    the operator to regenerate it, rather than clobbering a partially-valid
    file with a fresh 137-entry one."""
    if not os.path.exists(OVERLAY_DB_PATH):
        print(f'  note: {OVERLAY_DB_PATH} not found -- run build_pro_overlay_trajectories.py after this.')
        return {}, False
    try:
        with open(OVERLAY_DB_PATH) as f:
            return json.load(f), True
    except json.JSONDecodeError:
        print(f'  WARNING: {OVERLAY_DB_PATH} is corrupt/truncated -- leaving it untouched. '
              f'Delete it and re-run build_pro_overlay_trajectories.py after this.')
        return {}, False


def _ball_invisible_ids():
    if not os.path.exists(BALL_AUDIT_PATH):
        print(f'  --drop-ball-invisible: no audit at {BALL_AUDIT_PATH}, skipping that filter')
        return set()
    with open(BALL_AUDIT_PATH) as f:
        audit = json.load(f)
    rows = audit if isinstance(audit, list) else audit.get('results', audit.get('entries', []))
    return {r['id'] for r in rows if not r.get('ball_visible', True)}


def _load_contact_predictions(path):
    if not path:
        return {}
    with open(path) as f:
        preds = json.load(f)
    return {eid: p for eid, p in preds.items()
            if p.get('status') == 'ok' and p.get('confident') and p.get('contact_time_sec') is not None}


def rebuild(dry_run=False, drop_ball_invisible=False, contact_predictions_path=None):
    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    overlays, overlays_usable = _load_overlays()

    verdicts = clip_review_log.get_latest_verdicts()
    ball_invisible = _ball_invisible_ids() if drop_ball_invisible else set()
    confident_preds = _load_contact_predictions(contact_predictions_path)

    all_preds = {}
    if contact_predictions_path:
        with open(contact_predictions_path) as f:
            all_preds = json.load(f)

    lookup = build_swing_lookup()

    kept, dropped, reextracted, skipped, audio_filled, audio_flagged = [], [], [], [], [], []
    orig_total = db['total']
    orig_shots = dict(db.get('shots', {}))

    for entry in db['entries']:
        eid = entry['id']
        v = verdicts.get(eid)

        if v in DROP_VERDICTS:
            dropped.append((eid, v))
            overlays.pop(eid, None)
            continue
        if drop_ball_invisible and eid in ball_invisible:
            dropped.append((eid, 'ball_invisible'))
            overlays.pop(eid, None)
            continue

        orig_st = clip_review_log.original_shot_type_for(eid)

        if v in REEXTRACT_VERDICTS:
            res = reextract_for_entry(entry, lookup=lookup, original_shot_type=orig_st)
            if res['status'] == 'ok':
                entry['trajectory'] = res['trajectory']
                entry['peak_time'] = res['new_peak_time']
                overlays[eid] = res['overlay']
                reextracted.append(eid)
            else:
                skipped.append((eid, res['status']))
        elif eid in confident_preds:
            # Audio onset detector's confident contact time -- set the scalar,
            # re-anchor exactly as a hand correction would, and log a verdict
            # so a re-run treats it as a normal contact_time_corrected entry.
            old = entry.get('clip_contact_time_sec')
            new = round(confident_preds[eid]['contact_time_sec'], 4)
            entry['clip_contact_time_sec'] = new
            res = reextract_for_entry(entry, lookup=lookup, original_shot_type=orig_st)
            if res['status'] == 'ok':
                entry['trajectory'] = res['trajectory']
                entry['peak_time'] = res['new_peak_time']
                overlays[eid] = res['overlay']
                audio_filled.append(eid)
                if not dry_run:
                    clip_review_log.log_verdict(
                        eid, 'contact_time_corrected', note=f'{old} -> {new} (audio)')
            else:
                entry['clip_contact_time_sec'] = old  # revert -- couldn't propagate
                skipped.append((eid, f'audio_{res["status"]}'))
        elif eid in all_preds and all_preds[eid].get('status') == 'ok':
            audio_flagged.append(eid)

        kept.append(entry)

    db['entries'] = kept
    db['total'] = len(kept)
    db['shots'] = _recount_shots(kept)

    kept_ids = {e['id'] for e in kept}
    if overlays_usable:
        overlays = {k: t for k, t in overlays.items() if k in kept_ids}

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    if contact_predictions_path:
        print(f'  audio contact fill (confident)    : {len(audio_filled)} applied')
        print(f'  audio contact flagged (uncertain) : {len(audio_flagged)} -- need a human contact-mark pass')
    print(f'  re-extracted trajectory + overlay : {len(reextracted)}')
    missing = [s for s in skipped if s[1] == 'missing_lookup']
    sparse = [s for s in skipped if s[1] == 'too_few_points']
    if skipped:
        print(f'  skipped (left untouched)          : {len(skipped)}  '
              f'({len(missing)} missing_lookup, {len(sparse)} too_few_points)')
        for eid, why in skipped:
            print(f'      {eid:<22} {why}')
    print(f'  dropped                           : {len(dropped)}')
    by_reason = {}
    for _, why in dropped:
        by_reason[why] = by_reason.get(why, 0) + 1
    for why, n in sorted(by_reason.items()):
        print(f'      {why:<18} {n}')
    print(f'  total   : {orig_total} -> {db["total"]}')
    print(f'  shots   : {orig_shots} -> {db["shots"]}')
    if overlays_usable:
        print(f'  overlays: {len(overlays)} entries')
    else:
        print('  overlays: NOT written (missing/corrupt) -- regenerate with '
              'build_pro_overlay_trajectories.py')

    if dry_run:
        print('\n  --dry-run: nothing written.')
        return

    ts = time.strftime('%Y%m%d_%H%M%S')
    db_backup = os.path.join(os.path.dirname(PRO_DB_PATH),
                             f'pro_database_backup_pre_verdict_rebuild_{ts}.json')
    with open(PRO_DB_PATH) as f, open(db_backup, 'w') as bf:
        bf.write(f.read())
    print(f'\n  backup: {db_backup}')

    with open(PRO_DB_PATH, 'w') as f:
        json.dump(db, f)
    print(f'  wrote:  {PRO_DB_PATH}')

    if overlays_usable:
        ov_backup = os.path.join(os.path.dirname(OVERLAY_DB_PATH),
                                 f'overlay_trajectories_backup_pre_verdict_rebuild_{ts}.json')
        with open(OVERLAY_DB_PATH) as f, open(ov_backup, 'w') as bf:
            bf.write(f.read())
        with open(OVERLAY_DB_PATH, 'w') as f:
            json.dump(overlays, f)
        print(f'  backup: {ov_backup}')
        print(f'  wrote:  {OVERLAY_DB_PATH}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='compute + report, write nothing')
    ap.add_argument('--drop-ball-invisible', action='store_true',
                    help='also drop entries flagged not ball_visible in the 07_audits audit')
    ap.add_argument('--contact-predictions', default=None,
                    help='pro_clip_contact_predictions.json -- apply confident audio contact times')
    args = ap.parse_args()
    rebuild(dry_run=args.dry_run, drop_ball_invisible=args.drop_ball_invisible,
            contact_predictions_path=args.contact_predictions)


if __name__ == '__main__':
    main()
