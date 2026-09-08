"""
Similarity-score calibration harness.

Answers one question with real data: does either 0-100 score RallyMax shows a
user actually behave the way Jack wants --

  * a clip already IN the pro database      -> ~100  ("that's literally a pro")
  * a competent amateur swing               -> ~50   ("solid, room to improve")
  * a fresh ATP swing NOT in the database   -> ~85-92 ("basically pro")

...and if so, what `scale` constant gets it there. Two scores are compared
head-to-head because the app currently shows BOTH on one screen at different,
uncalibrated scales (see the plan / STATUS.md "score presentation"):

  full-traj : compare_swing.similarity_score(dtw over the whole trajectory)   scale 0.4
  phase     : phase_breakdown overall_score (sum of 4 windowed sub-scores)     PHASE_SCALE 1.8

Three buckets, all from data already on disk -- no new labels, no Claude calls:

  in_db      ~20 pro_database.json entries, matched against the FULL pool
             (themselves included) -- sanity check, should pin ~100
  held_out   ~15 other pro entries, matched with their own id EXCLUDED
             -- the "fresh ATP" proxy
  amateur    real (non-'skip') swings from data/08_coaching_ai/amateur_swing_labels.json,
             contact frame derived exactly like evaluate_amateur_dataset.py

Lean match path -- does NOT call compare_swing.compare() (that also runs racket
/ ball / overlay tracking for the UI). Reuses extract_user_poses ->
build_user_trajectory -> infer_camera_angle/detect_view_direction -> the same
angle +-window and view-direction candidate filters compare() uses -> dtw over
candidates. track_racket_body is run once per clip only for the phase metric's
body-rotation sub-score (skip with --no-racket).

Usage:
  python calibrate_similarity.py                     # process every bucket + report
  python calibrate_similarity.py --limit 6           # smoke test (2 per bucket)
  python calibrate_similarity.py --report-only       # re-print from the jsonl
  python calibrate_similarity.py --no-racket         # skip racket tracking (phase body-rotation omitted)
  python calibrate_similarity.py --in-db 20 --held-out 15 --amateur 50
"""
import argparse
import json
import math
import os
import sys
from collections import defaultdict

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '08_comparison_engine'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '09_coaching_ai'))

from paths import DATA_DIR  # noqa: E402
from compare_swing import (  # noqa: E402
    extract_user_poses, build_user_trajectory, eligible_match_candidates, KEY_LANDMARKS,
    eligible_by_angle, ANGLE_WINDOW, MIN_POOL_AFTER_FILTER,
)
from build_pro_database import PRE_SEC, POST_SEC  # noqa: E402
from trajectory_compare import dtw_distance  # noqa: E402
from trajectory_extraction import rotate_trajectory  # noqa: E402
from infer_angle import infer_camera_angle, detect_view_direction, extract_frame, create_landmarker, usable_roll  # noqa: E402
from track_racket_in_clip import track_racket_body, avg_racket_body_distance  # noqa: E402
import phase_breakdown  # noqa: E402

DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
CLIPS_DIR = os.path.join(DATA_DIR, '04_clips')
AMATEUR_LABELS_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'amateur_swing_labels.json')
AMATEUR_MANIFEST_PATH = os.path.join(CLIPS_DIR, 'amateur', 'manifest.json')
SWINGS_DIR = os.path.join(DATA_DIR, '03_swing_detection')
OUT_DIR = os.path.join(DATA_DIR, '17_amateur_eval')
RESULTS_PATH = os.path.join(OUT_DIR, 'similarity_calibration.jsonl')

# ANGLE_WINDOW / MIN_POOL_AFTER_FILTER now live in compare_swing.py and are
# re-exported through the import above so redesign_similarity.py's
# `from calibrate_similarity import ANGLE_WINDOW, ...` keeps working unchanged.

# scale sweep grids -- wide enough to bracket the current constants (0.4 / 1.8)
FULLTRAJ_SCALES = [round(0.15 + 0.05 * i, 2) for i in range(24)]   # 0.15 .. 1.30
PHASE_SCALES = [round(0.8 + 0.2 * i, 1) for i in range(22)]         # 0.8 .. 5.0


# ── stats helpers (numpy-free, same spirit as evaluate_amateur_dataset.py) ────

def _pct(sorted_vals, q):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def _summary(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return {'n': 0}
    return {
        'n': len(vals),
        'p25': round(_pct(vals, 0.25), 3),
        'median': round(_pct(vals, 0.50), 3),
        'p75': round(_pct(vals, 0.75), 3),
        'min': round(vals[0], 3),
        'max': round(vals[-1], 3),
    }


def fulltraj_score(dist, scale):
    return round(max(0.0, 100 * math.exp(-dist / scale)), 1)


def phase_score_from_dists(phase_dists, scale):
    """Recompute overall_score (0-100) from the 4 stored raw phase distances
    under a candidate PHASE_SCALE. None phases (unscoreable) are dropped and
    the remaining phases are rescaled to a 0-100 range so buckets with a
    missing phase stay comparable."""
    usable = [d for d in phase_dists if d is not None]
    if not usable:
        return None
    per_phase = [max(0.0, min(25.0, 25 * math.exp(-d / scale))) for d in usable]
    return round(sum(per_phase) * (4 / len(usable)), 1)


# ── query building ───────────────────────────────────────────────────────────

def load_swings(video_id, cache={}):
    if video_id not in cache:
        with open(os.path.join(SWINGS_DIR, f'amateur_{video_id}_swings.json')) as f:
            data = json.load(f)
        cache[video_id] = {sw['swing_id']: sw for sw in data['swings']}
    return cache[video_id]


def build_queries(n_in_db, n_held_out, n_amateur):
    """Deterministic sample -> list of query dicts:
       {key, bucket, shot_type, clip_path, contact_time_sec, exclude_ids}"""
    with open(DB_PATH) as f:
        db = json.load(f)
    entries_by_type = defaultdict(list)
    for e in db['entries']:
        # unreviewed practice-footage entries are held out of the live match
        # pool by eligible_match_candidates() -- so a practice clip used as an
        # 'in_db' query would match against the real pool, NOT itself, and
        # silently behave like a held-out query. Keep the pro buckets to
        # hand-reviewed broadcast entries only.
        if e.get('ingest') == 'practice_mvp':
            continue
        entries_by_type[e['shot_type']].append(e)
    for lst in entries_by_type.values():
        lst.sort(key=lambda e: e['id'])

    queries = []

    def take_pro(bucket, count, exclude_self):
        # spread the count across shot types, evenly-strided within each type
        per_type = max(1, count // len(entries_by_type))
        picked = []
        for st, lst in sorted(entries_by_type.items()):
            # held_out starts a third of the way in so it can't overlap the
            # front-loaded in_db sample
            offset = len(lst) // 3 if bucket == 'held_out' else 0
            pool = lst[offset:] or lst
            stride = max(1, len(pool) // per_type)
            for e in pool[::stride][:per_type]:
                picked.append((st, e))
        for st, e in picked[:count]:
            clip_rel = e.get('clip_path')
            if not clip_rel:
                continue
            queries.append({
                'key': f'{bucket}:{e["id"]}',
                'bucket': bucket,
                'shot_type': st,
                'clip_path': os.path.join(CLIPS_DIR, clip_rel),
                'contact_time_sec': e.get('clip_contact_time_sec'),
                'exclude_ids': [e['id']] if exclude_self else [],
            })

    take_pro('in_db', n_in_db, exclude_self=False)
    take_pro('held_out', n_held_out, exclude_self=True)

    # amateur
    with open(AMATEUR_LABELS_PATH) as f:
        labels = json.load(f)['labels']
    with open(AMATEUR_MANIFEST_PATH) as f:
        manifest = {f"{m['video_id']}_{m['swing_id']}": m for m in json.load(f)}
    real = [(k, v) for k, v in sorted(labels.items()) if v in ('forehand', 'backhand', 'serve')]
    # even stride so all 3 shot types are represented rather than the first N
    stride = max(1, len(real) // n_amateur) if n_amateur else 1
    for key, shot_type in real[::stride][:n_amateur]:
        m = manifest.get(key)
        if not m:
            continue
        video_id, swing_id = m['video_id'], m['swing_id']
        sw = load_swings(video_id).get(swing_id)
        if not sw:
            continue
        # clip frame 0 == swing start_frame (extract_clips.py); manifest
        # peak_frame is source-relative -- same derivation as
        # evaluate_amateur_dataset.process_example()
        clip_peak_frame = m['peak_frame'] - sw['start_frame']
        queries.append({
            'key': f'amateur:{key}',
            'bucket': 'amateur',
            'shot_type': shot_type,
            'clip_path': m['clip_path'],
            'contact_time_sec': None,          # filled per-clip once we know fps
            'clip_peak_frame': clip_peak_frame,
            'exclude_ids': [],
        })
    return queries


# ── one query ────────────────────────────────────────────────────────────────

def run_query(q, db_entries, reviewed_ids, with_racket, landmarker):
    clip = q['clip_path']
    if not os.path.exists(clip):
        return {**_meta(q), 'error': f'clip not found: {clip}'}

    frames, fps = extract_user_poses(clip)
    if not frames:
        return {**_meta(q), 'error': 'no frames decoded'}

    contact_time_sec = q.get('contact_time_sec')
    if contact_time_sec is None and q.get('clip_peak_frame') is not None:
        contact_time_sec = q['clip_peak_frame'] / fps

    user_traj, peak_frame = build_user_trajectory(frames, fps, contact_time_sec, shot_type=q['shot_type'])
    if not user_traj:
        return {**_meta(q), 'error': 'no usable pose trajectory'}

    # camera angle + view direction + roll -- same signals compare() filters on
    user_angle, angle_conf, angle_debug = infer_camera_angle(clip, peak_frame, landmarker=landmarker)
    roll = usable_roll(angle_debug.get('camera_roll_deg') if isinstance(angle_debug, dict) else None)
    if roll is not None:
        user_traj = rotate_trajectory(user_traj, roll)
    view = 'unknown'
    try:
        view = detect_view_direction(extract_frame(clip, peak_frame), landmarker=landmarker)
    except Exception:
        pass

    # candidate pool: eligible -> exclude self -> angle filter -> view filter,
    # each with compare()'s "fall back if <5 left" rule
    pool = [e for e in eligible_match_candidates(db_entries, q['shot_type'], reviewed_ids)
            if e['id'] not in set(q['exclude_ids'])]
    pool, _ = eligible_by_angle(pool, user_angle, None, conf_aware=False)
    if view in ('front', 'back'):
        vf = [c for c in pool if c.get('view_direction') == view]
        if len(vf) >= MIN_POOL_AFTER_FILTER:
            pool = vf
    if not pool:
        return {**_meta(q), 'error': 'empty candidate pool'}

    best = min(pool, key=lambda c: dtw_distance(user_traj, c['trajectory'], KEY_LANDMARKS))
    best_dist = dtw_distance(user_traj, best['trajectory'], KEY_LANDMARKS)

    # phase metric against the same best candidate
    user_rbd = None
    if with_racket:
        try:
            lo = peak_frame - int(PRE_SEC * fps)
            hi = peak_frame + int(POST_SEC * fps)
            user_rbd = avg_racket_body_distance(track_racket_body(clip, frame_range=(lo, hi), sample_every=4))
        except Exception as e:
            print(f'  racket track failed (non-fatal): {e}', file=sys.stderr)
    phase_dists = _phase_raw_distances(user_traj, best, q['shot_type'], user_rbd)

    return {
        **_meta(q),
        'fps': round(fps, 2),
        'user_angle': user_angle, 'angle_conf': angle_conf, 'view': view,
        'pool_size': len(pool),
        'best_pro_id': best['id'],
        'fulltraj_dist': round(best_dist, 4),
        'phase_dists': phase_dists,           # [backswing, contact, follow, body_rotation] raw distances (or None)
        'has_racket': user_rbd is not None,
    }


def _meta(q):
    return {'key': q['key'], 'bucket': q['bucket'], 'shot_type': q['shot_type']}


def _phase_raw_distances(user_traj, pro_entry, shot_type, user_rbd):
    """Raw (pre-exp) distances for the 4 phase sub-scores, so the report can
    sweep PHASE_SCALE without re-running DTW. Mirrors
    phase_breakdown.score_phase / score_body_rotation internals."""
    pb = phase_breakdown
    out = []
    for _, target_t in pb.PHASE_TARGET_T.items():
        us = pb._slice_window(user_traj, target_t, pb.PHASE_WINDOW) or (
            [pb._nearest(user_traj, target_t)] if pb._nearest(user_traj, target_t) else [])
        ps = pb._slice_window(pro_entry['trajectory'], target_t, pb.PHASE_WINDOW) or (
            [pb._nearest(pro_entry['trajectory'], target_t)] if pb._nearest(pro_entry['trajectory'], target_t) else [])
        if not us or not ps:
            out.append(None)
            continue
        d = dtw_distance(us, ps, pb.KEY_LANDMARKS)
        out.append(round(d, 4) if d != float('inf') else None)
    # body rotation: convert its 0-25 score back to an equivalent distance so
    # it can ride the same sweep (score = 25*exp(-d/ROTATION_SCALE_DEG) style).
    rot = pb.score_body_rotation(user_traj, pro_entry['trajectory'], user_rbd,
                                 pro_entry.get('racket_body_distance'))
    if rot['score'] is None:
        out.append(None)
    else:
        s = min(24.999, max(0.001, rot['score']))
        out.append(round(-pb.PHASE_SCALE * math.log(s / 25), 4))
    return out


# ── checkpoint io ────────────────────────────────────────────────────────────

def load_checkpoint():
    done = {}
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    done[rec['key']] = rec
                except (json.JSONDecodeError, KeyError):
                    continue
    return done


def append_result(rec):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RESULTS_PATH, 'a') as f:
        f.write(json.dumps(rec) + '\n')


# ── report ───────────────────────────────────────────────────────────────────

def print_report():
    done = load_checkpoint()
    recs = [r for r in done.values() if not r.get('error')]
    errs = [r for r in done.values() if r.get('error')]
    by_bucket = defaultdict(list)
    for r in recs:
        by_bucket[r['bucket']].append(r)

    print(f'\n=== similarity calibration : {len(recs)} scored, {len(errs)} errored ===')
    for r in errs:
        print(f'  ERR {r["key"]}: {r["error"]}')

    print('\n--- raw best-match DTW distance (lower = more similar) ---')
    print(f'{"bucket":10s} {"n":>4s} {"p25":>8s} {"median":>8s} {"p75":>8s}   full-traj')
    for b in ('in_db', 'held_out', 'amateur'):
        s = _summary([r['fulltraj_dist'] for r in by_bucket.get(b, [])])
        if s['n']:
            print(f'{b:10s} {s["n"]:>4d} {s["p25"]:>8.3f} {s["median"]:>8.3f} {s["p75"]:>8.3f}')

    # phase: sum the 4 raw distances per record for a single comparable number
    def phase_total(r):
        ds = [d for d in r.get('phase_dists', []) if d is not None]
        return sum(ds) / len(ds) * 4 if ds else None
    print(f'\n{"bucket":10s} {"n":>4s} {"p25":>8s} {"median":>8s} {"p75":>8s}   phase (mean sub-dist x4)')
    for b in ('in_db', 'held_out', 'amateur'):
        s = _summary([phase_total(r) for r in by_bucket.get(b, [])])
        if s['n']:
            print(f'{b:10s} {s["n"]:>4d} {s["p25"]:>8.3f} {s["median"]:>8.3f} {s["p75"]:>8.3f}')

    _sweep('FULL-TRAJECTORY  score = 100*exp(-dist/scale)', FULLTRAJ_SCALES, by_bucket,
           lambda r, sc: fulltraj_score(r['fulltraj_dist'], sc))
    _sweep('PHASE  overall_score = sum(25*exp(-d_i/scale))', PHASE_SCALES, by_bucket,
           lambda r, sc: phase_score_from_dists(r.get('phase_dists', []), sc))

    _recommend('full-traj', FULLTRAJ_SCALES, by_bucket,
               lambda r, sc: fulltraj_score(r['fulltraj_dist'], sc))
    _recommend('phase', PHASE_SCALES, by_bucket,
               lambda r, sc: phase_score_from_dists(r.get('phase_dists', []), sc))

    _separation(by_bucket)


def _median_score(recs, sc, fn):
    vals = sorted(v for v in (fn(r, sc) for r in recs) if v is not None)
    return _pct(vals, 0.5) if vals else None


def _sweep(title, scales, by_bucket, fn):
    print(f'\n--- scale sweep : {title} ---')
    print(f'{"scale":>6s} {"in_db":>8s} {"held_out":>9s} {"amateur":>8s}')
    for sc in scales:
        row = [_median_score(by_bucket.get(b, []), sc, fn) for b in ('in_db', 'held_out', 'amateur')]
        cells = ' '.join(f'{v:>8.1f}' if v is not None else f'{"--":>8s}' for v in row)
        mark = '  <' if row[2] is not None and 45 <= row[2] <= 55 else ''
        print(f'{sc:>6.2f} {cells}{mark}')


def _recommend(name, scales, by_bucket, fn):
    # pick the scale whose amateur median is closest to 50
    best_sc, best_gap = None, 1e9
    for sc in scales:
        med = _median_score(by_bucket.get('amateur', []), sc, fn)
        if med is None:
            continue
        gap = abs(med - 50)
        if gap < best_gap:
            best_sc, best_gap = sc, gap
    if best_sc is None:
        print(f'\n[{name}] no amateur data -- cannot recommend a scale')
        return
    meds = {b: _median_score(by_bucket.get(b, []), best_sc, fn) for b in ('in_db', 'held_out', 'amateur')}
    print(f'\n[{name}] recommended scale = {best_sc}  ->  '
          f'in_db {meds["in_db"]}, held_out {meds["held_out"]}, amateur {meds["amateur"]}')


def _separation(by_bucket):
    print('\n--- separation diagnostic ---')
    for metric, key, cast in (('full-traj', 'fulltraj_dist', lambda r: r.get('fulltraj_dist')),
                              ('phase', 'phase_dists',
                               lambda r: (sum(d for d in r.get('phase_dists', []) if d is not None)
                                          if any(d is not None for d in r.get('phase_dists', [])) else None))):
        ho = sorted(v for v in (cast(r) for r in by_bucket.get('held_out', [])) if v is not None)
        am = sorted(v for v in (cast(r) for r in by_bucket.get('amateur', [])) if v is not None)
        if not ho or not am:
            continue
        ho_med, am_med = _pct(ho, 0.5), _pct(am, 0.5)
        gap = am_med - ho_med
        verdict = ('OK -- held-out pros clearly closer than amateurs'
                   if gap > 0.15 * am_med else
                   'WEAK -- held-out pros ~= amateurs; DTW itself may not separate '
                   'pro from amateur and NO rescale fixes that')
        print(f'  {metric:10s}: held_out median dist {ho_med:.3f} vs amateur {am_med:.3f}  ->  {verdict}')


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in-db', type=int, default=20)
    ap.add_argument('--held-out', type=int, default=15)
    ap.add_argument('--amateur', type=int, default=45)
    ap.add_argument('--limit', type=int, default=None, help='cap total queries (2 per bucket-ish smoke test)')
    ap.add_argument('--no-racket', action='store_true', help='skip racket tracking; phase body-rotation omitted')
    ap.add_argument('--report-only', action='store_true')
    args = ap.parse_args()

    if args.report_only:
        print_report()
        return

    n_in, n_ho, n_am = args.in_db, args.held_out, args.amateur
    if args.limit:
        n_in = n_ho = n_am = max(2, args.limit // 3)
    queries = build_queries(n_in, n_ho, n_am)
    if args.limit:
        queries = queries[:args.limit]

    with open(DB_PATH) as f:
        db_entries = json.load(f)['entries']
    import clip_review_log
    reviewed_ids = clip_review_log.get_label_reviewed_ids()

    done = load_checkpoint()
    landmarker = create_landmarker()
    try:
        for i, q in enumerate(queries, 1):
            if q['key'] in done:
                continue
            print(f'[{i}/{len(queries)}] {q["key"]} ({q["shot_type"]})...', file=sys.stderr)
            try:
                rec = run_query(q, db_entries, reviewed_ids, not args.no_racket, landmarker)
            except Exception as e:
                rec = {**_meta(q), 'error': str(e)}
                print(f'  ERROR: {e}', file=sys.stderr)
            append_result(rec)
    finally:
        try:
            landmarker.close()
        except Exception:
            pass

    print_report()


if __name__ == '__main__':
    main()
