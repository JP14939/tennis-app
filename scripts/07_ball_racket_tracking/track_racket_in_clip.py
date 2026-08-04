"""
Track racket position + body (hip midpoint, shoulder width) per frame across
a clip, for the body-rotation phase's "racket vs. body" signal.

Reuses the exact crop->predict->uncrop pattern from sample_racket_crops.py
(generic yolo11n.pt COCO racket-class detection -> padded crop -> the
fine-tuned yolo_pose_run keypoint model) plus a MediaPipe pose pass per
frame (same normalisation building blocks as build_pro_database.py, so pro
clips and live user clips are scored identically).

Self-contained: does its own pose extraction rather than depending on an
already-built trajectory, so it works the same way whether called on a short
pro clip (whole clip) or a slice of the user's uploaded video (frame_range).
"""
import math
import os
import statistics
import sys

import cv2
from ultralytics import YOLO

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from build_pro_database import get_shoulder_ref  # noqa: E402

RACKET_CLASS = 38
DETECT_CONF = 0.25
PADDING_FRAC = 0.25
RACKET_DETECTOR_PATH = 'yolo11n.pt'
RACKET_KEYPOINT_MODEL_PATH = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\yolo_pose_run\weights\best.pt'
POINTS = ['handle', 'throat', 'tip', 'left_edge', 'right_edge']

_detector = None
_kp_model = None


def _models():
    global _detector, _kp_model
    if _detector is None:
        _detector = YOLO(RACKET_DETECTOR_PATH)
        _kp_model = YOLO(RACKET_KEYPOINT_MODEL_PATH)
    return _detector, _kp_model


def _detect_racket_handle(frame, detector, kp_model):
    """Returns (x, y) handle position in raw [0,1] frame-normalised coords, or None."""
    h, w = frame.shape[:2]
    results = detector.predict(frame, classes=[RACKET_CLASS], conf=DETECT_CONF, verbose=False)
    boxes = results[0].boxes
    if len(boxes) == 0:
        return None
    best = max(boxes, key=lambda b: float(b.conf[0]))
    x1, y1, x2, y2 = best.xyxy[0].tolist()
    bw, bh = x2 - x1, y2 - y1
    pad_x, pad_y = bw * PADDING_FRAC, bh * PADDING_FRAC
    cx1, cy1 = max(0, int(x1 - pad_x)), max(0, int(y1 - pad_y))
    cx2, cy2 = min(w, int(x2 + pad_x)), min(h, int(y2 + pad_y))
    crop = frame[cy1:cy2, cx1:cx2]
    if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 10:
        return None

    kp_results = kp_model.predict(crop, verbose=False)
    if len(kp_results[0].keypoints) == 0 or kp_results[0].keypoints.xy.shape[1] == 0:
        return None
    kpts = kp_results[0].keypoints.xy[0].cpu().numpy()
    handle_x, handle_y = kpts[POINTS.index('handle')]
    if handle_x == 0 and handle_y == 0:
        return None  # model's convention for "not predicted"

    full_x = cx1 + handle_x
    full_y = cy1 + handle_y
    return full_x / w, full_y / h


def track_racket_body(video_path, frame_range=None, landmarker=None, sample_every=3):
    """
    Runs racket + pose detection per frame across the clip (or frame_range
    if given, as (lo, hi) inclusive frame numbers).

    Returns a list of per-frame dicts:
      {frame, racket_handle: (x,y) or None, hip_mid: (x,y) or None,
       shoulder_width: float or None}
    all in raw [0,1] frame-normalised coords (not yet trajectory-scaled).
    """
    from infer_angle import create_landmarker, _run_landmarker  # local import, avoids circular path issues

    detector, kp_model = _models()
    own_landmarker = landmarker is None
    if own_landmarker:
        landmarker = create_landmarker()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        if own_landmarker:
            landmarker.close()
        raise RuntimeError(f'Cannot open video: {video_path}')
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    lo, hi = frame_range if frame_range is not None else (0, total - 1)
    lo, hi = max(0, lo), min(total - 1, hi)

    results = []
    idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if lo <= idx <= hi and (idx - lo) % sample_every == 0:
            racket_handle = _detect_racket_handle(frame, detector, kp_model)

            hip_mid = None
            shoulder_width = None
            landmarks = _run_landmarker(frame, landmarker)
            if landmarks is not None:
                lm_dict = {name: {'x': lm.x, 'y': lm.y, 'visibility': lm.visibility}
                           for name, lm in zip(
                               ['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip'],
                               [landmarks[11], landmarks[12], landmarks[23], landmarks[24]])}
                mid_x, mid_y, width = get_shoulder_ref(lm_dict)
                lh, rh = lm_dict['left_hip'], lm_dict['right_hip']
                if lh['visibility'] >= 0.3 and rh['visibility'] >= 0.3:
                    hip_mid = ((lh['x'] + rh['x']) / 2, (lh['y'] + rh['y']) / 2)
                if mid_x is not None and width >= 0.01:
                    shoulder_width = width

            results.append({'frame': idx, 'racket_handle': racket_handle,
                             'hip_mid': hip_mid, 'shoulder_width': shoulder_width})
        idx += 1
        if idx > hi:
            break

    cap.release()
    if own_landmarker:
        landmarker.close()
    return results


def avg_racket_body_distance(frame_results, min_valid_frames=3):
    """
    Normalised (shoulder-width-scaled) average distance from racket handle
    to hip midpoint across frames with a confident racket + pose detection.
    Returns None if fewer than min_valid_frames have both signals.
    """
    widths = [r['shoulder_width'] for r in frame_results if r['shoulder_width'] is not None]
    scale = statistics.median(widths) if widths else None
    if not scale or scale < 0.01:
        return None

    dists = []
    for r in frame_results:
        if r['racket_handle'] is None or r['hip_mid'] is None:
            continue
        hx, hy = r['racket_handle']
        px, py = r['hip_mid']
        dists.append(math.sqrt((hx - px) ** 2 + (hy - py) ** 2) / scale)

    if len(dists) < min_valid_frames:
        return None
    return round(sum(dists) / len(dists), 4)


if __name__ == '__main__':
    import json
    video_path = sys.argv[1]
    results = track_racket_body(video_path)
    n_racket = sum(1 for r in results if r['racket_handle'] is not None)
    n_pose = sum(1 for r in results if r['hip_mid'] is not None)
    print(f'{len(results)} frames | racket detected: {n_racket} | pose detected: {n_pose}')
    print(f'avg_racket_body_distance: {avg_racket_body_distance(results)}')
