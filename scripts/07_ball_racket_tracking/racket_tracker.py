"""
Racket path + ball-racket contact frame detection using a pretrained YOLO
(COCO) model — no custom training/labeling needed since 'tennis racket'
(class 38) and 'sports ball' (class 32) are both standard COCO classes.

Provides:
  track_racket_and_ball(video_path)  -> per-frame detections + fps
  find_contact_frame(detections, fallback_frame) -> (frame, confidence, method)
  racket_path(detections)            -> list of {frame, x, y, conf} centroids
"""
import math
import sys

import cv2
from ultralytics import YOLO

RACKET_CLASS = 38
BALL_CLASS = 32
CONF_THRESHOLD = 0.15

_model = None
_model_name = None


def get_model(model_name='yolo11n.pt'):
    global _model, _model_name
    if _model is None or _model_name != model_name:
        _model = YOLO(model_name)
        _model_name = model_name
    return _model


def track_racket_and_ball(video_path, model=None, frame_range=None):
    """Run detection on every frame, or only frame_range=(start, end) if given
    (much faster when only a small window around a known contact point matters,
    e.g. auditing pro clips rather than processing a whole clip). Returns
    (detections, fps)."""
    model = model or get_model()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video_path}')
    fps = cap.get(cv2.CAP_PROP_FPS)

    if frame_range:
        start, end = frame_range
        start = max(0, start)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        idx = start
    else:
        end = None
        idx = 0

    detections = []
    while cap.isOpened():
        if end is not None and idx >= end:
            break
        ret, frame = cap.read()
        if not ret:
            break
        results = model.predict(frame, classes=[RACKET_CLASS, BALL_CLASS],
                                 conf=CONF_THRESHOLD, verbose=False)
        racket_box = racket_conf = ball_box = ball_conf = None
        for box in results[0].boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            xyxy = box.xyxy[0].tolist()
            if cls == RACKET_CLASS and (racket_conf is None or conf > racket_conf):
                racket_box, racket_conf = xyxy, conf
            if cls == BALL_CLASS and (ball_conf is None or conf > ball_conf):
                ball_box, ball_conf = xyxy, conf

        detections.append({
            'frame': idx,
            'racket_box': racket_box, 'racket_conf': racket_conf,
            'ball_box': ball_box, 'ball_conf': ball_conf,
        })
        idx += 1

    cap.release()
    return detections, fps


def _center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _dist(b1, b2):
    c1, c2 = _center(b1), _center(b2)
    return math.hypot(c1[0] - c2[0], c1[1] - c2[1])


def _find_gap_contact(window_dets):
    """
    At true contact the ball is fastest-moving and often occluded by the
    racket/strings, so the detector frequently loses it for 1-2 frames right
    at impact. If the ball is tracked approaching, vanishes briefly, then
    reappears departing, the midpoint of that gap is a strong contact signal
    — often better than proximity, since the true contact frame may have no
    ball detection at all.

    Returns (frame_idx, confidence, gap_size) or None if no clean gap found.
    """
    ball_frames = sorted(d['frame'] for d in window_dets if d['ball_box'])
    if len(ball_frames) < 2:
        return None

    gaps = [(ball_frames[i], ball_frames[i + 1]) for i in range(len(ball_frames) - 1)]
    start, end = max(gaps, key=lambda g: g[1] - g[0])
    gap_size = end - start
    if gap_size < 2:  # ball never actually vanished — no occlusion event
        return None

    midpoint = round((start + end) / 2)
    # confidence: tight gaps (brief occlusion) are more trustworthy than long ones
    conf = round(max(0.3, 1.0 - 0.1 * gap_size), 3)
    return midpoint, conf, gap_size


def find_contact_frame(detections, fallback_frame, fps, search_window_sec=0.3):
    """
    Best-guess contact frame, searched only within `search_window_sec` of the
    existing wrist-velocity estimate (`fallback_frame`) — that estimate is a
    reasonably reliable rough anchor, we're just refining it, not replacing
    it wholesale. Tries, in order:
      1. Ball-detection gap midpoint (see _find_gap_contact) — the ball
         vanishing briefly from occlusion/blur is a stronger contact signal
         than proximity, when available.
      2. Closest ball-racket proximity frame, among frames where both are
         actually detected.
      3. The wrist-velocity peak itself.

    Returns (frame_idx, confidence, method).
    """
    window = int(search_window_sec * fps)
    window_dets = [d for d in detections if abs(d['frame'] - fallback_frame) <= window]

    gap_result = _find_gap_contact(window_dets)
    if gap_result:
        frame, conf, gap_size = gap_result
        return frame, conf, f'ball_occlusion_gap({gap_size}f)'

    candidates = [d for d in window_dets if d['racket_box'] and d['ball_box']]
    if candidates:
        best = min(candidates, key=lambda d: _dist(d['racket_box'], d['ball_box']))
        conf = round(min(best['racket_conf'], best['ball_conf']), 3)
        return best['frame'], conf, 'ball_racket_proximity'

    return fallback_frame, 0.3, 'wrist_velocity_fallback'


def racket_path(detections):
    """List of {frame, x, y, conf} racket centroids for frames with a detection."""
    path = []
    for d in detections:
        if d['racket_box']:
            x, y = _center(d['racket_box'])
            path.append({'frame': d['frame'], 'x': round(x, 1), 'y': round(y, 1),
                         'conf': round(d['racket_conf'], 3)})
    return path


if __name__ == '__main__':
    clip = sys.argv[1] if len(sys.argv) > 1 else \
        r'C:\Users\jackp\tennis_app\data\04_clips\forehand\forehand_swing_0005_conf100.mp4'
    dets, fps = track_racket_and_ball(clip)
    fallback = len(dets) // 2
    frame, conf, method = find_contact_frame(dets, fallback, fps)
    path = racket_path(dets)

    print(f'{clip}')
    print(f'{len(dets)} frames @ {fps:.1f}fps')
    print(f'Racket path: {len(path)}/{len(dets)} frames with a racket detection')
    print(f'Contact frame: {frame} ({frame/fps:.2f}s) — confidence {conf} — method: {method}')
