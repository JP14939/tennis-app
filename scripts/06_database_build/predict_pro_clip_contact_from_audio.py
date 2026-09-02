"""
Phase B.2 -- predict every kept pro-DB entry's clip contact time from the
source-compilation audio.

Every pro_database.json entry's `clip_contact_time_sec` is a placeholder
(1.0 / 1.001 / 1.8 / 1.802) -- each clip was cut at `swing-detector-peak - 1.0s`,
so contact sits at 1.0s *by construction*, and that peak is ~20 frames off the
real ball-strike. So every un-hand-reviewed pro trajectory is mis-anchored for
the DTW match.

This runs the audio onset detector (the live fusion model,
onset_classifier.pkl) over the source video's audio window for every entry
that:
  - is KEPT (latest review verdict not in DROP_VERDICTS), and
  - was NOT hand-marked by Jack (latest verdict != contact_time_corrected --
    those ~196 keep their human value).

Writes one prediction per entry to
data/06_pro_database/pro_clip_contact_predictions.json:
  {entry_id: {contact_time_sec, confidence, margin, confident, n_onsets,
              status}}

rebuild_pro_database_from_verdicts.py --contact-predictions <that file> then
applies the confident ones (sets the scalar, re-anchors trajectory + overlay,
logs a contact_time_corrected verdict). Non-confident entries are listed for a
short targeted human contact-mark pass in the Dev tool.

Read-only w.r.t. pro_database.json. Resumable (skips ids already predicted;
--force re-does them). ~0.3s/entry.

Usage:
  python predict_pro_clip_contact_from_audio.py [--limit N]
      [--shot-type forehand|backhand|serve] [--force]
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
for p in (HERE,
          os.path.join(SCRIPTS_DIR, '00_utils'),
          os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking')):
    if p not in sys.path:
        sys.path.insert(0, p)

import clip_review_log  # noqa: E402
from paths import DATA_DIR  # noqa: E402
from source_footage_lookup import source_video_for  # noqa: E402
from rebuild_helpers import build_swing_lookup  # noqa: E402
from rebuild_pro_database_from_verdicts import DROP_VERDICTS  # noqa: E402
from audio_onset import extract_audio_wav  # noqa: E402
import audio_contact  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
PRED_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_clip_contact_predictions.json')
AUDIO_CACHE = os.path.join(DATA_DIR, '06_pro_database', '.audio_cache')
POSE_EVAL_CSV = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'eval_pro_clip_contact.csv')

# The clip window in the source video: clips are cut at peak - PRE and run a
# few seconds; contact sits near 1.0s. A 3.6s window comfortably contains it
# plus enough tail for the onset's decay features.
CLIP_WINDOW_SEC = 3.6
# The audio pick must land somewhere sane inside the clip window to be
# applied -- the confident gate + anchor band should already guarantee this,
# this is just a last backstop against a degenerate onset.
MIN_CONTACT_SEC, MAX_CONTACT_SEC = 0.3, 2.6


def _pose_hints():
    """entry_id -> {wrist_peak_sec, pose_pred_sec} from the pose-baseline eval
    CSV, for the ~197 entries it covers. Better fusion features than the
    by-construction 1.0s prior for those; everything else falls back to 1.0s."""
    hints = {}
    if not os.path.exists(POSE_EVAL_CSV):
        return hints
    with open(POSE_EVAL_CSV) as f:
        for row in csv.DictReader(f):
            try:
                fps = float(row['fps'])
                hints[row['id']] = {
                    'wrist_peak_sec': float(row['anchor_frame']) / fps,
                    'pose_pred_sec': float(row['pred_time_heuristic']),
                }
            except (KeyError, ValueError, ZeroDivisionError):
                continue
    return hints


def predict_one(entry, lookup, hints, orig_shot_type):
    st = orig_shot_type or entry['shot_type']
    swing_id = entry['swing_id']

    found = lookup.get((st, swing_id))
    if not found:
        return {'status': 'missing_lookup'}
    src = source_video_for(st, swing_id)
    if not src or not os.path.exists(src):
        return {'status': 'no_source_video'}

    start_sec = found['start_frame'] / found['fps']
    os.makedirs(AUDIO_CACHE, exist_ok=True)
    wav = os.path.join(AUDIO_CACHE, f'{st}_{swing_id:04d}.wav')
    if not extract_audio_wav(src, wav, start_sec=start_sec, dur_sec=CLIP_WINDOW_SEC):
        return {'status': 'audio_extract_failed'}

    h = hints.get(entry['id'], {'wrist_peak_sec': 1.0, 'pose_pred_sec': 1.0})
    ac = audio_contact.detect_contact(
        'x', audio_path=wav,
        anchor_time_sec=h['wrist_peak_sec'], search_window_sec=0.6,
        video_hints=h,
    )
    if not ac:
        return {'status': 'no_onsets'}

    t = round(ac['contact_time_sec'], 4)
    in_range = MIN_CONTACT_SEC <= t <= MAX_CONTACT_SEC
    return {
        'status': 'ok',
        'contact_time_sec': t,
        'confidence': round(ac['confidence'], 4),
        'margin': round(ac['margin'], 4),
        'n_onsets': ac['n_onsets'],
        'confident': bool(ac['confident'] and in_range),
    }


def _hand_marks():
    """entry_id -> clip-relative hand-marked contact sec, from the
    contact_time_corrected verdicts (the 'new' side of the note)."""
    marks, latest = {}, {}
    with open(clip_review_log.LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            latest[r['entry_id']] = r['verdict']
            if r['verdict'] == 'contact_time_corrected' and r.get('note') and '->' in r['note']:
                try:
                    marks[r['entry_id']] = float(r['note'].split('->')[1].strip().rstrip('s'))
                except ValueError:
                    pass
    return {k: v for k, v in marks.items() if latest.get(k) == 'contact_time_corrected'}


def validate(argv_limit=None):
    """Run the same predictor over the hand-marked clips and report error vs
    the human mark -- the honest accuracy check before touching the live DB."""
    with open(PRO_DB_PATH) as f:
        db = {e['id']: e for e in json.load(f)['entries']}
    lookup = build_swing_lookup()
    hints = _pose_hints()
    marks = _hand_marks()
    ids = [i for i in marks if i in db]
    if argv_limit:
        ids = ids[:argv_limit]
    print(f'validating on {len(ids)} hand-marked clips', file=sys.stderr)

    errs, conf_errs, n_conf = [], [], 0
    for i, eid in enumerate(ids, 1):
        try:
            res = predict_one(db[eid], lookup, hints,
                              clip_review_log.original_shot_type_for(eid))
        except Exception:  # noqa: BLE001
            continue
        if res['status'] != 'ok':
            continue
        err = abs(res['contact_time_sec'] - marks[eid])
        errs.append(err)
        if res['confident']:
            n_conf += 1
            conf_errs.append(err)
        if i % 25 == 0:
            print(f'  [{i}/{len(ids)}]', file=sys.stderr)

    def _rep(name, e):
        if not e:
            print(f'  {name}: no picks')
            return
        e = sorted(e)
        within = lambda k: sum(x <= k for x in e) / len(e)  # noqa: E731
        print(f'  {name}: n={len(e)}  median={e[len(e) // 2] * 1000:.0f}ms  '
              f'<=50ms={within(0.05):.0%}  <=100ms={within(0.10):.0%}  <=150ms={within(0.15):.0%}')

    print('\n=== validation vs hand marks ===')
    _rep('all onset picks ', errs)
    _rep('confident picks ', conf_errs)
    print(f'  confident rate: {n_conf}/{len(errs)} of picks')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--shot-type', choices=['forehand', 'backhand', 'serve'])
    ap.add_argument('--force', action='store_true', help='re-predict ids already in the output file')
    ap.add_argument('--validate', action='store_true',
                    help='run on the hand-marked clips and report error vs the human mark; writes nothing')
    args = ap.parse_args(argv)

    if args.validate:
        validate(args.limit)
        return

    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    verdicts = clip_review_log.get_latest_verdicts()
    lookup = build_swing_lookup()
    hints = _pose_hints()

    preds = {}
    if os.path.exists(PRED_PATH) and not args.force:
        with open(PRED_PATH) as f:
            preds = json.load(f)

    targets = []
    for e in db['entries']:
        v = verdicts.get(e['id'])
        if v in DROP_VERDICTS or v == 'contact_time_corrected':
            continue
        if args.shot_type and e['shot_type'] != args.shot_type:
            continue
        if e['id'] in preds and not args.force:
            continue
        targets.append(e)
    if args.limit:
        targets = targets[:args.limit]

    print(f'{len(targets)} entries to predict '
          f'({len(preds)} already done, {len(db["entries"])} in DB)', file=sys.stderr)

    from collections import Counter
    tally = Counter()
    for i, e in enumerate(targets, 1):
        try:
            res = predict_one(e, lookup, hints,
                              clip_review_log.original_shot_type_for(e['id']))
        except Exception as ex:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            res = {'status': f'error:{type(ex).__name__}'}
        preds[e['id']] = res
        tally[res['status']] += 1
        if res.get('confident'):
            tally['_confident'] += 1
        if i % 25 == 0:
            print(f'  [{i}/{len(targets)}] {dict(tally)}', file=sys.stderr)
            with open(PRED_PATH, 'w') as f:
                json.dump(preds, f, indent=1)

    with open(PRED_PATH, 'w') as f:
        json.dump(preds, f, indent=1)

    ok = [p for p in preds.values() if p['status'] == 'ok']
    conf = [p for p in ok if p['confident']]
    print('\n=== done ===')
    for k, n in sorted(tally.items(), key=lambda t: -t[1]):
        print(f'  {k:<22} {n}')
    print(f'\n  predictions file: {PRED_PATH}')
    print(f'  {len(ok)} onset picks, {len(conf)} confident '
          f'({len(conf) / len(ok):.0%} of picks)' if ok else '  no picks')
    if conf:
        ts = sorted(p['contact_time_sec'] for p in conf)
        print(f'  confident contact_time_sec: median {ts[len(ts) // 2]:.3f}s  '
              f'range {ts[0]:.3f}-{ts[-1]:.3f}s')


if __name__ == '__main__':
    main()
