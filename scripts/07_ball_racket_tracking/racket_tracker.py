"""
Racket path + ball-racket contact frame detection using a pretrained YOLO
(COCO) model — no custom training/labeling needed since 'tennis racket'
(class 38) and 'sports ball' (class 32) are both standard COCO classes.

Provides:
  track_racket_and_ball(video_path)  -> per-frame detections + fps
  find_contact_frame(detections, fallback_frame) -> (frame, confidence, method)
  ball_departure_confirmed(detections, contact_frame, fps) -> (confirmed, confidence)
  racket_path(detections)            -> list of {frame, x, y, conf} centroids
"""
import math
import sys

import cv2
from ultralytics import YOLO

from ball_tracker import track_ball

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


def _center_in_original_space(box, det):
    """
    Detections from the CROPPED tracking path (verify_shot_contact.py's
    track_racket_and_ball_cropped / track_racket_tip_and_ball_cropped)
    carry each frame's own crop scale/offset ('crop_scale'/'crop_x0'/
    'crop_y0') -- every frame is cropped tight to THAT frame's own pose
    bbox, so raw crop-pixel coordinates are NOT comparable across frames
    (same issue _racket_velocity_profile already had to correct for).
    Detections without crop metadata (the non-cropped track_racket_and_ball()
    path) default to scale=1, offset=0 -- already in original-frame space.
    """
    cx, cy = _center(box)
    scale = det.get('crop_scale', 1.0) or 1.0
    x0 = det.get('crop_x0', 0)
    y0 = det.get('crop_y0', 0)
    return (x0 + cx / scale, y0 + cy / scale)


def _interpolated_ball_track(detections, start_frame, end_frame, max_gap_frames=3):
    """
    (frame, ball_center) for every frame in [start_frame, end_frame] with a
    ball detection, in original-frame coordinate space (see
    _center_in_original_space). Delegates to ball_tracker.py's constant-
    velocity Kalman filter: predicts through a gap up to max_gap_frames long
    (the ball vanishing for a frame or two right at contact is expected --
    see _find_gap_contact's comment -- and shouldn't kill a real departure
    trend) rather than plain linear fill, and rejects a measurement that
    doesn't fit the ball's established motion (a stray ball-shaped object
    elsewhere in frame) instead of blindly trusting every detection. Predicts
    on faith for up to max_gap_frames consecutive misses; beyond that there's
    no real basis to guess where the ball went, so the track breaks there
    rather than fabricating a trend indefinitely.
    """
    return track_ball(detections, start_frame, end_frame, _center_in_original_space, max_gap_frames)


def ball_departure_confirmed(detections, contact_frame, fps, window_sec=0.3):
    """
    Independent evidence a swing was a real strike: after the contact
    frame, does the ball's distance from the racket's position AT contact
    show a clear net-increasing trend (the ball moving away, i.e. actually
    struck), rather than sitting still or drifting closer (a stray
    ball-shaped detection unrelated to this swing)?

    Meant to rescue exactly the swings find_contact_frame() falls back to
    'wrist_velocity_fallback' for (no racket/ball proximity or occlusion-gap
    evidence at all) -- see verify_shot_contact.py's use of this. Never
    invents a signal from data that isn't there: returns
    (False, 0.0) whenever there's no racket detection at the contact frame
    to anchor on, or too few (interpolatable) ball detections afterward to
    judge a trend from.

    Returns (confirmed: bool, confidence: float).
    """
    contact_det = next((d for d in detections if d['frame'] == contact_frame), None)
    if not contact_det or not contact_det['racket_box']:
        return False, 0.0
    origin = _center_in_original_space(contact_det['racket_box'], contact_det)

    window = int(window_sec * fps)
    track = _interpolated_ball_track(detections, contact_frame, contact_frame + window)
    if len(track) < 3:  # too little real evidence to judge a trend from
        return False, 0.0

    distances = [math.hypot(c[0] - origin[0], c[1] - origin[1]) for _, c in track]

    # Net trend, not just first-vs-last -- robust to one noisy detection.
    # Count each consecutive step as "receding" or not, rather than fitting
    # a full regression: simple, and matches the coarse confidence bands
    # find_contact_frame()'s other methods already use.
    steps = [distances[i + 1] - distances[i] for i in range(len(distances) - 1)]
    receding_steps = sum(1 for s in steps if s > 0)
    fraction_receding = receding_steps / len(steps)

    if fraction_receding < 0.7:
        return False, 0.0

    # Same confidence range as ball_racket_proximity/ball_occlusion_gap
    # (0.3-1.0) -- scales with how clean the receding trend is, capped
    # below the strongest existing methods since this is corroborating
    # evidence for the weakest case, not a direct contact-frame pinpoint.
    confidence = round(min(0.7, 0.3 + 0.4 * fraction_receding), 3)
    return True, confidence


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
