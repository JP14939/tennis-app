"""
How often does the ball detector actually give ball_speed.py's radial
(size-derivative) estimator enough to work with, on real behind-the-baseline
footage?

Not a contact-frame accuracy eval (that's eval_pro_clip_contact.py /
train_contact_frame_model.py's job) -- this samples arbitrary points spread
through real match footage (default: Jack's own IMG_5755.MOV/IMG_5756.MOV,
confirmed real behind-the-baseline recordings -- see TODO_MANUAL.md's
2026-09-11 entry on why the data/01_source_videos/practice/*.mp4 set is NOT
a fair stand-in, it's downloaded broadcast footage) as a proxy for "typical
in-play moments", not swing contacts specifically. At each sample point it
asks two separate questions ball_speed.py's DIAMETER_HALF_WINDOW/
MIN_BALL_CONF_FOR_DIAMETER gate conflates into one pass/fail:

  1. RECALL: how many confident ball detections fall inside the
     +/-DIAMETER_HALF_WINDOW frame window (need >=2 for even a degree-1 fit,
     >=3 for the default degree-2)?
  2. PRECISION (box quality, not presence): among the detections that DO
     clear the confidence bar, how noisy is the measured diameter frame to
     frame? A size-derivative estimator is directly sensitive to box-size
     jitter in a way a centre-position tracker isn't, so a detector that's
     "good enough" for position tracking can still be too imprecise here.

Usage: python eval_ball_speed_diameter_availability.py [--videos PATH ...]
                                                        [--n-samples N]
Output: printed table + data/07_audits/ball_speed_diameter_availability.json
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
for _sub in ('00_utils',):
    _p = os.path.join(SCRIPTS_DIR, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from paths import DATA_DIR  # noqa: E402
from racket_tracker import track_racket_and_ball  # noqa: E402
from ball_speed import DIAMETER_HALF_WINDOW, MIN_BALL_CONF_FOR_DIAMETER  # noqa: E402

OUT_PATH = os.path.join(DATA_DIR, '07_audits', 'ball_speed_diameter_availability.json')

DEFAULT_VIDEOS = [
    r'C:\Users\jackp\Downloads\IMG_5755.MOV',
    r'C:\Users\jackp\Downloads\IMG_5756.MOV',
]


def _diameter_at(box):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return None
    return float(np.sqrt(w * h))


def _sample_windows(video_path, n_samples, window_frames):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if nframes <= 0:
        return fps, []

    margin = window_frames + 1
    centers = np.linspace(margin, max(margin, nframes - margin - 1), n_samples, dtype=int)

    results = []
    for center in centers:
        start, end = int(center - window_frames), int(center + window_frames)
        detections, _ = track_racket_and_ball(video_path, frame_range=(start, end))
        confident = []
        for d in detections:
            box, conf = d.get('ball_box'), d.get('ball_conf')
            if box is None or conf is None or conf < MIN_BALL_CONF_FOR_DIAMETER:
                continue
            diam = _diameter_at(box)
            if diam is not None:
                confident.append((d['frame'], diam))
        confident.sort(key=lambda p: p[0])

        jitter_ratios = []
        for (f0, d0), (f1, d1) in zip(confident, confident[1:]):
            if f1 - f0 == 1 and d0 > 0:
                jitter_ratios.append(abs(d1 - d0) / d0)

        results.append({
            'center_frame': int(center),
            'n_confident_in_window': len(confident),
            'enough_for_linear_fit': len(confident) >= 2,
            'enough_for_quadratic_fit': len(confident) >= 3,
            'frame_to_frame_jitter_ratios': jitter_ratios,
        })
    return fps, results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--videos', nargs='+', default=None)
    parser.add_argument('--n-samples', type=int, default=40)
    args = parser.parse_args()

    videos = args.videos or [v for v in DEFAULT_VIDEOS if os.path.exists(v)]
    if not videos:
        print('No videos found (checked default IMG_5755/5756.MOV paths -- pass --videos).',
              file=sys.stderr)
        sys.exit(1)

    window_frames = DIAMETER_HALF_WINDOW
    all_results = {}
    for video in videos:
        print(f'\n=== {video} ===')
        fps, results = _sample_windows(video, args.n_samples, window_frames)
        all_results[video] = results

        n = len(results)
        n_linear_ok = sum(r['enough_for_linear_fit'] for r in results)
        n_quad_ok = sum(r['enough_for_quadratic_fit'] for r in results)
        all_jitter = [j for r in results for j in r['frame_to_frame_jitter_ratios']]

        print(f'  windows sampled: {n} (+/-{window_frames} frames each, fps={fps:.1f})')
        print(f'  enough for linear fit (>=2 confident dets):    {n_linear_ok}/{n} '
              f'({100 * n_linear_ok / n:.0f}%)')
        print(f'  enough for quadratic fit (>=3 confident dets): {n_quad_ok}/{n} '
              f'({100 * n_quad_ok / n:.0f}%)')
        if all_jitter:
            arr = np.array(all_jitter)
            print(f'  frame-to-frame diameter jitter (|delta|/diameter), n={len(arr)}: '
                  f'median={np.median(arr):.3f} p90={np.percentile(arr, 90):.3f} '
                  f'max={arr.max():.3f}')
        else:
            print('  frame-to-frame diameter jitter: no adjacent-frame confident pairs found')

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f'\nWrote {OUT_PATH}')


if __name__ == '__main__':
    main()
