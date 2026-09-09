"""
Metric-redesign bench for the swing-similarity score.

calibrate_similarity.py established (2026-09-08) that the current unconstrained
DTW over normalised landmark positions does NOT separate a held-out ATP pro
(median best-match dist 0.455) from a club amateur (0.484). Jack's call: redesign
the metric before doing any score unification.

This script:
  1. `cache`  -- extract each eval query's user trajectory once (roll-corrected,
                 same front-half as calibrate_similarity.run_query) and dump it to
                 data/17_amateur_eval/traj_cache/<key>.json, together with the
                 angle/view-filtered candidate-pool ids. Slow (pose extraction),
                 run once.
  2. `eval`   -- load the cache + pro DB and score every registered metric
                 variant against all 3 buckets, printing the separation table so
                 variants can be compared without re-extracting anything.
  3. `decomp` -- for the in-DB bucket, compare each query against its OWN stored
                 entry and try small time offsets, to see how much of the ~0.15
                 "identical footage" distance is contact-anchor misalignment vs
                 pipeline normalisation drift.

Usage:
  python redesign_similarity.py cache        # once (~15 min, competes with training)
  python redesign_similarity.py eval         # fast, iterate here
  python redesign_similarity.py decomp
"""
import argparse
import json
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from calibrate_similarity import (  # noqa: E402  -- reuse the harness front-half
    build_queries, _meta, _summary, _pct, DB_PATH, OUT_DIR,
    ANGLE_WINDOW, MIN_POOL_AFTER_FILTER,
)

SCRIPTS_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '08_comparison_engine'))
from compare_swing import extract_user_poses, build_user_trajectory, eligible_match_candidates, KEY_LANDMARKS  # noqa: E402
from build_pro_database import PRE_SEC, POST_SEC  # noqa: E402
from trajectory_extraction import rotate_trajectory, mirror_trajectory  # noqa: E402
from infer_angle import infer_camera_angle, detect_view_direction, extract_frame, create_landmarker, usable_roll  # noqa: E402
import clip_review_log  # noqa: E402

sys.path.insert(0, os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking'))
from track_racket_in_clip import track_racket_body, avg_racket_body_distance, racket_body_features  # noqa: E402

CACHE_DIR = os.path.join(OUT_DIR, 'traj_cache')
CACHE_VERSION = 4   # v4: z on every joint is metric world-derived (soft-yaw
                    # rotated), regardless of whether x/y were yaw-normalized --
                    # so the depth axes fire on the whole pool, not just the
                    # hard-yaw subset. v3: yaw-normalized user trajectories.
                    # v2: + racket_frames, + LH-mirror for amateur queries.


def _rec_metric_z(rec):
    """v4 cache recs carry an explicit z_metric flag (metric world-derived z on
    every joint -- see the trajectory_extraction z-overlay). v3 and below: only
    when yaw actually rotated the swing."""
    if rec.get('v', 1) >= 4:
        return rec.get('z_metric', True)
    return rec.get('v', 1) >= 3 and rec.get('user_yaw_deg') is not None


def _entry_metric_z(entry):
    """A traj_version-4 pro entry carries metric world-derived z on every joint.
    v3: only when the reslice actually yaw-rotated it (traj_yaw_deg not None)."""
    tv = entry.get('traj_version', 0)
    if tv >= 4:
        return True
    return tv >= 3 and entry.get('traj_yaw_deg') is not None

# swing-arm chain carries the technique signal; nose/hips are gross position
LANDMARK_WEIGHTS = {
    'nose': 0.5,
    'left_shoulder': 1.0, 'right_shoulder': 1.0,
    'left_elbow': 1.5, 'right_elbow': 1.5,
    'left_wrist': 2.0, 'right_wrist': 2.0,
    'left_hip': 0.75, 'right_hip': 0.75,
}


# ── frame-distance kernels ───────────────────────────────────────────────────

def _fd_mean(a, b, names):
    tot = n = 0.0
    for k in names:
        pa, pb = a.get(k), b.get(k)
        if pa is None or pb is None:
            continue
        tot += math.hypot(pa['x'] - pb['x'], pa['y'] - pb['y'])
        n += 1
    return tot / n if n else 1.5


def _fd_weighted(a, b, names):
    tot = w = 0.0
    for k in names:
        pa, pb = a.get(k), b.get(k)
        if pa is None or pb is None:
            continue
        wk = LANDMARK_WEIGHTS.get(k, 1.0)
        tot += wk * math.hypot(pa['x'] - pb['x'], pa['y'] - pb['y'])
        w += wk
    return tot / w if w else 1.5


# ── DTW variants ─────────────────────────────────────────────────────────────

def dtw(traj_a, traj_b, fd=_fd_mean, band=None, warp_penalty=0.0):
    n, m = len(traj_a), len(traj_b)
    if n == 0 or m == 0:
        return float('inf')
    INF = float('inf')
    prev = [INF] * (m + 1)
    prev[0] = 0.0
    la = [p['landmarks'] for p in traj_a]
    lb = [p['landmarks'] for p in traj_b]
    w = int(max(n, m) * band) if band else None
    for i in range(1, n + 1):
        cur = [INF] * (m + 1)
        jlo, jhi = 1, m
        if w is not None:
            centre = i * m / n
            jlo = max(1, int(centre - w))
            jhi = min(m, int(centre + w))
        ai = la[i - 1]
        for j in range(jlo, jhi + 1):
            cost = fd(ai, lb[j - 1], KEY_LANDMARKS)
            diag = prev[j - 1]
            up = prev[j] + warp_penalty
            left = cur[j - 1] + warp_penalty
            cur[j] = cost + min(diag, up, left)
        prev = cur
    return prev[m] / max(n, m)


# ── feature trajectory ───────────────────────────────────────────────────────

def _angle(lm, a, b, c):
    pa, pb, pc = lm.get(a), lm.get(b), lm.get(c)
    if not pa or not pb or not pc:
        return None
    v1 = (pa['x'] - pb['x'], pa['y'] - pb['y'])
    v2 = (pc['x'] - pb['x'], pc['y'] - pb['y'])
    d = math.hypot(*v1) * math.hypot(*v2)
    if d == 0:
        return None
    cosv = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / d))
    return math.acos(cosv)


def to_feature_traj(traj):
    """Re-express a trajectory as per-frame biomechanical scalars (elbow
    angles, shoulder & hip line angle, wrist height relative to shoulder,
    shoulder-hip separation). Wrapped back into the {'landmarks': {...}}
    shape so the same dtw() can consume it -- each 'landmark' here is a
    1-D feature stored as {'x': value, 'y': 0}."""
    out = []
    for p in traj:
        lm = p['landmarks']
        feats = {}
        re = _angle(lm, 'right_shoulder', 'right_elbow', 'right_wrist')
        le = _angle(lm, 'left_shoulder', 'left_elbow', 'left_wrist')
        if re is not None:
            feats['r_elbow'] = {'x': re, 'y': 0}
        if le is not None:
            feats['l_elbow'] = {'x': le, 'y': 0}
        ls, rs = lm.get('left_shoulder'), lm.get('right_shoulder')
        lh, rh = lm.get('left_hip'), lm.get('right_hip')
        if ls and rs:
            sang = math.atan2(rs['y'] - ls['y'], rs['x'] - ls['x'])
            feats['sh_line'] = {'x': sang, 'y': 0}
            rw = lm.get('right_wrist')
            if rw:
                feats['rw_height'] = {'x': (rw['y'] - (ls['y'] + rs['y']) / 2), 'y': 0}
        if lh and rh:
            hang = math.atan2(rh['y'] - lh['y'], rh['x'] - lh['x'])
            feats['hip_line'] = {'x': hang, 'y': 0}
        if ls and rs and lh and rh:
            feats['xfactor'] = {'x': sang - hang, 'y': 0}
        out.append({'t': p['t'], 'landmarks': feats})
    return out


_FEATURE_NAMES = ['r_elbow', 'l_elbow', 'sh_line', 'hip_line', 'xfactor', 'rw_height']


def _fd_feature(a, b, _names):
    tot = n = 0.0
    for k in _FEATURE_NAMES:
        pa, pb = a.get(k), b.get(k)
        if pa is None or pb is None:
            continue
        tot += abs(pa['x'] - pb['x'])
        n += 1
    return tot / n if n else 2.0


# ── metric registry : name -> fn(user_traj, pro_traj) -> raw distance ─────────

def _best(user_traj, pool_trajs, scorer, k=1):
    ds = sorted(scorer(user_traj, pt) for pt in pool_trajs)
    ds = [d for d in ds if d != float('inf')]
    if not ds:
        return float('inf')
    return sum(ds[:k]) / min(k, len(ds))


METRICS = {
    'v0_baseline':     lambda u, pool: _best(u, pool, lambda a, b: dtw(a, b, _fd_mean)),
    'v1_band10':       lambda u, pool: _best(u, pool, lambda a, b: dtw(a, b, _fd_mean, band=0.10)),
    'v2_warp0.05':     lambda u, pool: _best(u, pool, lambda a, b: dtw(a, b, _fd_mean, warp_penalty=0.05)),
    'v3_weighted':     lambda u, pool: _best(u, pool, lambda a, b: dtw(a, b, _fd_weighted)),
    'v4_feature':      lambda u, pool: _best(to_feature_traj(u), [to_feature_traj(p) for p in pool],
                                             lambda a, b: dtw(a, b, _fd_feature, band=0.15)),
    'v5_k5nearest':    lambda u, pool: _best(u, pool, lambda a, b: dtw(a, b, _fd_mean), k=5),
    'v6_band+weight+warp': lambda u, pool: _best(u, pool, lambda a, b: dtw(a, b, _fd_weighted, band=0.10, warp_penalty=0.03)),
    'v7_feat+k5':      lambda u, pool: _best(to_feature_traj(u), [to_feature_traj(p) for p in pool],
                                             lambda a, b: dtw(a, b, _fd_feature, band=0.15), k=5),
}


# ── cache phase ──────────────────────────────────────────────────────────────

def do_cache(args):
    queries = build_queries(args.in_db, args.held_out, args.amateur)
    with open(DB_PATH) as f:
        db_entries = json.load(f)['entries']
    reviewed = clip_review_log.get_label_reviewed_ids()
    os.makedirs(CACHE_DIR, exist_ok=True)
    lmk = create_landmarker()
    try:
        for i, q in enumerate(queries, 1):
            cp = os.path.join(CACHE_DIR, q['key'].replace(':', '__').replace('/', '_') + '.json')
            if os.path.exists(cp):
                try:
                    if json.load(open(cp)).get('v', 1) >= CACHE_VERSION:
                        continue
                except Exception:
                    pass
            print(f'[{i}/{len(queries)}] {q["key"]}', file=sys.stderr)
            try:
                rec = _extract_one(q, db_entries, reviewed, lmk)
            except Exception as e:
                rec = {**_meta(q), 'error': str(e)}
                print(f'  ERR {e}', file=sys.stderr)
            with open(cp, 'w') as f:
                json.dump(rec, f)
    finally:
        try:
            lmk.close()
        except Exception:
            pass
    print('cache done')


def _extract_one(q, db_entries, reviewed, lmk):
    clip = q['clip_path']
    if not os.path.exists(clip):
        return {**_meta(q), 'error': 'clip missing'}
    frames, fps = extract_user_poses(clip)
    if not frames:
        return {**_meta(q), 'error': 'no frames'}
    ct = q.get('contact_time_sec')
    if ct is None and q.get('clip_peak_frame') is not None:
        ct = q['clip_peak_frame'] / fps
    # yaw_enabled=True: x/y are yaw-normalized to a canonical facing when the
    # lead-in estimate is confident. The z channel is metric world-derived
    # regardless (v4) -- yaw_meta['z_metric'] says whether it landed.
    user_traj, peak, yaw_meta = build_user_trajectory(frames, fps, ct, shot_type=q['shot_type'],
                                                      yaw_enabled=True, return_meta=True)
    if not user_traj:
        return {**_meta(q), 'error': 'no trajectory'}
    user_angle, _conf, dbg = infer_camera_angle(clip, peak, landmarker=lmk)
    roll = usable_roll(dbg.get('camera_roll_deg') if isinstance(dbg, dict) else None)
    if roll is not None:
        user_traj = rotate_trajectory(user_traj, roll)
    # LH amateurs are not mirrored by the eval path (no handedness label) and
    # inflate the amateur bucket's spread. Heuristic: the swinging wrist is the
    # one that travels farther through the window; if it's the left, mirror so
    # the swing lands in the same RH convention the pro DB is normalised to.
    mirrored = False
    if q['bucket'] == 'amateur' and _dominant_wrist(user_traj) == 'left':
        user_traj = mirror_trajectory(user_traj)
        mirrored = True
    view = 'unknown'
    try:
        view = detect_view_direction(extract_frame(clip, peak), landmarker=lmk)
    except Exception:
        pass
    pool = [e for e in eligible_match_candidates(db_entries, q['shot_type'], reviewed)
            if e['id'] not in set(q['exclude_ids'])]
    if user_angle is not None:
        af = [c for c in pool if c.get('camera_angle') is not None
              and abs(c['camera_angle'] - user_angle) <= ANGLE_WINDOW]
        if len(af) >= MIN_POOL_AFTER_FILTER:
            pool = af
    if view in ('front', 'back'):
        vf = [c for c in pool if c.get('view_direction') == view]
        if len(vf) >= MIN_POOL_AFTER_FILTER:
            pool = vf
    # racket handle path for racket-based axes (racket-to-body distance, lag)
    racket_frames = None
    try:
        lo = peak - int(PRE_SEC * fps)
        hi = peak + int(POST_SEC * fps)
        racket_frames = track_racket_body(clip, frame_range=(lo, hi), landmarker=lmk, sample_every=4)
    except Exception as e:
        print(f'  racket track failed (non-fatal): {e}', file=sys.stderr)

    return {
        **_meta(q), 'v': CACHE_VERSION, 'user_angle': user_angle, 'view': view, 'mirrored': mirrored,
        'fps': round(fps, 3), 'peak_frame': peak,
        'self_id': q['exclude_ids'][0] if q['exclude_ids'] else (q['key'].split(':', 1)[1] if q['bucket'] == 'in_db' else None),
        'pool_ids': [c['id'] for c in pool],
        'user_traj': user_traj,
        'user_yaw_deg': yaw_meta.get('yaw_deg'),
        'user_z_yaw_deg': yaw_meta.get('z_yaw_deg'),
        'z_metric': yaw_meta.get('z_metric', False),
        'racket_frames': racket_frames,
    }


def _dominant_wrist(traj):
    def path(name):
        pts = [p['landmarks'].get(name) for p in traj]
        pts = [q for q in pts if q]
        return sum(math.hypot(pts[i]['x'] - pts[i - 1]['x'], pts[i]['y'] - pts[i - 1]['y'])
                   for i in range(1, len(pts))) if len(pts) > 3 else 0.0
    r, l = path('right_wrist'), path('left_wrist')
    return 'left' if l > r * 1.25 else 'right'


# ── eval phase ───────────────────────────────────────────────────────────────

def _load_cache():
    recs = []
    for fn in os.listdir(CACHE_DIR):
        if not fn.endswith('.json'):
            continue
        with open(os.path.join(CACHE_DIR, fn)) as f:
            r = json.load(f)
        if not r.get('error'):
            recs.append(r)
    return recs


def do_eval(args):
    recs = _load_cache()
    with open(DB_PATH) as f:
        _entries = json.load(f)['entries']
    traj_by_id = {e['id']: e['trajectory'] for e in _entries}
    angle_by_id = {e['id']: e.get('camera_angle') for e in _entries}
    if args.angle_window:
        for r in recs:
            ua = r.get('user_angle')
            if ua is None:
                continue
            tight = [i for i in r['pool_ids']
                     if angle_by_id.get(i) is not None and abs(angle_by_id[i] - ua) <= args.angle_window]
            if len(tight) >= 5:
                r['pool_ids'] = tight
    by_bucket = defaultdict(list)
    for r in recs:
        by_bucket[r['bucket']].append(r)
    print(f'cache: { {k: len(v) for k, v in by_bucket.items()} }')

    names = args.metrics.split(',') if args.metrics else list(METRICS)
    print(f'\n{"metric":22s} {"in_db":>18s} {"held_out":>18s} {"amateur":>18s}   sep')
    print(f'{"":22s} {"p25 / med / p75":>18s} {"p25 / med / p75":>18s} {"p25 / med / p75":>18s}')
    for name in names:
        fn = METRICS[name]
        dists = defaultdict(list)
        for b, rs in by_bucket.items():
            for r in rs:
                pool = [traj_by_id[i] for i in r['pool_ids'] if i in traj_by_id]
                if not pool:
                    continue
                dists[b].append(fn(r['user_traj'], pool))
        row = []
        for b in ('in_db', 'held_out', 'amateur'):
            s = _summary(dists.get(b, []))
            row.append(f'{s.get("p25","-"):>5} /{s.get("median","-"):>5} /{s.get("p75","-"):>5}' if s['n'] else f'{"n=0":>18s}')
        ho = sorted(dists.get('held_out', []))
        am = sorted(dists.get('amateur', []))
        sep = ''
        if ho and am:
            ho_m, am_m = _pct(ho, 0.5), _pct(am, 0.5)
            sep = f'{(am_m - ho_m) / am_m * 100:+.0f}%'   # >0 = amateurs farther (good)
        print(f'{name:22s} {row[0]:>18s} {row[1]:>18s} {row[2]:>18s}   {sep}')
    print('\nsep = (amateur_median - heldout_median) / amateur_median. '
          'Bigger positive = metric separates pro from amateur better. v0 ~ +6%.')


# ── axes phase : does any biomechanical axis separate pro from amateur? ───────
#
# The rubric-score hypothesis (Jack, 2026-09-08): instead of nearest-pro
# trajectory distance, score each swing on independent biomechanical axes
# against the DISTRIBUTION of that axis across the pro database ("pros define
# the good range"). This phase tests whether the axes actually discriminate
# before any rubric is built -- if held-out pros don't sit more central in the
# pro distribution than amateurs do, the rubric is no better than v0.

def _pt_at(traj, t):
    return min(traj, key=lambda p: abs(p['t'] - t))['landmarks'] if traj else {}


def _mid(lm, a, b):
    pa, pb = lm.get(a), lm.get(b)
    if not pa or not pb:
        return None
    return ((pa['x'] + pb['x']) / 2, (pa['y'] + pb['y']) / 2)


def _win(traj, lo, hi):
    return [p for p in traj if lo <= p['t'] <= hi]


# ── depth (metric-z) axis helpers ────────────────────────────────────────────
# Only meaningful once BOTH trajectory sides are yaw-normalised metric 3D
# (traj_version >= 3): world landmarks rotated to a canonical facing and scaled
# by the metric shoulder width, so z is the same scale as x/y (unlike the raw
# monocular image-z, abs-median ~3x wider). Frame convention after
# yaw+project+normalise: x canonical image-right, y image-down, z world depth
# (toward the camera = smaller). RH convention (mirror_trajectory preserves z).

def _has_z(*pts):
    return all(p is not None and p.get('z') is not None for p in pts)


def _mid3(lm, a, b):
    pa, pb = lm.get(a), lm.get(b)
    if not _has_z(pa, pb):
        return None
    return ((pa['x'] + pb['x']) / 2, (pa['y'] + pb['y']) / 2, (pa['z'] + pb['z']) / 2)


def _plane_tilt_deg(points):
    """Angle (deg, 0-90) between vertical (y) and the normal of the best-fit
    plane through a set of 3D points -- 0 = the wrist arc lies in a horizontal
    plane, 90 = a vertical swing plane. Covariance smallest-eigenvector normal."""
    if len(points) < 6:
        return None
    try:
        import numpy as np
    except ImportError:
        return None
    p = np.asarray(points, dtype=float)
    p = p - p.mean(axis=0)
    # smallest-eigenvector of the 3x3 covariance = plane normal
    _w, v = np.linalg.eigh(p.T @ p)
    n = v[:, 0]
    tilt = math.degrees(math.acos(min(1.0, abs(float(n[1])) / (float(np.linalg.norm(n)) or 1e-9))))
    return tilt


def axis_values(traj, racket_frames=None, metric_z=False):
    """Scalar biomechanical features for one trajectory. None where not
    computable. Right-handed convention (pros are normalised RH; LH amateur
    queries are mirrored at cache time)."""
    import phase_breakdown as pb
    ax = {}
    if racket_frames:
        rf = racket_body_features(racket_frames)
        if rf:
            ax['racket_body_dist'] = rf['mean']
            ax['racket_body_range'] = rf['range']
            ax['racket_path_ratio'] = rf['path_ratio']
    c = _pt_at(traj, 0.0)
    sh = _mid(c, 'left_shoulder', 'right_shoulder')
    hip = _mid(c, 'left_hip', 'right_hip')
    rw = c.get('right_wrist')
    # contact: wrist height relative to shoulder line (neg = above shoulders)
    if rw and sh:
        ax['contact_wrist_height'] = rw['y'] - sh[1]
    # contact: wrist lateral offset from body centre
    if rw and hip:
        ax['contact_wrist_lateral'] = rw['x'] - hip[0]
    # contact: right elbow extension angle
    ea = _angle(c, 'right_shoulder', 'right_elbow', 'right_wrist')
    if ea is not None:
        ax['contact_elbow_angle'] = ea
    # backswing depth: how far behind body centre the wrist gets pre-contact
    bw = _win(traj, -0.6, -0.15)
    if bw and hip:
        xs = [p['landmarks']['right_wrist']['x'] - hip[0]
              for p in bw if p['landmarks'].get('right_wrist')]
        if xs:
            ax['backswing_depth'] = max(xs)          # RH: racket goes to +x behind
    # follow-through: wrist height + cross-body at +0.4..+1.0s
    fw = _win(traj, 0.4, 1.0)
    if fw and sh:
        hs = [p['landmarks']['right_wrist']['y'] - sh[1]
              for p in fw if p['landmarks'].get('right_wrist')]
        if hs:
            ax['follow_through_height'] = min(hs)    # most-raised point
    # body rotation range (existing, blends z when available)
    rr = pb.rotation_range(traj)
    if rr is not None:
        ax['rotation_range'] = rr
    # wrist path length (total) / net displacement -- swing "looseness"
    pts = [p['landmarks'].get('right_wrist') for p in traj]
    pts = [q for q in pts if q]
    if len(pts) >= 4:
        path = sum(math.hypot(pts[i]['x'] - pts[i - 1]['x'], pts[i]['y'] - pts[i - 1]['y'])
                   for i in range(1, len(pts)))
        net = math.hypot(pts[-1]['x'] - pts[0]['x'], pts[-1]['y'] - pts[0]['y'])
        ax['wrist_path_ratio'] = path / net if net > 0.05 else None
    # tempo: fraction of the window spent in backswing (wrist-speed peak position)
    sp = []
    for i in range(1, len(pts)):
        sp.append(math.hypot(pts[i]['x'] - pts[i - 1]['x'], pts[i]['y'] - pts[i - 1]['y']))
    if sp:
        peak_i = max(range(len(sp)), key=lambda i: sp[i])
        ax['tempo_peak_frac'] = peak_i / len(sp)

    # ── depth-aware axes (metric-z only; see helpers above) ──────────────────
    if metric_z:
        # 1. swing-plane tilt: plane fit to the wrist arc through contact.
        pw = [(p['landmarks']['right_wrist']['x'], p['landmarks']['right_wrist']['y'],
               p['landmarks']['right_wrist']['z'])
              for p in _win(traj, -0.30, 0.30)
              if _has_z(p['landmarks'].get('right_wrist'))]
        tilt = _plane_tilt_deg(pw)
        if tilt is not None:
            ax['swing_plane_tilt'] = tilt
        # 2. forward weight transfer: pelvis depth travel, contact vs backswing.
        hip_c = _mid3(c, 'left_hip', 'right_hip')
        bw3 = [h for p in _win(traj, -0.60, -0.30) if (h := _mid3(p['landmarks'], 'left_hip', 'right_hip'))]
        if hip_c and bw3:
            ax['forward_weight_transfer'] = -(hip_c[2] - sum(h[2] for h in bw3) / len(bw3))
        # 3. contact depth ahead: lead hip minus wrist in depth at contact.
        lh, rwz = c.get('left_hip'), c.get('right_wrist')
        if _has_z(lh, rwz):
            ax['contact_depth_ahead'] = lh['z'] - rwz['z']
        # 4. 3D coil (X-factor) at top of backswing.
        bwin = _win(traj, -0.6, -0.1)
        if bwin:
            def _sep(p):
                l = p['landmarks']
                if not _has_z(l.get('left_shoulder'), l.get('right_shoulder'),
                              l.get('left_hip'), l.get('right_hip')):
                    return None
                return abs(l['right_shoulder']['z'] - l['left_shoulder']['z']) - \
                    abs(l['right_hip']['z'] - l['left_hip']['z'])
            seps = [(s, p) for p in bwin if (s := _sep(p)) is not None]
            if seps:
                ax['coil_depth_xfactor'] = max(seps, key=lambda sp: abs(sp[0]))[0]
        # 5. wrist-elbow depth lag just before contact.
        lag = [p['landmarks']['right_wrist']['z'] - p['landmarks']['right_elbow']['z']
               for p in _win(traj, -0.12, -0.02)
               if _has_z(p['landmarks'].get('right_wrist'), p['landmarks'].get('right_elbow'))]
        if lag:
            ax['wrist_elbow_depth_lag'] = sum(lag) / len(lag)

    return {k: v for k, v in ax.items() if v is not None}


_RACKET_AXIS_KEY = {'racket_body_dist': 'mean', 'racket_body_range': 'range',
                    'racket_path_ratio': 'path_ratio'}


def _pro_dists_by_view(entries, shot, reviewed, cache_recs):
    """{view: {axis: sorted_vals}} for view in ('back', 'front', '_pooled').
    Sign-ambiguous axes (backswing_depth, contact_wrist_lateral) only make
    sense within one camera view -- mixing views makes the pro 'centre'
    meaningless. Racket axes come from entry['racket_body_features'] (the
    enrich pass); if that hasn't run, pooled from the pro-bucket eval clips."""
    B = {'back': defaultdict(list), 'front': defaultdict(list), '_pooled': defaultdict(list)}

    def targets(vd):
        return [B['_pooled']] + ([B[vd]] if vd in ('back', 'front') else [])

    for e in eligible_match_candidates(entries, shot, reviewed):
        tg = targets(e.get('view_direction'))
        for k, v in axis_values(e['trajectory'], metric_z=_entry_metric_z(e)).items():
            for t in tg:
                t[k].append(v)
        rf = e.get('racket_body_features')
        if rf:
            for ax_k, feat_k in _RACKET_AXIS_KEY.items():
                if rf.get(feat_k) is not None:
                    for t in tg:
                        t[ax_k].append(rf[feat_k])

    if not any('racket_body_dist' in B[v] for v in B):
        for r in cache_recs:
            if r['bucket'] in ('in_db', 'held_out') and r['shot_type'] == shot and r.get('racket_frames'):
                av = axis_values(r['user_traj'], r['racket_frames'], metric_z=_rec_metric_z(r))
                tg = targets(r.get('view'))
                for ax_k in _RACKET_AXIS_KEY:
                    if ax_k in av:
                        for t in tg:
                            t[ax_k].append(av[ax_k])

    return {v: {k: sorted(vs) for k, vs in d.items() if len(vs) >= 15} for v, d in B.items()}


def _axis_prolikeness(val, pro_dists, view, axis):
    """100 at the pro median for this axis (view-specific dist if it has ≥15
    samples, else pooled), decaying by ~1 IQR."""
    d = pro_dists.get(view, {}) if view in ('back', 'front') else {}
    vs = d.get(axis) or pro_dists['_pooled'].get(axis)
    if not vs:
        return None
    med = _pct(vs, 0.5)
    iqr = (_pct(vs, 0.75) - _pct(vs, 0.25)) or 1e-6
    return 100 * math.exp(-abs(val - med) / iqr)


def do_axes(args):
    recs = _load_cache()
    with open(DB_PATH) as f:
        entries = json.load(f)['entries']
    reviewed = clip_review_log.get_label_reviewed_ids()
    by_bucket = defaultdict(list)
    for r in recs:
        by_bucket[r['bucket']].append(r)

    for shot in ('forehand', 'backhand', 'serve'):
        n_pro = len(eligible_match_candidates(entries, shot, reviewed))
        pro_dists = _pro_dists_by_view(entries, shot, reviewed, recs)
        all_axes = sorted(pro_dists['_pooled'])

        rows = {b: defaultdict(list) for b in ('in_db', 'held_out', 'amateur')}
        for b in rows:
            for r in by_bucket.get(b, []):
                if r['shot_type'] != shot:
                    continue
                av = axis_values(r['user_traj'], r.get('racket_frames'), metric_z=_rec_metric_z(r))
                for k, v in av.items():
                    if k in all_axes:
                        pl = _axis_prolikeness(v, pro_dists, r.get('view'), k)
                        if pl is not None:
                            rows[b][k].append(pl)

        vc = {k: len(pro_dists['back'].get(k, [])) for k in all_axes}
        print(f'\n=== {shot} (pros n={n_pro}) : per-axis pro-likeness (100 = at pro median, view-conditioned) ===')
        print(f'{"axis":24s} {"in_db":>8s} {"held_out":>9s} {"amateur":>8s}   sep   back-n')
        for k in all_axes:
            m = {b: (_pct(sorted(rows[b][k]), 0.5) if rows[b][k] else None) for b in rows}
            sep = f'{m["held_out"] - m["amateur"]:+.0f}' if m['held_out'] is not None and m['amateur'] is not None else ''
            cells = ' '.join(f'{m[b]:>8.0f}' if m[b] is not None else f'{"--":>8s}'
                             for b in ('in_db', 'held_out', 'amateur'))
            print(f'{k:24s} {cells}   {sep:>4s}   {vc[k]}')
        print('sep = heldout_median - amateur_median pro-likeness. Positive & large = discriminative.')


# ── rubric phase : combined curated-axis score per bucket ────────────────────
#
# Curated from `axes` output: keep axes where held-out pro scores clearly MORE
# pro-like than amateur. Weights ~ proportional to measured separation. An axis
# with no pro distribution (racket_* before the enrich pass runs, or view-
# conditioned dist < 15) is dropped automatically at scoring time.
#
# Re-curated 2026-09-08 from the view-conditioned `axes` run (84-clip cache,
# no racket enrich yet). Kept: sep >= +7. Dropped: forehand/backhand
# backswing_depth & contact_elbow_angle where they invert, rotation_range on
# groundstrokes (flat). racket_* on spec (weight small) -- re-curate once the
# enrich pass + 60-held-out cache land. Weights ~ sep magnitude.

# Re-curated 2026-09-09 from the post-stride-1 + yaw (metric-3D) `axes` run
# (648-entry DB, 67-held-out / 45-amateur v3 cache). Rule: keep sep >= +7,
# weight ~ sep/10. Dropped where they now invert: forehand contact_elbow_angle
# (-3) & wrist_path_ratio (+1); serve follow_through_height (-35),
# contact_wrist_lateral (-21), tempo_peak_frac (-6), rotation_range (-1).
# Added the metric-3D depth axes that landed strong: forehand
# contact_depth_ahead (+46, the top forehand discriminator) & wrist_elbow_depth_lag
# (+32); backhand coil_depth_xfactor (+26) & forward_weight_transfer (+15).
# Serve depth axes EXCLUDED -- back-n=0 (no yaw-rotated serve pros => image-z
# fallback, unreliable); serve is left with only 3 solid axes, itself a finding.
CURATED_AXES = {
    'forehand': {'contact_depth_ahead': 4.5, 'wrist_elbow_depth_lag': 3.2,
                 'follow_through_height': 3.0, 'racket_body_dist': 2.1,
                 'racket_path_ratio': 1.8, 'contact_wrist_height': 1.2,
                 'contact_wrist_lateral': 1.1, 'tempo_peak_frac': 0.9,
                 'racket_body_range': 0.7},
    'backhand': {'tempo_peak_frac': 6.2, 'racket_body_range': 5.1, 'backswing_depth': 3.7,
                 'coil_depth_xfactor': 2.6, 'contact_wrist_lateral': 2.5,
                 'contact_elbow_angle': 2.2, 'racket_body_dist': 1.6,
                 'forward_weight_transfer': 1.5, 'contact_wrist_height': 1.4,
                 'rotation_range': 0.8},
    'serve':    {'contact_elbow_angle': 5.1, 'racket_body_range': 2.2,
                 'wrist_path_ratio': 1.8},
}


def do_rubric(args):
    recs = _load_cache()
    with open(DB_PATH) as f:
        entries = json.load(f)['entries']
    reviewed = clip_review_log.get_label_reviewed_ids()
    by_bucket = defaultdict(list)
    for r in recs:
        by_bucket[r['bucket']].append(r)

    allscores = defaultdict(list)
    for shot, weights in CURATED_AXES.items():
        pro_dists = _pro_dists_by_view(entries, shot, reviewed, recs)
        avail = set(pro_dists['_pooled'])
        wk = {k: w for k, w in weights.items() if k in avail}
        print(f'\n=== {shot} rubric : axes {list(wk)} ===')
        print(f'{"bucket":10s} {"n":>4s} {"p25":>7s} {"median":>7s} {"p75":>7s}')
        for b in ('in_db', 'held_out', 'amateur'):
            scs = []
            for r in by_bucket.get(b, []):
                if r['shot_type'] != shot:
                    continue
                av = axis_values(r['user_traj'], r.get('racket_frames'), metric_z=_rec_metric_z(r))
                num = den = 0.0
                for k, w in wk.items():
                    if k in av:
                        pl = _axis_prolikeness(av[k], pro_dists, r.get('view'), k)
                        if pl is not None:
                            num += w * pl
                            den += w
                if den:
                    scs.append(num / den)
            allscores[b] += [(shot, s) for s in scs]
            s = _summary(scs)
            if s['n']:
                print(f'{b:10s} {s["n"]:>4d} {s["p25"]:>7.1f} {s["median"]:>7.1f} {s["p75"]:>7.1f}')

    print('\n=== combined (all shot types) ===')
    print(f'{"bucket":10s} {"n":>4s} {"p25":>7s} {"median":>7s} {"p75":>7s}')
    for b in ('in_db', 'held_out', 'amateur'):
        s = _summary([sc for _, sc in allscores[b]])
        if s['n']:
            print(f'{b:10s} {s["n"]:>4d} {s["p25"]:>7.1f} {s["median"]:>7.1f} {s["p75"]:>7.1f}')
    ho = sorted(sc for _, sc in allscores['held_out'])
    am = sorted(sc for _, sc in allscores['amateur'])
    if ho and am:
        print(f'\nheld_out median {_pct(ho,0.5):.1f} vs amateur {_pct(am,0.5):.1f}  '
              f'-> gap {_pct(ho,0.5)-_pct(am,0.5):+.1f} pts (DTW v0 gap was ~+3 on a 0-100 scale)')


# ── decomp phase ─────────────────────────────────────────────────────────────

def do_decomp(args):
    recs = [r for r in _load_cache() if r['bucket'] == 'in_db' and r.get('self_id')]
    with open(DB_PATH) as f:
        traj_by_id = {e['id']: e['trajectory'] for e in json.load(f)['entries']}
    print(f'in_db self-comparison (n={len(recs)}) -- how close is a clip to its OWN stored entry?\n')
    print(f'{"id":24s} {"as-is":>8s} {"best±0.12s":>11s} {"offset":>7s}')
    raw, shifted = [], []
    for r in recs:
        pt = traj_by_id.get(r['self_id'])
        if not pt:
            continue
        base = dtw(r['user_traj'], pt, _fd_mean)
        best, boff = base, 0.0
        for off in [i * 0.02 for i in range(-6, 7)]:
            shifted_traj = [{'t': p['t'] + off, 'landmarks': p['landmarks']} for p in r['user_traj']]
            d = dtw(shifted_traj, pt, _fd_mean)
            if d < best:
                best, boff = d, off
        raw.append(base)
        shifted.append(best)
        print(f'{r["self_id"]:24s} {base:>8.3f} {best:>11.3f} {boff:>+7.2f}')
    if raw:
        print(f'\nmedian as-is {_pct(sorted(raw),0.5):.3f}  ->  after best time-shift {_pct(sorted(shifted),0.5):.3f}')
        print('big drop = contact-anchor misalignment is the main error; small drop = '
              'pipeline normalisation drift (pose extraction/scale/roll), not timing.')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('cache'); c.add_argument('--in-db', type=int, default=21)
    c.add_argument('--held-out', type=int, default=60); c.add_argument('--amateur', type=int, default=45)
    e = sub.add_parser('eval'); e.add_argument('--metrics', default=None, help='comma list; default all')
    e.add_argument('--angle-window', type=float, default=0, help='re-filter candidate pool to ±N° of the user angle (0 = keep cached ±20°)')
    sub.add_parser('decomp')
    sub.add_parser('axes')
    sub.add_parser('rubric')
    args = ap.parse_args()
    {'cache': do_cache, 'eval': do_eval, 'decomp': do_decomp,
     'axes': do_axes, 'rubric': do_rubric}[args.cmd](args)
