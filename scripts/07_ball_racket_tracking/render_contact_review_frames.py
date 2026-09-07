"""
One-off visual audit: draws the ball/racket tracker's own detected boxes on
frames around its guessed contact frame (and Jack's hand-marked one, when
they differ) for a sample of reviewed practice clips -- weighted toward
serves, the shot type contact_frame_training_log.jsonl shows has ~2x the
contact-frame error of forehand/backhand even against real human ground
truth (27f vs 6-14f median absolute error).

Answers "how good is ball/racket detection really" with pictures instead of
just aggregate numbers. Calls the exact same functions the live pipeline
uses (racket_tracker.track_racket_and_ball / find_contact_frame,
compare_swing.find_peak_wrist_frame) -- no reimplementation, so what you see
here is genuinely what the pipeline sees.

Run once, browse the output folder in Explorer/an image viewer -- no
server/UI needed for this first pass.

Usage:
  python render_contact_review_frames.py [--n-serve 15] [--n-fh 5] [--n-bh 5]

Output: data/07_ball_racket_tracking/contact_review/<clip_id>/frame_NNNN.jpg
  + a printed summary table (guess vs human frame, delta, method, confidence).
"""
import argparse
import json
import os
import random
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
for sub in ('00_utils', '06_database_build', '08_comparison_engine'):
    p = os.path.join(SCRIPTS_DIR, sub)
    if p not in sys.path:
        sys.path.insert(0, p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from paths import DATA_DIR  # noqa: E402
from clip_urls import PRO_CLIPS_DIR  # noqa: E402
from racket_tracker import track_racket_and_ball, find_contact_frame  # noqa: E402
from compare_swing import find_peak_wrist_frame  # noqa: E402
from build_contact_student_dataset import (  # noqa: E402
    PRO_DB_PATH, _practice_teacher_times, _lm_by_name, _get_poses,
)

OUT_DIR = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'contact_review')
WINDOW_RADIUS = 5       # frames either side of the tracker's guess to render
TRACK_HALF_RANGE = 90   # frames either side of the wrist-peak fallback to run
                        # YOLO over -- find_contact_frame only ever searches
                        # +/-0.3s of that anchor anyway, this is just render context

BALL_COLOR = (0, 255, 255)     # yellow, BGR
RACKET_COLOR = (255, 0, 255)   # magenta, BGR
TAG_COLOR = (0, 0, 255)        # red
PLAIN_COLOR = (255, 255, 255)  # white


def _sample_clips(n_serve, n_fh, n_bh, seed=7):
    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    by_id = {e['id']: e for e in db['entries']}
    teacher_times = _practice_teacher_times()

    by_shot = {'serve': [], 'forehand': [], 'backhand': []}
    for eid, human_sec in teacher_times.items():
        entry = by_id.get(eid)
        if entry and entry['shot_type'] in by_shot:
            by_shot[entry['shot_type']].append((eid, entry, human_sec))

    random.seed(seed)
    picked = []
    for shot, n in (('serve', n_serve), ('forehand', n_fh), ('backhand', n_bh)):
        pool = by_shot[shot]
        picked += random.sample(pool, min(n, len(pool)))
    return picked


def _draw_box(frame, box, color, label):
    if box is None:
        return
    x1, y1, x2, y2 = (int(v) for v in box)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(frame, label, (x1, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


def render_one(eid, entry, human_sec):
    clip = os.path.join(PRO_CLIPS_DIR, entry['clip_path'])
    if not os.path.exists(clip):
        return None, 'clip_missing'

    # Same fallback anchor the live pipeline uses: the wrist-velocity peak
    # from pose, computed on the already-cached pose data (Phase C's sweep
    # already populated this cache for every reviewed practice entry).
    poses = _get_poses(clip, eid)
    raw = poses.get('frames') or []
    frames_lm = [{'frame': fr['frame'], 'landmarks': _lm_by_name(fr)} for fr in raw]
    cap = cv2.VideoCapture(clip)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if any(f['landmarks'] for f in frames_lm):
        anchor_idx = find_peak_wrist_frame(frames_lm, poses.get('fps') or fps)
        fallback_frame = frames_lm[anchor_idx]['frame']
    else:
        fallback_frame = round(human_sec * fps)  # last resort, no pose at all

    frame_range = (fallback_frame - TRACK_HALF_RANGE, fallback_frame + TRACK_HALF_RANGE)
    detections, tracked_fps = track_racket_and_ball(clip, frame_range=frame_range)
    fps = tracked_fps or fps

    guess_frame, guess_conf, guess_method = find_contact_frame(detections, fallback_frame, fps)
    human_frame = round(human_sec * fps)

    det_by_frame = {d['frame']: d for d in detections}
    out_dir = os.path.join(OUT_DIR, eid)
    os.makedirs(out_dir, exist_ok=True)

    frames_to_render = sorted(
        set(range(guess_frame - WINDOW_RADIUS, guess_frame + WINDOW_RADIUS + 1))
        | set(range(human_frame - 2, human_frame + 3))
    )
    cap = cv2.VideoCapture(clip)
    for fi in frames_to_render:
        if fi < 0:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, frame = cap.read()
        if not ret:
            continue
        d = det_by_frame.get(fi)
        if d:
            _draw_box(frame, d.get('ball_box'), BALL_COLOR, f"ball {d.get('ball_conf') or 0:.2f}")
            _draw_box(frame, d.get('racket_box'), RACKET_COLOR, f"racket {d.get('racket_conf') or 0:.2f}")
        tags = []
        if fi == guess_frame:
            tags.append('TRACKER GUESS')
        if fi == human_frame:
            tags.append('YOUR MARK')
        label = f'f{fi}' + (('  ' + ' + '.join(tags)) if tags else '')
        cv2.putText(frame, label, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    TAG_COLOR if tags else PLAIN_COLOR, 2)
        cv2.imwrite(os.path.join(out_dir, f'frame_{fi:04d}.jpg'), frame)
    cap.release()

    return {
        'id': eid, 'shot_type': entry['shot_type'],
        'guess_frame': guess_frame, 'human_frame': human_frame,
        'delta': guess_frame - human_frame,
        'method': guess_method, 'confidence': guess_conf,
    }, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n-serve', type=int, default=15)
    ap.add_argument('--n-fh', type=int, default=5)
    ap.add_argument('--n-bh', type=int, default=5)
    args = ap.parse_args()

    picked = _sample_clips(args.n_serve, args.n_fh, args.n_bh)
    print(f'Sampled {len(picked)} reviewed clips ({args.n_serve} serve / {args.n_fh} forehand / {args.n_bh} backhand target)\n')

    results, failed = [], []
    for eid, entry, human_sec in picked:
        try:
            r, skip_reason = render_one(eid, entry, human_sec)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            failed.append((eid, f'{type(e).__name__}: {e}'))
            continue
        if skip_reason:
            failed.append((eid, skip_reason))
            continue
        results.append(r)
        print(f"  {eid:16} {r['shot_type']:9} guess={r['guess_frame']:4} human={r['human_frame']:4} "
              f"delta={r['delta']:+4}f  conf={r['confidence']:.2f}  {r['method']}")

    print(f'\n{len(results)} clips rendered to {OUT_DIR}')
    if failed:
        print(f'{len(failed)} skipped:')
        for eid, reason in failed:
            print(f'  {eid}: {reason}')

    if results:
        import statistics
        by_shot = {}
        for r in results:
            by_shot.setdefault(r['shot_type'], []).append(abs(r['delta']))
        print('\nmedian |delta| by shot type (this sample):')
        for shot, deltas in by_shot.items():
            print(f'  {shot:10} n={len(deltas):3}  median={statistics.median(deltas):.1f}f')


if __name__ == '__main__':
    main()
