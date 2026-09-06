"""
Ad-hoc visual: render the ball tracker's output onto a whole clip as an mp4.

 - small hollow circle  = raw per-frame YOLO ball detection (fine-tuned model),
   labelled with confidence
 - filled circle + trail = the Kalman-filtered track (ball_tracker.track_ball),
   green when it accepted a measurement that frame, amber when it's coasting
   on prediction alone
 - box = racket detection

Usage:
  python render_ball_overlay.py <video_path> [--out out.mp4] [--start N] [--end N]
"""
import argparse
import os
import sys
from collections import deque

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import racket_tracker as rt
from ball_tracker import track_ball


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video')
    ap.add_argument('--out', default=None)
    ap.add_argument('--start', type=int, default=None)
    ap.add_argument('--end', type=int, default=None)
    args = ap.parse_args()

    frame_range = (args.start, args.end) if args.start is not None and args.end is not None else None
    print(f'detecting on {args.video} ...')
    detections, fps = rt.track_racket_and_ball(args.video, frame_range=frame_range)
    start_frame = detections[0]['frame']
    end_frame = detections[-1]['frame']

    track = dict(track_ball(detections, start_frame, end_frame, rt._center_in_original_space))
    accepted_frames = set()
    # re-run just to know per-frame accept/coast: track_ball hides it, so
    # approximate -- a frame is "accepted" if it had a real detection.
    for d in detections:
        if d['ball_box'] is not None:
            accepted_frames.add(d['frame'])

    n_det = sum(1 for d in detections if d['ball_box'] is not None)
    print(f'{n_det}/{len(detections)} frames had a raw ball detection; '
          f'tracked path spans {len(track)} frames')

    out_path = args.out or os.path.join(
        os.environ.get('TEMP', '.'), 'ball_overlay_' + os.path.splitext(os.path.basename(args.video))[0] + '.mp4')

    cap = cv2.VideoCapture(args.video)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if frame_range:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'mp4v'), fps or 30, (w, h))

    trail = deque(maxlen=15)
    det_by_frame = {d['frame']: d for d in detections}
    idx = start_frame
    while cap.isOpened() and idx <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break
        d = det_by_frame.get(idx)
        if d and d['racket_box']:
            x1, y1, x2, y2 = [int(v) for v in d['racket_box']]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 180, 0), 2)
        if d and d['ball_box']:
            bx1, by1, bx2, by2 = [int(v) for v in d['ball_box']]
            cx, cy = (bx1 + bx2) // 2, (by1 + by2) // 2
            cv2.circle(frame, (cx, cy), max(8, (bx2 - bx1) // 2 + 4), (0, 0, 255), 2)
            cv2.putText(frame, f"{d['ball_conf']:.2f}", (cx + 10, cy - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        if idx in track:
            tx, ty = track[idx]
            trail.append((int(tx), int(ty)))
            coasting = idx not in accepted_frames
            color = (0, 165, 255) if coasting else (0, 220, 0)
            cv2.circle(frame, (int(tx), int(ty)), 6, color, -1)
        for i in range(1, len(trail)):
            cv2.line(frame, trail[i - 1], trail[i], (0, 220, 0), 2)

        cv2.putText(frame, f'frame {idx}', (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        writer.write(frame)
        idx += 1

    cap.release()
    writer.release()
    print(f'wrote {out_path}')


if __name__ == '__main__':
    main()
