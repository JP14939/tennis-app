"""
Go / no-go for homography-based SIGNED camera azimuth from the 4 net keypoints.

The current camera angle is `degrees(acos(net_width / 0.80))` -- unsigned, so a
camera 30 deg left of the court axis and one 30 deg right produce the same
number even though the swing projects as a mirror image. The fix is to recover
the real camera pose from the net (a known-size rectangle) via solvePnP and read
a signed azimuth off it. That only works if the corner detections are precise
enough. This script measures whether they are.

  net_pose_from_corners(corners_px, img_w, img_h, focal_guess)
      -> {azimuth_deg (<0 = camera left of centre), elevation_deg, distance_m,
          cam_xyz, reproj_err_px}

  Part A  empirical -- GT-corner azimuth vs model-corner azimuth on the labeled
          test set; also the current acos proxy for reference. Needs
          net_keypoint_testset_v1 labels + an eval_net_keypoints results file.
  Part B  Monte-Carlo -- project the net from known camera poses, add Gaussian
          corner noise sigma in {2,5,10,20} px, measure azimuth error + sign-flip
          rate vs sigma. No data dependence.
  Part C  focal ablation -- Part B best case with focal_guess swept +-50%, to
          bound how much the unknown phone intrinsic alone corrupts azimuth.

Verdict (thresholds overridable via CLI):
  GREEN  median |d azimuth| <= 5 deg AND sign-agreement >= 95% (high-conf slice)
  AMBER  sign-agreement 85-95%   -> azimuth only when all 4 corners conf >= 0.8
  RED    sign-agreement < 85% OR median |d azimuth| > 10 deg  -> keep unsigned,
         fix the sign heuristically elsewhere

Usage
  python net_geometry_sensitivity.py --model-run yolo_pose_run_v4
  python net_geometry_sensitivity.py --parts BC          # synthetic only
  python net_geometry_sensitivity.py --model-run yolo_pose_run_v4 --focal-fracs 0.7,1.0,1.5
"""
import argparse
import json
import math
import os
import statistics as stats
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', '..', 'data'))
NET_DIR = os.path.join(DATA, '10_net_detection')
TESTSET_DIR = os.path.join(NET_DIR, 'net_keypoint_testset_v1')
LABELS_PATH = os.path.join(TESTSET_DIR, 'net_keypoint_testset_v1_labels.json')
EVAL_DIR = os.path.join(NET_DIR, 'net_keypoint_eval')
OUT_DIR = os.path.join(NET_DIR, 'net_keypoint_eval')

POINTS = ['net_top_left', 'net_top_right', 'left_post_base', 'right_post_base']

# Net rectangle in metres: doubles net posts 12.8 m apart, 1.07 m high at posts.
# X right (+), Y up (+), Z out of the net plane toward the court/camera.
NET_OBJP = np.array([
    [-6.40, 1.07, 0.0],   # net_top_left
    [+6.40, 1.07, 0.0],   # net_top_right
    [-6.40, 0.00, 0.0],   # left_post_base
    [+6.40, 0.00, 0.0],   # right_post_base
], dtype=np.float64)

FULL_NET_FRACTION = 0.80  # mirrors infer_angle.FULL_NET_FRACTION


def _K(focal, w, h):
    return np.array([[focal, 0, w / 2.0], [0, focal, h / 2.0], [0, 0, 1]], dtype=np.float64)


def net_pose_from_corners(corners_px, img_w, img_h, focal_guess):
    """corners_px: dict name -> (x,y) with all 4 POINTS present. Returns pose dict or None."""
    import cv2
    imgp = np.array([corners_px[p] for p in POINTS], dtype=np.float64)
    K = _K(focal_guess, img_w, img_h)
    dist = np.zeros(5)
    try:
        n_sol, rvecs, tvecs, reproj = cv2.solvePnPGeneric(
            NET_OBJP, imgp, K, dist, flags=cv2.SOLVEPNP_IPPE)
    except cv2.error:
        return None
    if not n_sol:
        return None

    best = None
    for rvec, tvec in zip(rvecs, tvecs):
        R, _ = cv2.Rodrigues(rvec)
        cam = (-R.T @ tvec).ravel()          # camera centre in net coords
        # reprojection error
        proj, _ = cv2.projectPoints(NET_OBJP, rvec, tvec, K, dist)
        err = float(np.mean(np.linalg.norm(proj.reshape(-1, 2) - imgp, axis=1)))
        # camera must be on the +Z side of the net and above the ground
        if cam[2] <= 0:
            err += 1e6
        cand = (err, cam)
        if best is None or cand[0] < best[0]:
            best = cand

    err, cam = best
    cam_x, cam_y, cam_z = float(cam[0]), float(cam[1]), float(cam[2])
    azimuth = math.degrees(math.atan2(cam_x, cam_z))      # <0 => camera left of net centre
    ground = math.hypot(cam_x, cam_z)
    elevation = math.degrees(math.atan2(cam_y, ground)) if ground > 1e-6 else 90.0
    return {
        'azimuth_deg': round(azimuth, 2),
        'elevation_deg': round(elevation, 2),
        'distance_m': round(math.sqrt(cam_x ** 2 + cam_y ** 2 + cam_z ** 2), 2),
        'cam_xyz': [round(cam_x, 2), round(cam_y, 2), round(cam_z, 2)],
        'reproj_err_px': round(err, 2),
        'focal_guess': focal_guess,
    }


def project_net(azimuth_deg, elevation_deg, distance_m, focal, w, h):
    """Place a camera at (azimuth, elevation, distance) looking at the net centre;
    return the 4 projected corner pixel coords."""
    import cv2
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    cam = np.array([
        distance_m * math.cos(el) * math.sin(az),
        distance_m * math.sin(el),
        distance_m * math.cos(el) * math.cos(az),
    ])
    fwd = -cam / np.linalg.norm(cam)
    world_up = np.array([0.0, 1.0, 0.0])
    right = np.cross(fwd, world_up); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    R = np.vstack([right, -up, fwd])            # world -> camera
    rvec, _ = cv2.Rodrigues(R)
    tvec = (-R @ cam).reshape(3, 1)
    proj, _ = cv2.projectPoints(NET_OBJP, rvec, tvec, _K(focal, w, h), np.zeros(5))
    return {p: tuple(proj[i][0]) for i, p in enumerate(POINTS)}


def acos_proxy_angle(corners_px, img_w):
    tl, tr = corners_px['net_top_left'], corners_px['net_top_right']
    frac = abs(tr[0] - tl[0]) / img_w
    return math.degrees(math.acos(min(frac / FULL_NET_FRACTION, 1.0)))


# ---------------- Part A ----------------

def part_a(model_run, focal_fracs, out):
    def w(s=''):
        out.append(s); print(s)
    w('\n========== PART A -- empirical (labeled test set) ==========')
    results_path = os.path.join(EVAL_DIR, f'results_{model_run}.jsonl')
    if not (os.path.exists(LABELS_PATH) and os.path.exists(results_path)):
        w(f'  SKIP: need {LABELS_PATH} and {results_path} '
          f'(run label_net_keypoints.py + eval_net_keypoints.py --model-run {model_run})')
        return None

    with open(LABELS_PATH) as f:
        gt = {r['frame_file']: r for r in json.load(f)['labels']}
    preds = {}
    with open(results_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    r = json.loads(line); preds[r['frame_file']] = r
                except (json.JSONDecodeError, KeyError):
                    pass

    verdict_rows = {}
    for frac in focal_fracs:
        d_az, sign_ok, d_proxy = [], 0, []
        n = 0
        hi_d_az, hi_sign_ok, hi_n = [], 0, 0
        for ff, g in gt.items():
            if not g.get('usable'):
                continue
            gk = g['keypoints']
            if any(gk.get(p) is None for p in POINTS):
                continue
            pr = preds.get(ff)
            if not pr or 'errors_px' not in pr:
                continue
            # reconstruct predicted corners from GT + error is not possible;
            # eval stores pred implicitly via errors -- instead re-read pred_conf
            # presence and require all 4 returned
            if not pr.get('all4'):
                continue
            w_img, h_img = pr.get('img_w'), pr.get('img_h')
            focal = frac * w_img
            gt_c = {p: tuple(gk[p]) for p in POINTS}
            # predicted corners: eval didn't persist them; approximate from GT and
            # per-point error direction is unknown -> we need actual preds.
            pred_c = pr.get('pred_xy')
            if pred_c is None:
                # older results file without pred_xy: skip, ask for re-run
                continue
            pred_c = {p: tuple(pred_c[p]) for p in POINTS}

            gpose = net_pose_from_corners(gt_c, w_img, h_img, focal)
            ppose = net_pose_from_corners(pred_c, w_img, h_img, focal)
            if not gpose or not ppose:
                continue
            n += 1
            da = abs(gpose['azimuth_deg'] - ppose['azimuth_deg'])
            d_az.append(da)
            sgn = (gpose['azimuth_deg'] >= 0) == (ppose['azimuth_deg'] >= 0)
            sign_ok += sgn
            d_proxy.append(abs(acos_proxy_angle(gt_c, w_img) - acos_proxy_angle(pred_c, w_img)))
            conf = pr.get('pred_conf', {})
            if conf and all((conf.get(p) or 0) >= 0.8 for p in POINTS):
                hi_n += 1; hi_d_az.append(da); hi_sign_ok += sgn

        if n == 0:
            w(f'  focal={frac:.2f}*w : no usable frames with 4 GT + 4 pred corners + pred_xy persisted.')
            w('    (re-run eval_net_keypoints.py after adding pred_xy persistence, or label more frames)')
            continue
        med = stats.median(d_az)
        sa = sign_ok / n
        w(f'  focal={frac:.2f}*w  n={n}')
        w(f'    |d azimuth|  median={med:.2f}  p90={sorted(d_az)[min(n-1,int(.9*n))]:.2f}  max={max(d_az):.2f}')
        w(f'    sign-agreement (all)      {sa:.1%}')
        if hi_n:
            w(f'    sign-agreement (conf>=.8) {hi_sign_ok/hi_n:.1%}   n={hi_n}   '
              f'median|d az|={stats.median(hi_d_az):.2f}')
        w(f'    acos-proxy |d angle| median={stats.median(d_proxy):.2f} (corner error only, not the 0.80 constant)')
        verdict_rows[frac] = {'n': n, 'median_d_az': med, 'sign_agree': sa,
                              'hi_sign_agree': (hi_sign_ok / hi_n) if hi_n else None,
                              'hi_n': hi_n}
    return verdict_rows


# ---------------- Part B ----------------

def part_b(sigmas, out, focal_frac=1.0, draws=500, w_img=1920, h_img=1080):
    def w(s=''):
        out.append(s); print(s)
    w('\n========== PART B -- Monte-Carlo corner noise ==========')
    w(f'  net projected from known poses, focal={focal_frac:.2f}*w, {draws} draws/cell')
    rng = np.random.default_rng(0)
    true_azes = [-40, -25, -12, -5, 0, 5, 12, 25, 40]
    distance, elevation = 12.0, 8.0
    focal = focal_frac * w_img
    table = {}
    w(f'  {"true_az":>8} | ' + ' | '.join(f'sig={s:>2}' for s in sigmas))
    for taz in true_azes:
        clean = project_net(taz, elevation, distance, focal, w_img, h_img)
        cells = []
        for sg in sigmas:
            errs, flips = [], 0
            for _ in range(draws):
                noisy = {p: (clean[p][0] + rng.normal(0, sg), clean[p][1] + rng.normal(0, sg))
                         for p in POINTS}
                pose = net_pose_from_corners(noisy, w_img, h_img, focal)
                if not pose:
                    continue
                errs.append(abs(pose['azimuth_deg'] - taz))
                if (pose['azimuth_deg'] >= 0) != (taz >= 0):
                    flips += 1
            if errs:
                med = stats.median(errs)
                p90 = sorted(errs)[min(len(errs) - 1, int(0.9 * len(errs)))]
                cells.append(f'{med:4.1f}/{p90:4.1f}')
                table[(taz, sg)] = {'median': med, 'p90': p90, 'flip_rate': flips / draws}
            else:
                cells.append('  -  ')
        w(f'  {taz:>8} | ' + ' | '.join(cells))
    w('  cells = median / p90 azimuth error (deg)')
    # threshold: smallest sigma at which p90 stays < 10 for near-frontal poses
    w('\n  sign-flip rate near 0 deg (|true_az| <= 5):')
    for sg in sigmas:
        fr = [table[(t, sg)]['flip_rate'] for t in (-5, 0, 5) if (t, sg) in table]
        if fr:
            w(f'    sigma={sg:>2}px : {stats.mean(fr):.1%}')
    return table


# ---------------- Part C ----------------

def part_c(out, w_img=1920, h_img=1080):
    def w(s=''):
        out.append(s); print(s)
    w('\n========== PART C -- focal-length ablation ==========')
    true_focal = 1.0 * w_img
    distance, elevation = 12.0, 8.0
    w('  net projected with focal = 1.0*w ; solved with a WRONG focal guess:')
    w(f'  {"true_az":>8} | ' + ' | '.join(f'{g:+.0%}' for g in (-0.5, -0.25, 0.0, 0.25, 0.5)))
    for taz in (-30, -12, 0, 12, 30):
        clean = project_net(taz, elevation, distance, true_focal, w_img, h_img)
        cells = []
        for g in (-0.5, -0.25, 0.0, 0.25, 0.5):
            pose = net_pose_from_corners(clean, w_img, h_img, true_focal * (1 + g))
            cells.append(f'{pose["azimuth_deg"] - taz:+5.1f}' if pose else '  -  ')
        w(f'  {taz:>8} | ' + ' | '.join(cells))
    w('  cells = azimuth error (deg) from focal mismatch alone, corners perfect')


# ---------------- verdict ----------------

def verdict(part_a_rows, green_daz, amber_sign, green_sign, out):
    def w(s=''):
        out.append(s); print(s)
    w('\n========== VERDICT ==========')
    if not part_a_rows:
        w('  INCONCLUSIVE -- Part A did not run. Verdict needs the labeled test set + eval results.')
        w('  Use Part B/C to set the corner-precision target, then re-run with --model-run.')
        return 'INCONCLUSIVE'
    best = min(part_a_rows.values(),
              key=lambda r: (-(r['hi_sign_agree'] or r['sign_agree']), r['median_d_az']))
    sa = best['hi_sign_agree'] if best['hi_sign_agree'] is not None else best['sign_agree']
    daz = best['median_d_az']
    if sa >= green_sign and daz <= green_daz:
        v = 'GREEN'
    elif sa >= amber_sign:
        v = 'AMBER'
    else:
        v = 'RED'
    w(f'  best focal slice: sign-agreement={sa:.1%}  median|d azimuth|={daz:.2f}')
    w(f'  --> {v}')
    w({'GREEN': '  Build net_azimuth_signed_deg into infer_angle (plan section 6.2).',
       'AMBER': '  Emit signed azimuth ONLY when all 4 corners conf>=0.8; keep unsigned fallback.',
       'RED':   '  Do NOT build homography azimuth. Keep the acos proxy; fix the abs() sign\n'
                '  heuristically (player body-facing / court-side, or view_direction+player-x agreement).',
       'INCONCLUSIVE': ''}[v])
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-run', default=None)
    ap.add_argument('--parts', default='ABC', help='subset of A,B,C to run')
    ap.add_argument('--focal-fracs', default='0.7,1.0,1.5')
    ap.add_argument('--sigmas', default='2,5,10,20')
    ap.add_argument('--green-daz', type=float, default=5.0)
    ap.add_argument('--amber-sign', type=float, default=0.85)
    ap.add_argument('--green-sign', type=float, default=0.95)
    args = ap.parse_args()

    focal_fracs = [float(x) for x in args.focal_fracs.split(',')]
    sigmas = [int(x) for x in args.sigmas.split(',')]
    out = []
    part_a_rows = None

    if 'B' in args.parts:
        part_b(sigmas, out)
    if 'C' in args.parts:
        part_c(out)
    if 'A' in args.parts:
        if not args.model_run:
            print('Part A needs --model-run; skipping.', file=sys.stderr)
        else:
            part_a_rows = part_a(args.model_run, focal_fracs, out)

    if 'A' in args.parts:
        v = verdict(part_a_rows, args.green_daz, args.amber_sign, args.green_sign, out)
    else:
        v = 'not-run'

    os.makedirs(OUT_DIR, exist_ok=True)
    tag = args.model_run or 'synthetic'
    with open(os.path.join(OUT_DIR, f'sensitivity_{tag}.txt'), 'w') as f:
        f.write('\n'.join(out) + '\n')
    with open(os.path.join(OUT_DIR, f'sensitivity_{tag}.json'), 'w') as f:
        json.dump({'verdict': v, 'part_a': part_a_rows}, f, indent=2)


if __name__ == '__main__':
    main()
