"""
Prototype: can the ball-on-strings AUDIO transient pin the contact frame?

The pose+ball pipeline (eval_pro_clip_contact.py) lands ~9 frames off on the
197 hand-marked pro clips -- the wrist-velocity anchor is a swing detector, not
a contact detector, and pose has no sharp contact signal. The clean "pock" of
racket-ball impact is the sharpest event in the recording; this measures how
well a scipy-only spectral-flux onset detector recovers it.

Pro clips (data/04_clips) have NO audio stream -- but the source compilation
videos (data/01_source_videos) do. Each pro entry maps back to a source video
+ a clip window via source_footage_lookup + build_swing_lookup; the human
contact mark (teacher_time) is clip-relative, so it compares directly to an
onset time measured inside the same window.

Read-only. Writes data/07_ball_racket_tracking/eval_audio_contact.csv
(resumable) + prints a report. Report-only: --report-only.

Usage:
  python eval_audio_contact.py [--limit N] [--only ID[,ID...]] [--report-only]
                               [--highpass HZ] [--anchor-sec S]
"""
import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE,
          os.path.join(SCRIPTS_DIR, '00_utils'),
          os.path.join(SCRIPTS_DIR, '06_database_build')):
    if p not in sys.path:
        sys.path.insert(0, p)

from paths import DATA_DIR  # noqa: E402
import clip_review_log  # noqa: E402
from source_footage_lookup import source_video_for  # noqa: E402
from rebuild_helpers import build_swing_lookup  # noqa: E402
from audio_onset import (  # noqa: E402
    HIGHPASS_HZ_DEFAULT, REPORT_FPS, ONSET_BIAS_F, WINDOW_LO_SEC, WINDOW_HI_SEC,
    extract_audio_wav, onset_envelope, find_onsets,
)

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
REVIEW_LOG_PATH = clip_review_log.LOG_PATH
AUDIO_CACHE = os.path.join(DATA_DIR, '07_ball_racket_tracking', '.audio_cache')
OUT_CSV = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'eval_audio_contact.csv')

WINDOW_SEC = 3.2          # audio pulled per clip (clip span is ~3.0s)
ANCHOR_SEC_DEFAULT = 1.0  # where the wrist-velocity anchor sits in-clip (PRE_SWING_SEC)

CSV_FIELDS = [
    'id', 'shot_type', 'orig_shot_type', 'swing_id', 'source_video',
    'teacher_time', 'n_onsets',
    'strongest_time', 'strongest_err_f',
    'nearest_anchor_time', 'nearest_anchor_err_f',
    'windowed_strongest_time', 'windowed_strongest_err_f',
    'oracle_best_err_f', 'oracle_best_strength',
    'onsets_json',
    'error',
]


def teacher_labels():
    """{entry_id: teacher_time_sec} for entries whose LATEST verdict pinned the
    contact frame. Mirrors eval_pro_clip_contact.teacher_labels()."""
    latest, corrected = {}, {}
    with open(REVIEW_LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            latest[r['entry_id']] = r['verdict']
            if r['verdict'] == 'contact_time_corrected' and r.get('note') and '->' in r['note']:
                try:
                    corrected[r['entry_id']] = float(r['note'].split('->')[1].strip().rstrip('s'))
                except ValueError:
                    pass
    db = json.load(open(PRO_DB_PATH))
    by_id = {e['id']: e for e in db['entries']}
    out = {}
    for eid, verdict in latest.items():
        if eid not in by_id:
            continue
        if verdict == 'contact_time_corrected' and eid in corrected:
            out[eid] = corrected[eid]
        elif verdict == 'label_confirmed':
            t = by_id[eid].get('clip_contact_time_sec')
            if t is not None:
                out[eid] = float(t)
    return out, by_id


def _id_parts(entry_id):
    st, _, sid = entry_id.rpartition('_')
    return st, int(sid)


def eval_one(entry, teacher_time, highpass_hz, anchor_sec):
    st, sid = _id_parts(entry['id'])
    orig_st = clip_review_log.original_shot_type_for(entry['id']) or st
    src = source_video_for(orig_st, sid)
    if not src or not os.path.exists(src):
        return {'error': f'no_source:{orig_st}:{sid}'}

    lookup = _LOOKUP
    info = lookup.get((orig_st, sid))
    if not info:
        return {'error': f'no_swing_lookup:{orig_st}:{sid}'}
    start_sec = info['start_frame'] / info['fps']

    cache_path = os.path.join(AUDIO_CACHE, f'{orig_st}_{sid}_{highpass_hz:.0f}.wav')
    if not extract_audio_wav(src, cache_path, start_sec=start_sec, dur_sec=WINDOW_SEC):
        return {'error': 'ffmpeg_or_no_audio'}

    flux_t, flux = onset_envelope(cache_path, highpass_hz)
    onsets = find_onsets(flux_t, flux)

    row = {
        'orig_shot_type': orig_st, 'swing_id': sid,
        'source_video': os.path.basename(src),
        'n_onsets': len(onsets),
        'strongest_time': '', 'strongest_err_f': '',
        'nearest_anchor_time': '', 'nearest_anchor_err_f': '',
        'windowed_strongest_time': '', 'windowed_strongest_err_f': '',
        'oracle_best_err_f': '', 'oracle_best_strength': '',
        'onsets_json': json.dumps([[round(t, 4), round(s, 3)] for t, s in onsets[:12]]),
    }
    if not onsets:
        return row

    def err(t):
        return round((t - teacher_time) * REPORT_FPS, 2)

    strongest = onsets[0]
    row['strongest_time'] = round(strongest[0], 4)
    row['strongest_err_f'] = err(strongest[0])

    nearest = min(onsets, key=lambda o: abs(o[0] - anchor_sec))
    row['nearest_anchor_time'] = round(nearest[0], 4)
    row['nearest_anchor_err_f'] = err(nearest[0])

    banded = [o for o in onsets if WINDOW_LO_SEC <= o[0] <= WINDOW_HI_SEC]
    if banded:
        ws = max(banded, key=lambda o: o[1])   # strongest within the band
        row['windowed_strongest_time'] = round(ws[0], 4)
        row['windowed_strongest_err_f'] = err(ws[0])

    oracle = min(onsets, key=lambda o: abs(o[0] - teacher_time))
    row['oracle_best_err_f'] = err(oracle[0])
    row['oracle_best_strength'] = round(oracle[1], 3)
    return row


_LOOKUP = None


def run(limit=None, only=None, highpass_hz=HIGHPASS_HZ_DEFAULT, anchor_sec=ANCHOR_SEC_DEFAULT):
    global _LOOKUP
    _LOOKUP = build_swing_lookup()
    labels, by_id = teacher_labels()
    if only:
        labels = {k: v for k, v in labels.items() if k in only}

    done = {}
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV, newline='') as f:
            done = {r['id']: r for r in csv.DictReader(f)}
    todo = sorted(eid for eid in labels if eid not in done)
    if limit:
        todo = todo[:limit]
    print(f'{len(labels)} labelled | {len(done)} done | {len(todo)} to run', file=sys.stderr)

    new_file = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        for i, eid in enumerate(todo, 1):
            entry = by_id[eid]
            print(f'[{i}/{len(todo)}] {eid}', file=sys.stderr)
            row = {k: '' for k in CSV_FIELDS}
            row.update({'id': eid, 'shot_type': entry['shot_type'],
                        'teacher_time': round(labels[eid], 4)})
            try:
                res = eval_one(entry, labels[eid], highpass_hz, anchor_sec)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                res = {'error': f'exception:{type(e).__name__}:{e}'}
            row.update(res)
            w.writerow(row)
            f.flush()
    report()


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _summary(errs, label):
    errs = [e for e in errs if e is not None]
    if not errs:
        print(f'  {label}: no data')
        return
    a = sorted(abs(e) for e in errs)
    n = len(a)
    w = lambda k: sum(1 for e in a if e <= k) / n
    print(f'  {label}:  n={n}  median|e|={statistics.median(a):.2f}f  '
          f'p90={a[int(0.9 * (n - 1))]:.2f}f  bias(med)={statistics.median(errs):+.2f}f  '
          f'<=1f={w(1):.0%}  <=2f={w(2):.0%}  <=3f={w(3):.0%}  <=5f={w(5):.0%}')


def report():
    if not os.path.exists(OUT_CSV):
        print('no CSV yet', file=sys.stderr)
        return
    rows = list(csv.DictReader(open(OUT_CSV, newline='')))
    errored = [r for r in rows if r.get('error')]
    ok = [r for r in rows if not r.get('error')]
    with_onset = [r for r in ok if r.get('strongest_time') not in ('', None)]

    print('\n' + '=' * 74)
    print(f'AUDIO-ONSET CONTACT EVAL  --  {len(rows)} clips  '
          f'({len(ok)} ok, {len(errored)} errored, {len(with_onset)} with >=1 onset)')
    print('=' * 74)
    if errored:
        from collections import Counter
        print('errors:', dict(Counter(r['error'].split(':')[0] for r in errored)))
    print(f'no onset detected at all: {len(ok) - len(with_onset)} / {len(ok)}')

    def biasc(vals):
        return [v - ONSET_BIAS_F if v is not None else None for v in vals]

    print(f'\nSTRATEGIES (frames @ 59.94fps)  [raw]')
    _summary([_f(r['strongest_err_f']) for r in with_onset], 'strongest onset      ')
    _summary([_f(r['nearest_anchor_err_f']) for r in with_onset], 'nearest to anchor(1s)')
    _summary([_f(r['windowed_strongest_err_f']) for r in with_onset], 'windowed strongest   ')
    _summary([_f(r['oracle_best_err_f']) for r in with_onset], 'oracle (best onset)  ')

    print(f'\nSTRATEGIES  [bias-corrected -{ONSET_BIAS_F}f]')
    _summary(biasc([_f(r['strongest_err_f']) for r in with_onset]), 'strongest onset      ')
    _summary(biasc([_f(r['windowed_strongest_err_f']) for r in with_onset]), 'windowed strongest   ')
    _summary(biasc([_f(r['oracle_best_err_f']) for r in with_onset]), 'oracle (best onset)  ')

    print('\nORACLE CEILING (is a correct onset present at all?)')
    orc = [abs(_f(r['oracle_best_err_f'])) for r in with_onset if _f(r['oracle_best_err_f']) is not None]
    if orc:
        n = len(orc)
        for k in (1, 2, 3, 5):
            print(f'  onset within +-{k}f of truth: {sum(1 for e in orc if e <= k) / n:.0%}  '
                  f'(of {n} clips with any onset; {n}/{len(ok)} = {n/len(ok):.0%} of all)')

    print('\nBY SHOT TYPE (nearest-to-anchor)')
    byst = defaultdict(list)
    for r in with_onset:
        byst[r['shot_type']].append(_f(r['nearest_anchor_err_f']))
    for k in sorted(byst):
        _summary(byst[k], f'{k:<20}')

    print('\nBY SOURCE VIDEO (nearest-to-anchor)')
    bysrc = defaultdict(list)
    for r in with_onset:
        bysrc[r['source_video']].append(_f(r['nearest_anchor_err_f']))
    for k in sorted(bysrc):
        _summary(bysrc[k], f'{k:<28}')

    print('\n10 WORST (nearest-to-anchor)')
    worst = sorted((r for r in with_onset if _f(r['nearest_anchor_err_f']) is not None),
                   key=lambda r: -abs(_f(r['nearest_anchor_err_f'])))[:10]
    for r in worst:
        print(f'  {r["id"]:<16} {r["shot_type"]:<9} err={float(r["nearest_anchor_err_f"]):+7.1f}f  '
              f'teacher={r["teacher_time"]}s picked={r["nearest_anchor_time"]}s  '
              f'n_onsets={r["n_onsets"]} oracle_err={r["oracle_best_err_f"]}f  {r["source_video"]}')
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--only')
    ap.add_argument('--report-only', action='store_true')
    ap.add_argument('--highpass', type=float, default=HIGHPASS_HZ_DEFAULT)
    ap.add_argument('--anchor-sec', type=float, default=ANCHOR_SEC_DEFAULT)
    args = ap.parse_args()
    if args.report_only:
        report()
        return
    only = set(args.only.split(',')) if args.only else None
    run(limit=args.limit, only=only, highpass_hz=args.highpass, anchor_sec=args.anchor_sec)


if __name__ == '__main__':
    main()
