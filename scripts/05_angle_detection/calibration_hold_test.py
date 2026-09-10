"""
Does a DELIBERATE square-and-still hold let us read the camera->net angle?

Background: pose-based yaw normalization was shelved 2026-09-09
(project_viewpoint_normalization_dead) because on Jack's self-fed practice
footage facing_azimuth() had ~0 correlation with the real camera angle
(Spearman -0.09). Two root causes: (1) no still ready-stance to read from
(self-feeding), (2) MediaPipe world-landmark depth noisy at ~10 m.

Jack's proposal (2026-09-10): treat it as a ONCE-PER-SESSION calibration.
The user stands square to the net, dead still, for ~2 s at the start; we
average facing_azimuth over the whole hold (30-60 frames, which beats down
the depth noise) and reuse that transform for every swing in the session.

This script is the gate. It measures, on clips filmed that way, whether the
averaged hold facing tracks the real camera angle. If yes -> the
calibrate-once design is worth building. If it's still scattered even with a
clean hold -> cause (2) is fatal, park it for good.

────────────────────────────────────────────────────────────────────────────
HOW TO FILM  (Jack)
────────────────────────────────────────────────────────────────────────────
6-8 short clips (~4 s each), same spot on court each time, camera on a
tripod/fence at chest height, LANDSCAPE:

  1. Stand on/near the baseline facing the net, square (shoulders parallel
     to the net), arms relaxed at your sides or holding the racket in front.
  2. Hold DEAD STILL for a slow count of 3 (~2-3 s).
  3. (optional) do one forehand, then stop the recording.

Camera positions -- do each one, note the rough angle:
  - behind the centre mark                         ~0
  - ~1.5 m LEFT of centre, still behind baseline    ~-15
  - ~1.5 m RIGHT of centre                          ~+15
  - one back corner (diagonal across)              ~-40  (or +40)
  - the other corner                               ~+40
  - from the sideline, side-on (negative control)  ~85

Put the clips in data/05_angle_detection/calib_hold/clips/ and fill in
data/05_angle_detection/calib_hold_manifest.json (a template is written on
first run). `approx_deg` is SIGNED: negative = camera left of the centre
line as you look at the net, positive = right. 0 = dead centre.

  python calibration_hold_test.py            # extract (cached) + report
  python calibration_hold_test.py --no-net   # skip the net-model comparison
  python calibration_hold_test.py --no-montage
"""
import argparse
import json
import math
import os
import statistics
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ('02_pose_extraction', '05_angle_detection', '06_database_build'):
    sys.path.insert(0, os.path.join(SCRIPTS_DIR, _d))
from extract_poses import extract_poses  # noqa: E402
from trajectory_extraction import build_world_pose_index  # noqa: E402
from viewpoint_normalization import facing_azimuth, usable_yaw, soft_yaw  # noqa: E402

DATA_DIR = os.path.join(SCRIPTS_DIR, '..', 'data')
CALIB_DIR = os.path.join(DATA_DIR, '05_angle_detection', 'calib_hold')
CLIPS_DIR = os.path.join(CALIB_DIR, 'clips')
POSE_DIR = os.path.join(CALIB_DIR, 'poses')
MANIFEST_PATH = os.path.join(DATA_DIR, '05_angle_detection', 'calib_hold_manifest.json')
OUT_DIR = os.path.join(CALIB_DIR, 'validation')
VIZ_DIR = os.path.join(DATA_DIR, 'runtime', 'testing_viz', 'calib_hold')

_TEMPLATE = [
    {"video": "clips/HOLD_center.MOV", "approx_deg": 0, "note": "behind centre mark"},
    {"video": "clips/HOLD_left15.MOV", "approx_deg": -15, "note": "~1.5m left of centre"},
    {"video": "clips/HOLD_right15.MOV", "approx_deg": 15, "note": "~1.5m right of centre"},
    {"video": "clips/HOLD_corner_L.MOV", "approx_deg": -40, "note": "back corner, diagonal"},
    {"video": "clips/HOLD_corner_R.MOV", "approx_deg": 40, "note": "other back corner"},
    {"video": "clips/HOLD_sideline.MOV", "approx_deg": 85, "note": "side-on negative control"},
]

# a "still" frame: max wrist displacement vs the previous kept frame, in
# normalised image units. Hand tremor / breathing is ~<0.004; a step or a
# swing is >>0.02.
STILL_SPEED = 0.010
STILL_MIN_FRAMES = 12


def _ensure_manifest():
    if os.path.exists(MANIFEST_PATH):
        return json.load(open(MANIFEST_PATH))
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    os.makedirs(CLIPS_DIR, exist_ok=True)
    json.dump(_TEMPLATE, open(MANIFEST_PATH, 'w'), indent=1)
    print(f'wrote a template manifest -> {MANIFEST_PATH}')
    print(f'drop the clips in {CLIPS_DIR}/ and edit approx_deg, then re-run.')
    sys.exit(0)


def _poses(video_abs, name):
    os.makedirs(POSE_DIR, exist_ok=True)
    pose_path = os.path.join(POSE_DIR, f'{name}.json')
    if not (os.path.exists(pose_path) and os.path.getmtime(pose_path) >= os.path.getmtime(video_abs)):
        print(f'  extracting poses (stride 1) -> {os.path.basename(pose_path)} ...')
        extract_poses(video_abs, pose_path, sample_every=1)
    return json.load(open(pose_path))


def _wrist_xy(lm_list, name):
    for lm in lm_list or []:
        if lm['name'] == name and lm.get('visibility', 0) > 0.5:
            return lm['x'], lm['y']
    return None


def _still_span(frames):
    """The longest run of consecutive detected frames whose frame-to-frame
    wrist movement stays below STILL_SPEED. Returns a set of frame numbers."""
    det = [f for f in frames if f.get('landmarks')]
    best, cur = [], []
    prev = None
    for f in det:
        lw, rw = _wrist_xy(f['landmarks'], 'left_wrist'), _wrist_xy(f['landmarks'], 'right_wrist')
        moved = 0.0
        if prev:
            for a, b in ((lw, prev[0]), (rw, prev[1])):
                if a and b:
                    moved = max(moved, math.hypot(a[0] - b[0], a[1] - b[1]))
        if prev is None or moved <= STILL_SPEED:
            cur.append(f['frame'])
        else:
            if len(cur) > len(best):
                best = cur
            cur = [f['frame']]
        prev = (lw, rw)
    if len(cur) > len(best):
        best = cur
    return set(best)


def _spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    n = len(xs)
    if n < 2:
        return float('nan')
    rx, ry = rank(xs), rank(ys)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return 1 - 6 * d2 / (n * (n * n - 1))


def _trimmed_mean(xs, frac=0.1):
    s = sorted(xs)
    k = int(len(s) * frac)
    s = s[k:len(s) - k] or s
    return sum(s) / len(s)


def _net_angle(video_abs, mid_frame):
    try:
        from infer_angle import infer_camera_angle
        ang, conf, _ = infer_camera_angle(video_abs, mid_frame)
        return ang, conf
    except Exception as e:  # noqa: BLE001
        return None, f'err: {e}'


def _montage(video_abs, name, world_idx, hold_frames):
    picks = hold_frames[:: max(1, len(hold_frames) // 6)][:6] or hold_frames[:6]
    cap = cv2.VideoCapture(video_abs)
    tiles = []
    for fn in picks:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ok, fr = cap.read()
        if not ok:
            continue
        az = facing_azimuth(world_idx[fn]) if fn in world_idx else None
        h, w = fr.shape[:2]
        t = cv2.resize(fr, (400, int(h * 400 / w)))
        cv2.putText(t, f"az {'--' if az is None else round(az)}", (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        tiles.append(t)
    cap.release()
    if tiles:
        os.makedirs(VIZ_DIR, exist_ok=True)
        hh = tiles[0].shape[0]
        cv2.imwrite(os.path.join(VIZ_DIR, f'{name}.jpg'),
                    cv2.hconcat([cv2.resize(t, (400, hh)) for t in tiles]))


def _verdict(rows):
    ok = [r for r in rows if r['facing_median'] is not None]
    if len(ok) < 4:
        return 'INCONCLUSIVE', 'fewer than 4 clips with a readable hold'
    signed_sp = _spearman([r['approx_deg'] for r in ok], [r['facing_median'] for r in ok])
    mag_sp = _spearman([abs(r['approx_deg']) for r in ok], [abs(r['facing_median']) for r in ok])
    head_on = [r for r in ok if abs(r['approx_deg']) <= 5]
    head_on_bad = [r for r in head_on if abs(r['facing_median']) > 15]
    med_iqr = statistics.median([r['facing_iqr'] for r in ok])
    reasons = [f'Spearman(signed)={signed_sp:+.2f}', f'Spearman(|.|)={mag_sp:+.2f}',
               f'within-hold IQR median={med_iqr:.0f}deg']
    if head_on:
        reasons.append(f'{len(head_on) - len(head_on_bad)}/{len(head_on)} head-on clips read |az|<15')
    if signed_sp >= 0.8 and med_iqr < 15 and not head_on_bad:
        return 'GREEN', '; '.join(reasons) + ' -- build the calibrate-once design'
    if signed_sp >= 0.5 or mag_sp >= 0.6:
        return 'AMBER', '; '.join(reasons) + ' -- partial signal; try a longer hold / tighter square'
    return 'RED', '; '.join(reasons) + ' -- no usable relationship; depth noise is fatal, park it'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-net', action='store_true')
    ap.add_argument('--no-montage', action='store_true')
    args = ap.parse_args()

    manifest = _ensure_manifest()
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []

    for e in manifest:
        vid = e['video'] if os.path.isabs(e['video']) else os.path.join(CALIB_DIR, e['video'])
        name = os.path.splitext(os.path.basename(vid))[0]
        if not os.path.exists(vid):
            print(f'{name}: MISSING {vid} -- skipping')
            continue
        pose = _poses(vid, name)
        fps = pose['fps']
        hold = _still_span(pose['frames'])
        world_idx = build_world_pose_index([f for f in pose['frames'] if f['frame'] in hold])
        azs = [az for fn in sorted(world_idx) if (az := facing_azimuth(world_idx[fn])) is not None]

        row = {'name': name, 'approx_deg': e['approx_deg'], 'note': e.get('note', ''),
               'hold_n': len(hold), 'az_n': len(azs)}
        if azs:
            row['facing_median'] = statistics.median(azs)
            row['facing_trimmed'] = _trimmed_mean(azs)
            row['facing_iqr'] = (statistics.quantiles(azs, n=4)[2] - statistics.quantiles(azs, n=4)[0]
                                 if len(azs) >= 4 else float('nan'))
            row['facing_stdev'] = statistics.pstdev(azs) if len(azs) > 1 else 0.0
            row['usable_yaw'] = usable_yaw(azs)
            row['soft_yaw'] = soft_yaw(azs)
        else:
            row.update(facing_median=None, facing_trimmed=None, facing_iqr=None,
                       facing_stdev=None, usable_yaw=None, soft_yaw=None)

        if not args.no_net and hold:
            mid = sorted(hold)[len(hold) // 2]
            row['net_angle'], row['net_conf'] = _net_angle(vid, mid)

        if not args.no_montage and world_idx:
            try:
                _montage(vid, name, world_idx, sorted(world_idx))
            except Exception as ex:  # noqa: BLE001
                print(f'  {name}: montage failed ({ex})')
        rows.append(row)

    # ── report ──────────────────────────────────────────────────────────────
    print(f'\n=== {len(rows)} calibration holds ===\n')
    hdr = f'{"clip":18} {"true":>5} {"hold_n":>6} {"az_n":>5} {"median":>8} {"trimmed":>8} {"IQR":>6} {"stdev":>6} {"soft_yaw":>9}'
    if not args.no_net:
        hdr += f' {"net_ang":>8} {"net_conf":>8}'
    print(hdr)
    for r in sorted(rows, key=lambda r: r['approx_deg']):
        def f(v, w=8, p=1):
            return f'{v:>{w}.{p}f}' if isinstance(v, (int, float)) and not math.isnan(v) else f'{"--":>{w}}'
        line = (f'{r["name"][:18]:18} {r["approx_deg"]:>5} {r["hold_n"]:>6} {r["az_n"]:>5} '
                f'{f(r["facing_median"])} {f(r["facing_trimmed"])} {f(r["facing_iqr"], 6)} '
                f'{f(r["facing_stdev"], 6)} {f(r["soft_yaw"], 9)}')
        if not args.no_net:
            nc = r.get('net_conf')
            line += f' {f(r.get("net_angle"))} ' + (f'{nc:>8.2f}' if isinstance(nc, (int, float)) else f'{str(nc)[:8]:>8}')
        print(line)

    verdict, why = _verdict(rows)
    print(f'\n  VERDICT: {verdict}')
    print(f'  {why}')
    if not args.no_net:
        ok = [r for r in rows if isinstance(r.get('net_angle'), (int, float))]
        if len(ok) >= 4:
            sp = _spearman([abs(r['approx_deg']) for r in ok], [r['net_angle'] for r in ok])
            print(f'  net-model: Spearman(net_angle, |true_deg|) = {sp:+.2f}  (n={len(ok)})')

    json.dump(rows, open(os.path.join(OUT_DIR, 'summary.json'), 'w'), indent=1, default=str)
    print(f'\n  montages -> {VIZ_DIR}/')
    print(f'  summary  -> {os.path.join(OUT_DIR, "summary.json")}')


if __name__ == '__main__':
    main()
