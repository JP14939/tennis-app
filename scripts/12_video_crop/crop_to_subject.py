"""
Crop a swing video tightly around the player onto a solid backdrop.

Not real background removal/segmentation -- there's no matting model in this
codebase. This is a pose-driven bounding-box crop: track the player's
landmarks frame by frame, crop+resize tightly around them, and place that on
a solid canvas. It still shows the real background *inside* the crop
rectangle, just much less of the court around the player than the original,
uncropped frame.

Reuses extract_poses() (scripts/02_pose_extraction) for per-frame landmarks,
same building-block-reuse pattern as detect_rallies.py. New here: per-frame
bbox computation, temporal smoothing, and the crop/pad/write pass.

Usage:
  python crop_to_subject.py <in_video> <out_video>

Output (stdout): JSON -- {"cropped": true} on success, or
{"cropped": false, "reason": "..."} on failure. Never raises/exits non-zero
for a detection failure -- callers should fall back to the original video
rather than have the whole comparison request fail over a cosmetic crop.
"""
import sys
import os
import json
import argparse
import tempfile
import contextlib
import cv2
import numpy as np

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))

from extract_poses import extract_poses

# Canvas the cropped subject is placed on -- portrait, matches typical
# handheld swing-recording framing.
CANVAS_W = 480
CANVAS_H = 854
BACKDROP_COLOR = (24, 24, 24)  # BGR, close to the app's dark theme background

VISIBILITY_THRESHOLD = 0.5
MARGIN = 0.35  # fraction of bbox size added on each side
EMA_ALPHA = 0.3  # bbox smoothing -- lower = smoother/slower to react


def _frame_bbox(landmarks, width, height):
    xs, ys = [], []
    for lm in landmarks or []:
        if lm['visibility'] >= VISIBILITY_THRESHOLD:
            xs.append(lm['x'] * width)
            ys.append(lm['y'] * height)
    if not xs:
        return None
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    mx = (x1 - x0) * MARGIN
    my = (y1 - y0) * MARGIN
    return (x0 - mx, y0 - my, x1 + mx, y1 + my)


def _smooth_boxes(raw_boxes):
    """raw_boxes: list of bbox-or-None, one per frame. Holds the last known
    box across gaps and EMA-smooths across frames with a detection."""
    smoothed = []
    current = None
    for box in raw_boxes:
        if box is not None:
            if current is None:
                current = box
            else:
                current = tuple(
                    EMA_ALPHA * b + (1 - EMA_ALPHA) * c
                    for b, c in zip(box, current)
                )
        smoothed.append(current)
    return smoothed


def _place_on_canvas(frame, box):
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    h, w = frame.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return None

    crop = frame[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    scale = min(CANVAS_W / cw, CANVAS_H / ch)
    new_w, new_h = max(1, int(cw * scale)), max(1, int(ch * scale))
    resized = cv2.resize(crop, (new_w, new_h))

    canvas = np.full((CANVAS_H, CANVAS_W, 3), BACKDROP_COLOR, dtype='uint8')
    off_x = (CANVAS_W - new_w) // 2
    off_y = (CANVAS_H - new_h) // 2
    canvas[off_y:off_y + new_h, off_x:off_x + new_w] = resized
    return canvas


def crop_to_subject(video_path, output_path):
    with tempfile.TemporaryDirectory() as tmp:
        pose_path = os.path.join(tmp, 'poses.json')
        with contextlib.redirect_stdout(sys.stderr):
            extract_poses(video_path, pose_path, sample_every=1)
        with open(pose_path) as f:
            pose_data = json.load(f)

    fps = pose_data['fps']
    frames_meta = pose_data['frames']
    if not any(f['landmarks'] for f in frames_meta):
        return {'cropped': False, 'reason': 'No pose detected in any frame'}

    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    raw_boxes = [_frame_bbox(f['landmarks'], width, height) for f in frames_meta]
    boxes = _smooth_boxes(raw_boxes)
    # Fill any leading gap (no detection yet at video start) with the first
    # real box found, so early frames aren't dropped.
    first_real = next((b for b in boxes if b is not None), None)
    boxes = [b if b is not None else first_real for b in boxes]

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (CANVAS_W, CANVAS_H))

    frame_idx = 0
    written = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        box = boxes[frame_idx] if frame_idx < len(boxes) else boxes[-1]
        canvas = _place_on_canvas(frame, box) if box else None
        writer.write(canvas if canvas is not None else frame[:CANVAS_H, :CANVAS_W])
        written += 1
        frame_idx += 1

    cap.release()
    writer.release()

    if written == 0:
        return {'cropped': False, 'reason': 'No frames read from video'}
    return {'cropped': True}


def main():
    parser = argparse.ArgumentParser(description='Crop a swing video tightly around the player onto a solid backdrop')
    parser.add_argument('video', help='Path to input video')
    parser.add_argument('output', help='Path to write cropped output video')
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(json.dumps({'cropped': False, 'reason': f'Video not found: {args.video}'}))
        return

    try:
        result = crop_to_subject(args.video, args.output)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({'cropped': False, 'reason': str(e)}))


if __name__ == '__main__':
    main()
