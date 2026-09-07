"""
Visual verification for the in-plane camera-roll estimate (net_roll_deg).

For each video it samples several frames, runs the net-keypoint model, and
draws:
  - the detected net-top cord, extended across the full frame width (green)
  - a TRUE-horizontal reference line through the same midpoint (grey)
  - the per-frame roll angle, and the clip's median

so you can eyeball whether the measured tilt matches what you see. Same
"look before you trust the number" discipline as visualize_net_height.py.

Annotated frames + a side-by-side montage per clip are written under
  data/runtime/testing_viz/camera_roll_check/<clip>/

Usage:
  # specific clips
  python review_camera_roll.py "C:\\path\\a.mp4" "C:\\path\\b.mp4"

  # sample the user's recent uploads and/or the pro clips
  python review_camera_roll.py --user-clips 8
  python review_camera_roll.py --pro 6 --seed 1

  # after eyeballing, record a corrected value (writes a JSONL log you can
  # feed back via  compare_swing.py --camera-roll <deg>)
  python review_camera_roll.py "C:\\path\\a.mp4" --log
"""
import argparse
import glob
import json
import os
import random
import sys
import time

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
from infer_angle import (  # noqa: E402
    run_net_keypoint_model, net_roll_deg, usable_roll, extract_frame,
    ROLL_CORRECTION_MIN_DEG, ROLL_CORRECTION_MAX_DEG,
)
from paths import DATA_DIR  # noqa: E402

OUT_ROOT = os.path.join(DATA_DIR, 'runtime', 'testing_viz', 'camera_roll_check')
LOG_PATH = os.path.join(DATA_DIR, 'runtime', 'camera_roll_review_log.jsonl')
N_FRAMES = 6
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _median(xs):
    s = sorted(xs)
    return s[len(s) // 2] if s else None


def annotate_frame(frame, roll, kp):
    h, w = frame.shape[:2]
    vis = frame.copy()

    if 'net_top_left' in kp and 'net_top_right' in kp:
        (lx, ly), (rx, ry) = kp['net_top_left'], kp['net_top_right']
        if lx > rx:
            (lx, ly), (rx, ry) = (rx, ry), (lx, ly)
        lxp, lyp, rxp, ryp = lx * w, ly * h, rx * w, ry * h
        mx, my = (lxp + rxp) / 2, (lyp + ryp) / 2
        # detected net cord, extended full width along its own slope
        if rxp != lxp:
            slope = (ryp - lyp) / (rxp - lxp)
            y0, y1 = my - mx * slope, my + (w - mx) * slope
            cv2.line(vis, (0, int(y0)), (w, int(y1)), (0, 220, 0), 2)
        # true horizontal reference through the midpoint
        cv2.line(vis, (0, int(my)), (w, int(my)), (170, 170, 170), 1, cv2.LINE_AA)
        for (px, py) in ((lxp, lyp), (rxp, ryp)):
            cv2.circle(vis, (int(px), int(py)), 5, (0, 220, 0), -1)
        txt = f'roll {roll:+.1f}' if roll is not None else 'roll: n/a'
    else:
        txt = 'NO NET KEYPOINTS'

    cv2.rectangle(vis, (0, 0), (w, 34), (0, 0, 0), -1)
    cv2.putText(vis, txt, (10, 24), FONT, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    return vis


def review_video(video_path):
    name = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = os.path.join(OUT_ROOT, name)
    os.makedirs(out_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if total < 10:
        print(f'  {name}: too short ({total} frames) — skipped')
        return None

    frame_nums = [int(total * q) for q in
                  [i / (N_FRAMES + 1) for i in range(1, N_FRAMES + 1)]]
    rolls, tiles = [], []
    for fn in frame_nums:
        try:
            frame = extract_frame(video_path, fn)
        except RuntimeError:
            continue
        kp = run_net_keypoint_model(frame)
        roll = net_roll_deg(kp)
        if roll is not None:
            rolls.append(roll)
        vis = annotate_frame(frame, roll, kp)
        cv2.imwrite(os.path.join(out_dir, f'f{fn:05d}.jpg'), vis)
        tiles.append(cv2.resize(vis, (480, int(480 * vis.shape[0] / vis.shape[1]))))

    med = _median(rolls)
    if tiles:
        montage = cv2.vconcat(tiles)
        band = usable_roll(med)
        banner_txt = (f'{name}   median roll {med:+.1f} deg   '
                      f'{"CORRECTED (in %g-%g band)" % (ROLL_CORRECTION_MIN_DEG, ROLL_CORRECTION_MAX_DEG) if band is not None else "not corrected"}'
                      if med is not None else f'{name}   no net-cord slope on any sampled frame')
        banner = montage[:40].copy() * 0
        cv2.putText(banner, banner_txt, (10, 26), FONT, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        montage = cv2.vconcat([banner, montage])
        cv2.imwrite(os.path.join(out_dir, '_montage.jpg'), montage)

    return {
        'video': video_path, 'name': name, 'frames': frame_nums,
        'per_frame_roll': [round(r, 1) for r in rolls],
        'median_roll_deg': round(med, 1) if med is not None else None,
        'would_correct': usable_roll(med) is not None,
        'out_dir': out_dir,
    }


def sample_clips(user_n, pro_n, seed):
    random.seed(seed)
    picks = []
    if user_n:
        uc = glob.glob(os.path.join(DATA_DIR, 'runtime', 'user_clips', '**', '*.mp4'), recursive=True)
        picks += random.sample(uc, min(user_n, len(uc)))
    if pro_n:
        pc = []
        for st in ('forehand', 'backhand', 'serve'):
            pc += glob.glob(os.path.join(DATA_DIR, '04_clips', st, '*.mp4'))
        picks += random.sample(pc, min(pro_n, len(pc)))
    return picks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('videos', nargs='*', help='video file(s) to review')
    ap.add_argument('--user-clips', type=int, default=0, help='also sample N clips from data/runtime/user_clips')
    ap.add_argument('--pro', type=int, default=0, help='also sample N pro clips from data/04_clips')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--log', action='store_true', help='prompt for an eyeballed correction and append it to the review log')
    args = ap.parse_args()

    videos = list(args.videos) + sample_clips(args.user_clips, args.pro, args.seed)
    videos = [v for v in videos if os.path.exists(v)] or None
    if not videos:
        ap.error('no existing videos given (pass paths, or --user-clips / --pro)')

    os.makedirs(OUT_ROOT, exist_ok=True)
    print(f'Annotated output under: {OUT_ROOT}\n')
    print(f'{"clip":<40} {"median roll":>12} {"corrected?":>11}')
    print('-' * 66)

    results = []
    for v in videos:
        r = review_video(v)
        if r is None:
            continue
        results.append(r)
        mr = f'{r["median_roll_deg"]:+.1f}°' if r['median_roll_deg'] is not None else 'n/a'
        print(f'{r["name"]:<40} {mr:>12} {("yes" if r["would_correct"] else "no"):>11}')

    print(f'\nOpen each clip\'s  _montage.jpg  to eyeball: green = detected net cord, '
          f'grey = true horizontal. If they diverge, that angle is the roll.')

    if args.log and results:
        if not sys.stdin.isatty():
            print('\n--log: stdin is not interactive, skipping the correction prompt.')
            return
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            for r in results:
                ans = input(f'\n{r["name"]}: auto median = {r["median_roll_deg"]}°. '
                            f'Corrected roll in degrees (blank = accept auto, "x" = skip): ').strip()
                if ans.lower() == 'x':
                    continue
                corrected = r['median_roll_deg'] if ans == '' else float(ans)
                f.write(json.dumps({
                    'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'video': r['video'], 'name': r['name'],
                    'auto_median_roll_deg': r['median_roll_deg'],
                    'corrected_roll_deg': corrected,
                }) + '\n')
                print(f'  logged -> {LOG_PATH}  (re-run: compare_swing.py "{r["video"]}" <shot> --camera-roll {corrected})')


if __name__ == '__main__':
    main()
