"""
Phase 2 validation for yaw (camera-azimuth) normalization.

Runs against prep_yaw_calib.py's manifest (the same forehand hit from 6 camera
positions, buckets A..E). No true simultaneous multi-angle capture, so the
"same swing collapses" test is done bucket-to-bucket: the behind-centre (A/B)
swings are the near-canonical reference; yaw normalization should pull the
diagonal (C/D) swings CLOSER to that reference, and the side-on (E) bucket
should be rejected by usable_yaw() rather than mis-corrected.

Checks:
  1. azimuth vs bucket -- monotone, Spearman; per-bucket box table
  2. usable_yaw accept/reject by bucket (expect accept A-D, reject E)
  3. cross-bucket DTW: mean distance {C,D} -> {A,B} reference, raw vs yaw-norm
     (target: >= 20% drop, and C/D-normalised closer to A/B than C/D-raw is)
  4. rubric-axis spread across buckets, raw vs yaw-norm (should shrink)
  5. montage: lead-in frames with the measured lateral axis + azimuth drawn

Writes only under data/05_angle_detection/yaw_calib/ and data/runtime/testing_viz/.

Usage:
  python validate_yaw_normalization.py
  python validate_yaw_normalization.py --no-montage
"""
import argparse
import json
import math
import os
import statistics
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in ('06_database_build', '08_comparison_engine', '17_amateur_eval'):
    sys.path.insert(0, os.path.join(SCRIPTS_DIR, d))
from trajectory_extraction import (  # noqa: E402
    build_pose_index, build_world_pose_index, extract_trajectory_from_index,
)
from trajectory_compare import dtw_distance  # noqa: E402
from compare_swing import KEY_LANDMARKS  # noqa: E402
from viewpoint_normalization import (  # noqa: E402
    facing_azimuth, usable_yaw, YAW_PRE_CONTACT_SEC, YAW_LEADIN_SEC,
)

DATA_DIR = os.path.join(SCRIPTS_DIR, '..', 'data')
CALIB_DIR = os.path.join(DATA_DIR, '05_angle_detection', 'yaw_calib')
MANIFEST_PATH = os.path.join(DATA_DIR, '05_angle_detection', 'yaw_calib_manifest.json')
OUT_DIR = os.path.join(CALIB_DIR, 'validation')
VIZ_DIR = os.path.join(DATA_DIR, 'runtime', 'testing_viz', 'yaw_check')


def _leadin_azimuths(world_frames, contact_frame, fps):
    """(t, azimuth) for the lead-in frames, plus the raw list."""
    pairs = []
    for f in sorted(world_frames):
        t = (f - contact_frame) / fps
        az = facing_azimuth(world_frames[f])
        if az is not None:
            pairs.append((t, az))
    if not pairs:
        return [], []
    cutoff = min(min(t for t, _ in pairs) + YAW_LEADIN_SEC, YAW_PRE_CONTACT_SEC)
    lead = [az for t, az in pairs if t <= cutoff]
    return lead, pairs


_POSE_CACHE = {}


def _load(entry):
    path = os.path.join(CALIB_DIR, entry['pose_cache'])
    if path not in _POSE_CACHE:
        _POSE_CACHE[path] = json.load(open(path))
    pose = _POSE_CACHE[path]
    fps = pose['fps']
    cf = entry['contact_frame']
    # window the multi-swing recording to just this swing (+/- ~2.5 s) before
    # indexing -- otherwise the lead-in scan spans the whole 2.7 min clip.
    lo, hi = cf - int(2.5 * fps), cf + int(2.0 * fps)
    win = [f for f in pose['frames'] if lo <= f['frame'] <= hi]
    pidx = build_pose_index(win)
    widx = build_world_pose_index(win)
    lead_az, _ = _leadin_azimuths(widx, cf, fps)
    yaw = usable_yaw(lead_az)
    raw, _ = extract_trajectory_from_index(pidx, fps, cf, world_pose_index=widx, yaw_deg=None)
    ynorm, meta = extract_trajectory_from_index(pidx, fps, cf, world_pose_index=widx, yaw_deg=yaw)
    return {
        'entry': entry, 'fps': fps, 'pose': pose,
        'lead_az_median': statistics.median(lead_az) if lead_az else None,
        'lead_az_n': len(lead_az),
        'usable_yaw': yaw,
        'raw_traj': raw, 'ynorm_traj': ynorm, 'applied_yaw': meta['yaw_deg'],
    }


def _spearman(xs, ys):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for i, idx in enumerate(s):
            r[idx] = i
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return 1 - 6 * d2 / (n * (n * n - 1)) if n > 1 else float('nan')


def _mean_cross(a_trajs, b_trajs):
    ds = [dtw_distance(a, b, KEY_LANDMARKS)
          for a in a_trajs for b in b_trajs if a and b]
    ds = [d for d in ds if math.isfinite(d)]
    return statistics.mean(ds) if ds else float('nan')


def _montage(entry, pose_cache, fps):
    """6-frame lead-in filmstrip with the per-frame azimuth drawn -- read from
    the cached pose (no re-decode of the whole MOV, just grab those frames)."""
    mov = os.path.join(CALIB_DIR, 'clips', f"{entry['source']}.MOV")
    if not os.path.exists(mov):
        return
    cf = entry['contact_frame']
    wframes = build_world_pose_index(pose_cache['frames'])
    lead_frames = sorted(f for f in wframes
                         if (f - cf) / fps <= YAW_PRE_CONTACT_SEC
                         and (f - cf) / fps >= -(YAW_LEADIN_SEC + 1.2))
    pick = lead_frames[:: max(1, len(lead_frames) // 6)][:6] or lead_frames[:6]
    cap = cv2.VideoCapture(mov)
    tiles = []
    for fnum in pick:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fnum)
        ok, fr = cap.read()
        if not ok:
            continue
        az = facing_azimuth(wframes[fnum])
        h, w = fr.shape[:2]
        small = cv2.resize(fr, (420, int(h * 420 / w)))
        cv2.putText(small, f"az {'--' if az is None else round(az)}", (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        tiles.append(small)
    cap.release()
    if tiles:
        os.makedirs(VIZ_DIR, exist_ok=True)
        cv2.imwrite(os.path.join(VIZ_DIR, f"{entry['swing_group']}.jpg"),
                    cv2.hconcat([cv2.resize(t, (420, tiles[0].shape[0])) for t in tiles]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-montage', action='store_true')
    args = ap.parse_args()

    manifest = json.load(open(MANIFEST_PATH))
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = [_load(e) for e in manifest]

    print(f'\n=== {len(rows)} swings ===')

    # 1. azimuth vs bucket
    print('\n--- 1. lead-in azimuth by bucket ---')
    by_bucket = {}
    for r in rows:
        by_bucket.setdefault(r['entry']['bucket_letter'], []).append(r)
    order = 'ABCDE'
    xs, ys = [], []
    for b in order:
        rs = by_bucket.get(b, [])
        azs = [r['lead_az_median'] for r in rs if r['lead_az_median'] is not None]
        if not azs:
            print(f'  {b}: (no data)')
            continue
        deg = rs[0]['entry']['approx_deg']
        print(f'  {b} (~{deg:>2} deg)  n={len(azs)}  azimuth median={statistics.median(azs):6.1f}  '
              f'range=[{min(azs):6.1f},{max(azs):6.1f}]  |az|={statistics.median([abs(a) for a in azs]):.1f}')
        for a in azs:
            xs.append(deg)
            ys.append(abs(a))
    if len(xs) > 1:
        print(f'  Spearman(|azimuth|, approx_deg) = {_spearman(xs, ys):.3f}   [target >= 0.8]')

    # 2. usable_yaw accept/reject
    print('\n--- 2. usable_yaw verdict by bucket ---')
    for b in order:
        rs = by_bucket.get(b, [])
        acc = sum(1 for r in rs if r['usable_yaw'] is not None)
        vals = [round(r['usable_yaw'], 1) for r in rs if r['usable_yaw'] is not None]
        exp = 'reject' if b == 'E' else 'accept'
        print(f'  {b}: {acc}/{len(rs)} accepted (expect {exp})  applied yaw={vals}')

    # 3. cross-bucket DTW collapse
    print('\n--- 3. cross-bucket DTW: {C,D} vs {A,B} reference ---')
    ref_raw = [r['raw_traj'] for r in rows if r['entry']['bucket_letter'] in 'AB']
    ref_yn = [r['ynorm_traj'] for r in rows if r['entry']['bucket_letter'] in 'AB']
    diag_raw = [r['raw_traj'] for r in rows if r['entry']['bucket_letter'] in 'CD']
    diag_yn = [r['ynorm_traj'] for r in rows if r['entry']['bucket_letter'] in 'CD']
    d_raw = _mean_cross(diag_raw, ref_raw)
    d_yn = _mean_cross(diag_yn, ref_yn)
    print(f'  raw       mean DTW(diag -> ref) = {d_raw:.4f}')
    print(f'  yaw-norm  mean DTW(diag -> ref) = {d_yn:.4f}')
    if math.isfinite(d_raw) and d_raw > 0:
        print(f'  change = {100 * (d_yn - d_raw) / d_raw:+.1f}%   [target <= -20%]')
    # within-reference floor for scale
    print(f'  (within-ref raw DTW floor = {_mean_cross(ref_raw, ref_raw):.4f})')

    # 4. rubric-axis spread
    try:
        from redesign_similarity import axis_values
        print('\n--- 4. rubric-axis spread across buckets (raw vs yaw-norm) ---')
        for label, trajs in (('raw', [r['raw_traj'] for r in rows]),
                             ('yaw-norm', [r['ynorm_traj'] for r in rows])):
            axcols = {}
            for r, t in zip(rows, trajs):
                if not t:
                    continue
                av = axis_values(t, r['entry']['shot_type'])
                for k, v in (av or {}).items():
                    if isinstance(v, (int, float)):
                        axcols.setdefault(k, []).append(v)
            spreads = {k: (max(v) - min(v)) for k, v in axcols.items() if len(v) > 2}
            top = sorted(spreads.items(), key=lambda kv: -kv[1])[:6]
            print(f'  {label}: ' + ', '.join(f'{k}={s:.2f}' for k, s in top))
    except Exception as e:  # noqa: BLE001
        print(f'\n--- 4. rubric-axis spread: skipped ({e}) ---')

    # 5. montage
    if not args.no_montage:
        print('\n--- 5. montages -> data/runtime/testing_viz/yaw_check/ ---')
        for r in rows:
            try:
                _montage(r['entry'], r['pose'], r['fps'])
            except Exception as e:  # noqa: BLE001
                print(f"  {r['entry']['swing_group']}: montage failed ({e})")

    json.dump([{'swing_group': r['entry']['swing_group'],
                'bucket': r['entry']['bucket_letter'],
                'approx_deg': r['entry']['approx_deg'],
                'lead_az_median': r['lead_az_median'],
                'usable_yaw': r['usable_yaw']} for r in rows],
              open(os.path.join(OUT_DIR, 'summary.json'), 'w'), indent=1)
    print(f'\nsummary -> {os.path.join(OUT_DIR, "summary.json")}')


if __name__ == '__main__':
    main()
