"""
Verifies wrist-velocity swing candidates against real racket/ball contact
evidence, so "a shot" means more than "the wrist moved fast" -- reuses
scripts/07_ball_racket_tracking/racket_tracker.py exactly as-is (pretrained
YOLO, standard COCO racket/ball classes, no custom training needed). That
module already exposes find_contact_frame(), which searches a small window
around a rough time estimate and returns a confidence + method -- today
it's only ever called from pro-database auditing scripts
(batch_validate_contact.py, audit_ball_visibility.py); this is the first
time it's applied to a candidate BEFORE deciding whether it's a real shot
at all, rather than after a shot is already assumed real.

Usage (as a library):
  from verify_shot_contact import verify_swings
  swings = verify_swings(video_path, swings, fps)
  # each swing dict now has 'contact_confidence' and 'contact_method'
"""
import os
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '12_video_crop'))

from racket_tracker import (  # noqa: E402
    track_racket_and_ball, find_contact_frame, ball_departure_confirmed,
    get_model, RACKET_CLASS, BALL_CLASS, CONF_THRESHOLD, _center,
)
from crop_to_subject import _frame_bbox  # noqa: E402

# A full wide court shot makes the ball a handful of pixels -- easy for a
# generic pretrained detector to miss entirely (confirmed empirically: on
# real match footage this produced both false accepts and false rejects,
# see the plan doc). Cropping tightly around the player's own pose bbox
# before running YOLO makes the ball/racket a much larger fraction of the
# frame. Reuses crop_to_subject.py's own bbox+margin logic exactly (same
# MARGIN=1.6 that was just tuned there to stop clipping the racket) so the
# two don't drift into different definitions of "tight crop around player".
UPSCALE_TARGET_PX = 640


def _crop_and_upscale(frame, frame_data):
    h, w = frame.shape[:2]
    bbox = _frame_bbox(frame_data.get('landmarks') if frame_data else None, w, h)
    if bbox is None:
        return frame, 1.0, 0, 0
    x0, y0, x1, y1 = [int(round(v)) for v in bbox]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return frame, 1.0, 0, 0
    crop = frame[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    scale = UPSCALE_TARGET_PX / max(cw, ch) if max(cw, ch) < UPSCALE_TARGET_PX else 1.0
    if scale != 1.0:
        crop = cv2.resize(crop, (max(1, int(cw * scale)), max(1, int(ch * scale))))
    return crop, scale, x0, y0


def track_racket_and_ball_cropped(video_path, frames_by_idx, frame_range, model=None):
    """
    Same output shape as racket_tracker.track_racket_and_ball(), but crops
    each frame tightly around the player's pose bbox (from already-extracted
    landmarks, no extra MediaPipe call needed) and upscales before running
    YOLO -- see module docstring for why. `frames_by_idx`: {frame_number:
    frame_data} from extract_poses() output, for looking up each frame's
    landmarks. Box coordinates in the returned detections are in each
    frame's own crop-pixel space, not the original frame -- fine for
    find_contact_frame(), which only ever compares racket/ball position
    *within* one frame, never across frames.
    """
    model = model or get_model()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video_path}')

    start, end = frame_range
    start = max(0, start)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)

    detections = []
    idx = start
    while idx < end:
        ret, frame = cap.read()
        if not ret:
            break
        crop, scale, x0, y0 = _crop_and_upscale(frame, frames_by_idx.get(idx))
        results = model.predict(crop, classes=[RACKET_CLASS, BALL_CLASS], conf=CONF_THRESHOLD, verbose=False)
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
            # Each frame's crop has its own offset/scale (tight-cropped to
            # that frame's own pose bbox) -- kept per-detection so
            # _racket_velocity_profile() can convert back to a shared
            # original-frame coordinate space before comparing ACROSS
            # frames. Comparisons WITHIN one frame (find_contact_frame)
            # don't need this -- crop-space is fine there.
            'crop_scale': scale, 'crop_x0': x0, 'crop_y0': y0,
        })
        idx += 1

    cap.release()
    return detections

def track_racket_tip_and_ball_cropped(video_path, frames_by_idx, frame_range):
    """
    Like track_racket_and_ball_cropped(), but uses the fine-tuned racket
    KEYPOINT model (track_racket_in_clip.py's _detect_racket_keypoints(),
    already proven live for body_rotation phase-scoring) for racket
    position instead of the generic COCO bounding box -- see the plan doc
    for why: a bbox spans handle-to-tip (~60cm of real ambiguity) and
    three different attempts to derive a clean motion signal from its
    centroid all failed on real footage. The racket 'tip' (falling back to
    left_edge/right_edge if tip wasn't predicted that frame) is where
    contact actually happens -- returned here as a zero-size point "box"
    so it plugs into find_contact_frame()/the trajectory fit unchanged.
    Ball detection stays the plain COCO detector (no fine-tuned ball model
    exists), on the same cropped-and-upscaled frame.
    """
    from track_racket_in_clip import _models, _detect_racket_keypoints

    racket_detector, kp_model = _models()
    ball_model = get_model()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video_path}')
    start, end = frame_range
    start = max(0, start)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)

    detections = []
    idx = start
    while idx < end:
        ret, frame = cap.read()
        if not ret:
            break
        crop, scale, x0, y0 = _crop_and_upscale(frame, frames_by_idx.get(idx))
        ch, cw = crop.shape[:2]

        kpts = _detect_racket_keypoints(crop, racket_detector, kp_model)
        racket_box = racket_conf = None
        if kpts:
            for name in ('tip', 'left_edge', 'right_edge'):
                if name in kpts:
                    px, py = kpts[name][0] * cw, kpts[name][1] * ch
                    racket_box = [px, py, px, py]
                    racket_conf = 0.5  # model doesn't expose a per-keypoint score; fixed placeholder
                    break

        ball_results = ball_model.predict(crop, classes=[BALL_CLASS], conf=CONF_THRESHOLD, verbose=False)
        ball_box = ball_conf = None
        for box in ball_results[0].boxes:
            conf = float(box.conf[0])
            if ball_conf is None or conf > ball_conf:
                ball_box, ball_conf = box.xyxy[0].tolist(), conf

        detections.append({
            'frame': idx,
            'racket_box': racket_box, 'racket_conf': racket_conf,
            'ball_box': ball_box, 'ball_conf': ball_conf,
            # See track_racket_and_ball_cropped()'s matching comment.
            'crop_scale': scale, 'crop_x0': x0, 'crop_y0': y0,
        })
        idx += 1

    cap.release()
    return detections


TRAJECTORY_HALF_WINDOW = 8   # frames on each side of the candidate to fit
TRAJECTORY_POLY_DEGREE = 3   # cubic -- enough to capture accel/decel through a swing, not so much it just interpolates the noise


def _racket_velocity_profile(detections, center_frame, half_window=TRAJECTORY_HALF_WINDOW,
                              degree=TRAJECTORY_POLY_DEGREE):
    """
    Fits a polynomial to the racket centroid's tracked (x, y) positions
    across the whole window (the real trajectory shape, not a couple of
    adjacent points) and differentiates it analytically for a smooth
    velocity curve. This replaced two earlier approaches that both broke on
    real footage: a raw adjacent-frame delta was dominated by single-frame
    YOLO box-position jitter (a static pre-serve hold measured *faster*
    than a real swing); a before/after windowed-average delta then
    over-corrected the other way, netting out to ~zero at real contact
    because contact often sits near where the racket's path curves
    (backswing into follow-through), not at a point of large net
    displacement across a wide baseline. A polynomial fit doesn't have
    either problem -- it uses every point in the window to find the
    trajectory's actual shape, and differentiating it gives real
    instantaneous speed at any frame, including exactly at contact.

    Returns (frames, speeds) arrays for every integer frame in the window
    (not just frames with a detection), or (None, None) if there isn't
    enough racket data in the window to fit reliably.

    Detections from the cropped tracking path (track_racket_and_ball_cropped
    / track_racket_tip_and_ball_cropped) carry each frame's own crop
    scale/offset ('crop_scale'/'crop_x0'/'crop_y0') -- every frame is cropped
    tight to THAT frame's own pose bbox, so raw crop-pixel coordinates are
    NOT comparable across frames (a player's bbox moving/resizing between
    frames shifts the crop's origin and scale independently of any real
    racket motion). Centers are converted back to a shared original-frame
    pixel space here before fitting -- previously this fit raw per-crop
    coordinates directly, producing a trajectory in a coordinate space that
    changed frame to frame, i.e. not a real trajectory at all. Detections
    without crop metadata (the non-cropped track_racket_and_ball() path)
    default to scale=1, offset=0 -- already in original-frame space.
    """
    import numpy as np

    dets = sorted(
        (d for d in detections if d['racket_box'] and abs(d['frame'] - center_frame) <= half_window),
        key=lambda d: d['frame'],
    )
    degree = min(degree, len(dets) - 1)
    if degree < 1:
        return None, None

    frames = np.array([d['frame'] for d in dets], dtype=float)

    def to_original_space(d):
        cx, cy = _center(d['racket_box'])
        scale = d.get('crop_scale', 1.0) or 1.0
        x0 = d.get('crop_x0', 0)
        y0 = d.get('crop_y0', 0)
        return (x0 + cx / scale, y0 + cy / scale)

    centers = [to_original_space(d) for d in dets]
    xs = np.array([c[0] for c in centers])
    ys = np.array([c[1] for c in centers])

    t0 = frames[0]
    t = frames - t0
    px = np.polyfit(t, xs, degree)
    py = np.polyfit(t, ys, degree)
    dpx = np.polyder(px)
    dpy = np.polyder(py)

    eval_frames = np.arange(frames[0], frames[-1] + 1)
    eval_t = eval_frames - t0
    vx = np.polyval(dpx, eval_t)
    vy = np.polyval(dpy, eval_t)
    speeds = np.hypot(vx, vy)
    return eval_frames, speeds


def _racket_speed_at(detections, contact_frame, half_window=TRAJECTORY_HALF_WINDOW):
    """
    (fitted speed at contact_frame, peak fitted speed anywhere in the
    window) from the polynomial trajectory fit -- both None if there's not
    enough data. A real strike should be near the window's fastest point,
    not near-zero relative to it.
    """
    frames, speeds = _racket_velocity_profile(detections, contact_frame, half_window)
    if frames is None:
        return None, None
    peak_speed = float(speeds.max())
    idx = list(frames).index(contact_frame) if contact_frame in frames else min(
        range(len(frames)), key=lambda i: abs(frames[i] - contact_frame))
    return float(speeds[idx]), peak_speed

# How far around the wrist-velocity peak to look for racket/ball evidence.
# Matches find_contact_frame's own default search window; the extra pad
# gives track_racket_and_ball's frame_range enough margin on both sides for
# that search to actually have detections to look at near the window edges.
SEARCH_WINDOW_SEC = 0.3
EXTRA_PAD_SEC = 0.5

# Candidates that never found any racket/ball evidence at all fall back to
# the wrist-velocity estimate with this exact confidence (racket_tracker.py's
# find_contact_frame() hardcodes 0.3 for that case) -- used as the default
# reject threshold. Chosen empirically against real match footage (see
# verify_shot_contact_report.py), not guessed.
DEFAULT_MIN_CONFIDENCE = 0.3


def verify_swings(video_path, swings, fps, frames=None, search_window_sec=SEARCH_WINDOW_SEC,
                   use_crop=True, use_keypoints=False):
    """
    Mutates and returns `swings` (list of dicts with 'peak_frame', from
    detect_swings.find_swing_peaks()) -- adds 'contact_confidence' and
    'contact_method' to each. A swing whose only "evidence" is the
    wrist-velocity peak itself gets contact_method='wrist_velocity_fallback'
    and the lowest confidence (0.3) -- the signal that it might not be a
    real shot, since no racket/ball data corroborated it.

    `frames`: the same per-frame pose list (with landmarks) already produced
    by extract_poses() for wrist-velocity detection -- passing it in lets
    this crop tightly around the player (see track_racket_and_ball_cropped)
    instead of running detection on the full wide court shot, which was
    confirmed empirically to miss the ball far too often. Falls back to the
    uncropped racket_tracker.track_racket_and_ball() if frames isn't given
    or use_crop=False.
    """
    frames_by_idx = {f['frame']: f for f in frames} if frames else None

    for sw in swings:
        peak_frame = sw['peak_frame']
        window_frames = int((search_window_sec + EXTRA_PAD_SEC) * fps)
        frame_range = (peak_frame - window_frames, peak_frame + window_frames)
        try:
            if use_keypoints and frames_by_idx:
                detections = track_racket_tip_and_ball_cropped(video_path, frames_by_idx, frame_range)
            elif use_crop and frames_by_idx:
                detections = track_racket_and_ball_cropped(video_path, frames_by_idx, frame_range)
            else:
                detections, _ = track_racket_and_ball(video_path, frame_range=frame_range)
            frame, conf, method = find_contact_frame(
                detections, peak_frame, fps, search_window_sec=search_window_sec)
            speed_at_contact = peak_speed = None
            if method in ('ball_racket_proximity',) or method.startswith('ball_occlusion_gap'):
                # Diagnostic only -- NOT used to reject the candidate. This
                # used to reclassify low speed-ratio matches to
                # 'static_hold(...)' + confidence 0.2 (a held/bounced ball
                # near a stationary racket, not a strike), but backtesting
                # against 213 logged Claude verdicts
                # (data/16_shot_verification/shot_contact_training_log.jsonl)
                # found that rule was wrong 63-83% of the time -- real
                # contact often lands well below the window's peak fitted
                # speed (peak tends to fall during follow-through, not at
                # the strike), so "not near peak speed" is not evidence of
                # "not a strike." Real racket/ball position evidence is now
                # kept as real evidence regardless of the speed ratio.
                speed_at_contact, peak_speed = _racket_speed_at(detections, frame)
            elif method == 'wrist_velocity_fallback':
                # No racket/ball proximity or occlusion-gap evidence at all
                # -- the one case filter_verified_swings() rejects outright.
                # Independent evidence: if the ball is then seen moving away
                # from the racket's position at this frame, that's real
                # corroboration of a strike even without proximity/occlusion
                # evidence pinpointing the exact contact instant. Upgrades
                # the method (so it survives filter_verified_swings() on its
                # own merits) rather than silently keeping the fallback
                # label with a raised confidence, so it's clear in the data
                # WHY this one was trusted.
                departed, departure_conf = ball_departure_confirmed(detections, frame, fps)
                if departed:
                    conf, method = departure_conf, 'ball_departure_confirmed'
        except Exception as e:
            frame, conf, method, speed_at_contact, peak_speed = peak_frame, 0.0, f'error: {e}', None, None
        # find_contact_frame()'s actual guessed frame was computed above but
        # never kept on the swing dict -- only confidence/method were. Added
        # for contact_frame_training_log.py (needs the real frame number as
        # the "student" side of a frame-distance comparison), purely
        # additive so existing callers reading contact_confidence/
        # contact_method are unaffected.
        sw['contact_frame_guess'] = frame
        sw['contact_confidence'] = conf
        sw['contact_method'] = method
        sw['racket_speed_at_contact'] = round(speed_at_contact, 1) if speed_at_contact is not None else None
        sw['racket_peak_speed'] = round(peak_speed, 1) if peak_speed is not None else None
    return swings


def filter_verified_swings(swings, min_confidence=DEFAULT_MIN_CONFIDENCE):
    """
    Drops candidates with no real evidence of an actual strike:
      - contact_method == 'wrist_velocity_fallback' -- no racket/ball
        detection corroborated the wrist-velocity spike at all.
      - contact_method starting with 'static_hold(...)' -- only possible on
        old logged data from before this rejection rule was removed (see
        verify_swings()'s module comment for why); verify_swings() no
        longer produces this method, kept here defensively so old
        already-logged records still parse the same way if ever re-run
        through this function.
      - contact_method starting with 'error:' -- verify_swings()'s except
        block sets this when racket/ball tracking itself raised (bad crop,
        model OOM, etc.), with contact_confidence forced to 0.0. Neither of
        the two conditions above matched this shape, so a tracking failure
        was previously KEPT as if it had real corroboration instead of
        being rejected like any other no-evidence candidate.
    A real ball_occlusion_gap, ball_racket_proximity, or
    ball_departure_confirmed match is kept regardless of its exact
    confidence value or how fast the racket was moving there.
    """
    return [
        sw for sw in swings
        if not (sw.get('contact_method') == 'wrist_velocity_fallback'
                and sw.get('contact_confidence', 0) <= min_confidence)
        and not str(sw.get('contact_method', '')).startswith('static_hold')
        and not str(sw.get('contact_method', '')).startswith('error:')
    ]
