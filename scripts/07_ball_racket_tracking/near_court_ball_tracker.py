"""
Near-side ball detection: crop small around the player + racket + a cone
toward the net, upscale, and run the fine-tuned ball detector there.

Why: the ball detector was trained at imgsz 320 on ~28x29px ball boxes and is
scale-brittle. On the live path it currently runs on the FULL uncropped frame
at imgsz 320 -- `calibrate_ball_inference_scale.py` measured that a small
crop -> upscale to 640 -> detect at imgsz 224 is markedly better
(detect 0.94 / IoU 0.62 / FP 0.10 vs 0.89 / 0.59 / 0.08 full-frame). This
module applies that, scoped to the NEAR side of the net (image-y > net_y in a
"back" view -- user filming their own swing). The far side is left to physics
(ball_speed's constant-velocity extrapolation), not detection.

Output shape is identical to `racket_tracker.track_racket_and_ball` -- a
drop-in for `_interpolated_ball_track` / `_center_in_original_space`. Crop
metadata (`crop_scale`/`crop_x0`/`crop_y0`) uses the same convention
`verify_shot_contact.py` and `ball_roi_tracker.py` already do.

Import direction: consumers -> near_court_ball_tracker -> racket_tracker /
crop_to_subject / infer_angle. Nothing imports back into this module.
"""
import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
for _sub in ('12_video_crop', '05_angle_detection', '02_pose_extraction'):
    _p = os.path.join(SCRIPTS_DIR, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import racket_tracker as rt  # noqa: E402
from racket_tracker import detect_ball  # noqa: E402

# imgsz for the cropped detector call -- the regime-B winner from
# calibrate_ball_inference_scale.py (re-confirmed in eval_near_court_ball_detection.py).
NEAR_COURT_IMGSZ_DEFAULT = 224
# Upscale target for the crop's long side (matches verify_shot_contact.UPSCALE_TARGET_PX
# and calibrate_ball_inference_scale.UPSCALE_TARGET_PX -- keep the three equal).
UPSCALE_TARGET_PX = 640
# Long-side cap on the crop (original px). Past this the upscale to 640 becomes
# a downscale and the ball is shrunk below the ~28px training scale. Tune from
# the eval. At the cap, upscale factor is ~0.7 (ball ~28px -> ~20px).
CROP_MAX_LONG_SIDE_PX = 900
# Tight player bbox: fraction of body span added on each side (NOT
# crop_to_subject.MARGIN=1.6, which is tuned for the cosmetic video crop and
# is far too loose here -- it made the raw bbox exceed the size cap on every
# 1080p frame, so the near-court crop never fired).
TIGHT_BBOX_MARGIN = 0.20
# How far net-ward (as a multiple of player height) to extend the crop, capped
# by net_y when it's known and by CROP_MAX_LONG_SIDE_PX always.
NET_REACH_PLAYER_HEIGHTS = 1.3
# Pull the net-ward edge this fraction of frame height short of net_y (don't
# spend crop on the far side).
NET_MARGIN_FRAC = 0.04
VIS_MIN = 0.5


def _crop_and_upscale_rect(frame, rect):
    """Crop `frame` to `rect` (x0,y0,x1,y1 px) and upscale so the long side
    reaches UPSCALE_TARGET_PX (never downscale). Returns (crop, scale, x0, y0)
    or None if the rect is degenerate. Same math as
    calibrate_ball_inference_scale._crop_and_upscale, minus the _frame_bbox
    step -- keep them in sync."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = [int(round(v)) for v in rect]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = frame[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    scale = UPSCALE_TARGET_PX / max(cw, ch) if max(cw, ch) < UPSCALE_TARGET_PX else 1.0
    if scale != 1.0:
        crop = cv2.resize(crop, (max(1, int(cw * scale)), max(1, int(ch * scale))))
    return crop, scale, x0, y0


def tight_player_bbox(landmarks, w, h, margin=TIGHT_BBOX_MARGIN):
    """Player bbox in px from name->None MediaPipe landmarks (calibrate's
    _landmarks_for_frame shape) or dict landmarks. Small margin -- unlike
    crop_to_subject._frame_bbox (MARGIN=1.6, cosmetic video crop)."""
    xs, ys = [], []
    for lm in landmarks or []:
        v = lm.get('visibility', 1.0)
        if v is None or v >= VIS_MIN:
            xs.append(lm['x'] * w)
            ys.append(lm['y'] * h)
    if not xs:
        return None
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    mx, my = (x1 - x0) * margin, (y1 - y0) * margin
    return (x0 - mx, y0 - my, x1 + mx, y1 + my)


def _near_court_crop_rect(player_bbox, net_y_px, left_x_px, right_x_px,
                          view_direction, w, h):
    """A crop that hugs the player but reaches net-ward to cover the near-side
    ball flight. Returns (x0,y0,x1,y1) in original px, or None only when the
    approach doesn't apply (not back-view, or no player bbox). Oversized
    geometry is CLAMPED to CROP_MAX_LONG_SIDE_PX, not rejected.

    Back view only: the ball travels UP the frame (toward smaller y) after
    contact, so extend the top edge net-ward and leave the bottom (the
    player's feet) where it is.
    """
    if view_direction != 'back' or player_bbox is None:
        return None
    px0, py0, px1, py1 = player_bbox
    pw, ph = px1 - px0, py1 - py0
    if pw <= 0 or ph <= 0:
        return None

    # net-ward (up) reach: a multiple of player height, but stop short of net_y
    reach = NET_REACH_PLAYER_HEIGHTS * ph
    y0 = py0 - reach
    if net_y_px is not None:
        y0 = max(y0, net_y_px - NET_MARGIN_FRAC * h)
    y1 = py1
    # widen -- the ball fans out cross-court after contact
    extend = 0.5 * pw
    x0, x1 = px0 - extend, px1 + extend

    # clamp to the size cap: trim the net-ward extension first (keep the feet),
    # then narrow the cone, never below the player bbox itself
    if (y1 - y0) > CROP_MAX_LONG_SIDE_PX:
        y0 = min(py0, y1 - CROP_MAX_LONG_SIDE_PX)
    if (x1 - x0) > CROP_MAX_LONG_SIDE_PX:
        cx = (px0 + px1) / 2
        half = max(pw / 2, CROP_MAX_LONG_SIDE_PX / 2)
        x0, x1 = min(px0, cx - half), max(px1, cx + half)

    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return (int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)))


def _union_bbox(bboxes):
    xs0, ys0, xs1, ys1 = [], [], [], []
    for b in bboxes:
        if b is None:
            continue
        xs0.append(b[0]); ys0.append(b[1]); xs1.append(b[2]); ys1.append(b[3])
    if not xs0:
        return None
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _pose_bbox_from_contact_frame(video_path, frame_idx, w, h):
    """Single-frame pose bbox for the standalone path (no poses handed in)."""
    try:
        from infer_angle import create_landmarker, _run_landmarker  # noqa: PLC0415
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        lm = _run_landmarker(frame, create_landmarker())
        if lm is None:
            return None
        landmarks = [{'x': p.x, 'y': p.y, 'visibility': p.visibility} for p in lm]
        return tight_player_bbox(landmarks, w, h)
    except Exception:  # noqa: BLE001 -- best effort; caller falls back
        return None


def track_ball_near_court(video_path, frame_range, static_bbox=None, net_line=None,
                          view_direction='back', imgsz=NEAR_COURT_IMGSZ_DEFAULT):
    """Ball detections over frame_range from a near-court crop. Same return
    shape as racket_tracker.track_racket_and_ball: (detections, fps) where each
    detection is {frame, racket_box, racket_conf, ball_box, ball_conf,
    crop_scale, crop_x0, crop_y0}. racket_* are always None here (ball-only).

    static_bbox: player region in ORIGINAL px (x0,y0,x1,y1). If None, a
      single-frame pose bbox is taken from the first frame of the range.
    net_line: (left_x, right_x, net_y) normalised [0,1], or None.
    view_direction: 'back' | 'front' | 'unknown'.

    Fallback chain, decided once:
      1. near-court crop  (back view + net line + pose bbox, within size cap)
      2. plain player-bbox crop (regime B)  (pose bbox present)
      3. full frame @ 320  (delegate to track_racket_and_ball)
    """
    start, end = frame_range
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video_path}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    bbox = static_bbox or _pose_bbox_from_contact_frame(video_path, start, w, h)

    rect = None
    mode = 'full_frame'
    if bbox is not None:
        net_px = None
        if net_line is not None:
            lx, rx, ny = net_line
            net_px = (lx * w, rx * w, ny * h)
        if net_px is not None:
            rect = _near_court_crop_rect(bbox, net_px[2], net_px[0], net_px[1],
                                         view_direction, w, h)
        if rect is not None:
            mode = 'near_court'
        else:
            # regime B: the plain player bbox, clamped to frame
            bx0, by0, bx1, by1 = bbox
            rect = (max(0, bx0), max(0, by0), min(w, bx1), min(h, by1))
            if rect[2] - rect[0] >= 8 and rect[3] - rect[1] >= 8:
                mode = 'pose_bbox'
            else:
                rect = None

    if rect is None:
        cap.release()
        return rt.track_racket_and_ball(video_path, frame_range=frame_range)

    detections = []
    idx = max(0, start)
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    while idx < end:
        ok, frame = cap.read()
        if not ok:
            break
        cu = _crop_and_upscale_rect(frame, rect)
        if cu is None:
            detections.append({'frame': idx, 'racket_box': None, 'racket_conf': None,
                               'ball_box': None, 'ball_conf': None})
            idx += 1
            continue
        crop, scale, x0, y0 = cu
        box, conf = detect_ball(crop, imgsz=imgsz)
        detections.append({
            'frame': idx, 'racket_box': None, 'racket_conf': None,
            'ball_box': box, 'ball_conf': conf,
            'crop_scale': scale, 'crop_x0': x0, 'crop_y0': y0,
        })
        idx += 1
    cap.release()
    return detections, fps
