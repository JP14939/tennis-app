"""
Two-pass ROI re-detection ball tracker (pass 2).

Whole-frame YOLO detection stays pass 1 (racket_tracker.track_racket_and_ball).
This module is pass 2: fit the constant-velocity Kalman (ball_tracker) to
pass-1's clean detections, then RE-RUN the ball detector in a small crop around
the filter's predicted ball position for the frames pass 1 missed (or gated as
an outlier). A small crop gives the detector both the ~28x29px object scale it
was trained at AND almost no background to hallucinate from -- the reason a
blanket bigger imgsz was rejected (calibrate_ball_inference_scale.py: FP rate
8% -> 99% past imgsz~480).

Every ROI recovery is Mahalanobis-gated against the filter before it's
accepted -- that gate is the false-positive-safety argument: a hallucinated box
that doesn't sit where a constant-velocity ball would be is logged and dropped,
not added.

Import direction is one-way:
  ball_speed / compare_swing / render_ball_overlay / eval
    -> ball_roi_tracker  (this)
      -> racket_tracker (detect_ball, _center_in_original_space)
        -> ball_tracker (track_ball, track_ball_states, pure numpy)
racket_tracker does NOT import this module -- consumers call refine_ball_track()
directly with the pass-1 `detections` they already produce.

Constant-velocity only for v1; a gravity/parabola flight model is a deliberate
later refinement (see ball_tracker.py's module docstring and docs/future-ideas).
"""
import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cv2  # noqa: E402

from ball_tracker import OUTLIER_GATE_SIGMAS, track_ball, track_ball_states  # noqa: E402
from racket_tracker import _center_in_original_space, detect_ball  # noqa: E402

# ---------------------------------------------------------------------------
# Config (calibrated in eval_ball_roi_tracker.py stage 4)
# ---------------------------------------------------------------------------
# Pass 1 must have found at least this much of a real track for a motion model
# to be worth fitting -- below it, pass 2 returns pass-1 behaviour unchanged so
# nothing regresses on clips where there was never a ball to model.
MIN_BOOTSTRAP = 3          # accepted pass-1 ball detections
MIN_SPAN_FRAMES = 4        # frame span they cover

# Only re-detect a frame within this many frames of an ACCEPTED pass-1
# detection -- past that the constant-velocity prediction has drifted too far
# to crop tightly and the ROI just hallucinates on empty frames (measured:
# unrestricted candidates inflated fp_rate on ball-absent frames). Short gaps
# at contact / brief occlusions -- the cases worth recovering -- are all
# within a few frames of a real detection.
MAX_CANDIDATE_GAP = 3

# ROI half-size (px, original-frame space) = BALL_HALF_PX + MOTION_K*speed
#                                            + GATE_SIGMAS*sqrt(max eig of P2),
# clamped to [ROI_MIN_HALF, ROI_MAX_HALF].
BALL_HALF_PX = 15.0
MOTION_K = 1.0
GATE_SIGMAS = 3.0
ROI_MIN_HALF = 40.0
ROI_MAX_HALF = 160.0

ROI_UPSCALE_TARGET = 160   # only-upscale (never downscale) a crop to this max side; None disables
ROI_IMGSZ_DEFAULT = 160    # YOLO imgsz for the crop (pending stage-4 calibration)
ROI_CONF = 0.30            # detector conf on a normal ROI crop (raised from 0.15: a low
                           # conf on a small upscaled crop hallucinates on ball-absent frames)
ROI_MIN_BOX_CONF = 0.35    # a recovery below this detector confidence is logged, not added

# Skip a candidate whose predicted position covariance trace exceeds this --
# the ROI would be effectively full-frame-sized, so a crop buys nothing.
MAX_PRED_COV = 4000.0

# Accept an ROI recovery only if its Mahalanobis d^2 against (pred_pos,
# pred_cov + R) is within this. Kept at the base tracker's own gate
# (OUTLIER_GATE_SIGMAS**2) rather than looser -- the ROI crop already
# constrains where a box can land, so a slack gate only lets clutter in
# (measured: a loose gate inflated fp_rate on ball-absent frames).
ACCEPT_GATE = OUTLIER_GATE_SIGMAS ** 2
_ACCEPT_R_VAR = 16.0       # measurement-noise var added to pred_cov for the accept gate

# Widened window around contact: the ball is occluded/blurred by the racket, a
# constant-velocity prediction is least valid, so pad the ROI, loosen the gate,
# drop the conf, and keep any recovery OUT of contact detection.
CONTACT_WINDOW_SEC = 0.08
CONTACT_GAP_GUARD_SEC = 0.06
CONTACT_MOTION_K = 2.5
CONTACT_GATE_SIGMAS = 5.0
ROI_MAX_HALF_CONTACT = 260.0
CONTACT_CONF = 0.08

BUDGET_REDETECTIONS = 60


@dataclass
class RefinedBallResult:
    filled_track: list = field(default_factory=list)        # [(frame,(x,y))] -- drop-in for _interpolated_ball_track
    filled_track_dense: list = field(default_factory=list)  # every frame linearly filled -- for the overlay
    augmented_dets: list = field(default_factory=list)      # pass-1 dicts + ROI recoveries, each 'ball_source'-tagged
    contact_safe_dets: list = field(default_factory=list)   # augmented EXCEPT ROI recoveries inside the contact guard
    redetect_log: list = field(default_factory=list)        # per-attempt diagnostics
    bootstrapped: bool = False                              # False => pass-1 behaviour returned unchanged


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _snap32(n):
    """ultralytics silently rounds imgsz up to a multiple of the model stride
    (32) and warns -- snap here so the value we log is the value used."""
    return max(32, int(round(n / 32)) * 32)


def _frame_span(detections):
    frames = [d['frame'] for d in detections]
    return (min(frames), max(frames)) if frames else (0, -1)


def _densify(track, start_frame, end_frame):
    """Linear-fill every integer frame in [start, end] from a sparse
    [(frame,(x,y))] track. Endpoints held constant outside the track's span."""
    if not track:
        return []
    pts = sorted(track)
    out = []
    for f in range(start_frame, end_frame + 1):
        if f <= pts[0][0]:
            out.append((f, pts[0][1]))
            continue
        if f >= pts[-1][0]:
            out.append((f, pts[-1][1]))
            continue
        # find bracketing points
        for i in range(len(pts) - 1):
            (fa, pa), (fb, pb) = pts[i], pts[i + 1]
            if fa <= f <= fb:
                if fb == fa:
                    out.append((f, pa))
                else:
                    w = (f - fa) / (fb - fa)
                    out.append((f, (pa[0] + w * (pb[0] - pa[0]),
                                    pa[1] + w * (pb[1] - pa[1]))))
                break
    return out


def _pass1_ball_frames(detections, start_frame, end_frame):
    """{frame: det} for frames that carry a pass-1 ball_box in [start, end]."""
    return {d['frame']: d for d in detections
            if start_frame <= d['frame'] <= end_frame and d.get('ball_box')}


def _states_by_frame(states):
    return {s['frame']: s for s in states}


def _combine_states(fwd, bwd):
    """Per-frame pick of the lower position-covariance-trace estimate between
    the forward and backward passes. Returns {frame: {'pos','cov_trace'}}."""
    out = {}
    for src in (fwd, bwd):
        for s in src:
            tr = s['cov'][0][0] + s['cov'][1][1]
            cur = out.get(s['frame'])
            if cur is None or tr < cur['cov_trace']:
                out[s['frame']] = {'pos': s['pos'], 'cov': s['cov'], 'cov_trace': tr}
    return out


def _backward_states(detections, start_frame, end_frame, max_gap_frames):
    """track_ball_states over reversed frame order. The CV filter run on the
    reversed sequence recovers the (negated) velocity and the correct
    positions with no filter-math change -- gives predictions for frames
    BEFORE the forward filter's first lock (ball missed on the approach)."""
    span = start_frame + end_frame
    rev = []
    for d in detections:
        if start_frame <= d['frame'] <= end_frame:
            rd = dict(d)
            rd['frame'] = span - d['frame']
            rev.append(rd)
    rev_states = track_ball_states(rev, start_frame, end_frame,
                                  _center_in_original_space, max_gap_frames)
    for s in rev_states:
        s['frame'] = span - s['frame']
    return rev_states


def _roi_half(pred_cov, speed, *, motion_k, gate_sigmas, max_half):
    max_eig = max(np.linalg.eigvalsh(np.array(pred_cov)))
    half = BALL_HALF_PX + motion_k * speed + gate_sigmas * math.sqrt(max(0.0, max_eig))
    return float(np.clip(half, ROI_MIN_HALF, max_half))


def _crop_box(px, py, half, frame_w, frame_h):
    x0 = int(round(max(0, px - half)))
    y0 = int(round(max(0, py - half)))
    x1 = int(round(min(frame_w, px + half)))
    y1 = int(round(min(frame_h, py + half)))
    return x0, y0, x1, y1


def _upscale(crop, target):
    if not target:
        return crop, 1.0
    ch, cw = crop.shape[:2]
    m = max(cw, ch)
    if m == 0 or m >= target:
        return crop, 1.0
    scale = target / m
    return cv2.resize(crop, (max(1, int(cw * scale)), max(1, int(ch * scale)))), scale


def _accept_recovery(recovered_center, pred_pos, pred_cov):
    """Mahalanobis d^2 of a recovered centre against (pred_pos, pred_cov + R).
    Returns (accepted: bool, d2: float)."""
    S = np.array(pred_cov) + np.diag([_ACCEPT_R_VAR, _ACCEPT_R_VAR])
    y = np.array(recovered_center) - np.array(pred_pos)
    d2 = float(y.T @ np.linalg.solve(S, y))
    return d2 <= ACCEPT_GATE, d2


def _read_frames(video_path, frame_numbers):
    """{frame_number: BGR ndarray} for the requested frames (sorted seek)."""
    out = {}
    if not frame_numbers:
        return out
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video_path}')
    try:
        for f in sorted(set(frame_numbers)):
            if f < 0:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ok, frame = cap.read()
            if ok:
                out[f] = frame
    finally:
        cap.release()
    return out


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def refine_ball_track(video_path, detections, fps, *, contact_frame=None,
                      max_gap_frames=4, roi_imgsz=None, backward_pass=True,
                      budget_redetections=BUDGET_REDETECTIONS):
    """Pass 2. `detections` is pass-1 output (racket_tracker.track_racket_and_ball).
    Returns a RefinedBallResult. Never raises for a "nothing to do" case -- a
    cold clip returns pass-1 behaviour unchanged (bootstrapped=False)."""
    roi_imgsz = _snap32(roi_imgsz or ROI_IMGSZ_DEFAULT)
    start_frame, end_frame = _frame_span(detections)

    def _unchanged():
        ft = track_ball(detections, start_frame, end_frame, _center_in_original_space, max_gap_frames)
        return RefinedBallResult(
            filled_track=ft,
            filled_track_dense=_densify(ft, start_frame, end_frame),
            augmented_dets=[dict(d) for d in detections],
            contact_safe_dets=[dict(d) for d in detections],
            redetect_log=[],
            bootstrapped=False,
        )

    if end_frame < start_frame:
        return _unchanged()

    # 1. Bootstrap gate ------------------------------------------------------
    fwd = track_ball_states(detections, start_frame, end_frame,
                            _center_in_original_space, max_gap_frames)
    accepted_frames = [s['frame'] for s in fwd if s['accepted']]
    if (len(accepted_frames) < MIN_BOOTSTRAP
            or (max(accepted_frames) - min(accepted_frames)) < MIN_SPAN_FRAMES):
        return _unchanged()

    pass1_ball = _pass1_ball_frames(detections, start_frame, end_frame)

    # 2. Forward fit: classify candidate frames ----------------------------
    fwd_by_frame = _states_by_frame(fwd)
    gated_frames = [
        f for f, s in fwd_by_frame.items()
        if not s['accepted'] and s['measurement'] is not None
        and s['mahalanobis_d2'] is not None
        and s['mahalanobis_d2'] > OUTLIER_GATE_SIGMAS ** 2
    ]
    if gated_frames:
        fwd = track_ball_states(detections, start_frame, end_frame,
                                _center_in_original_space, max_gap_frames,
                                predict_only_frames=gated_frames)
        fwd_by_frame = _states_by_frame(fwd)

    missed_frames = [f for f in range(start_frame, end_frame + 1)
                     if f not in pass1_ball]

    # 3. Backward pass ----------------------------------------------------
    bwd = (_backward_states(detections, start_frame, end_frame, max_gap_frames)
           if backward_pass else [])
    combined = _combine_states(fwd, bwd)

    # 4-6. ROI re-detect loop ------------------------------------------------
    guard = max(1, round(CONTACT_GAP_GUARD_SEC * (fps or 30.0)))
    cwin = max(1, round(CONTACT_WINDOW_SEC * (fps or 30.0)))

    def _in_contact_window(f):
        return contact_frame is not None and abs(f - contact_frame) <= cwin

    def _in_contact_guard(f):
        return contact_frame is not None and abs(f - contact_frame) <= guard

    accepted_sorted = sorted(accepted_frames)

    def _near_accepted(f):
        return min(abs(f - af) for af in accepted_sorted) <= MAX_CANDIDATE_GAP

    candidates = sorted(set(missed_frames) | set(gated_frames))
    # most-confident (smallest predicted covariance) first; only frames close
    # enough to a real detection for the CV prediction to still crop tight
    candidates = [f for f in candidates if f in combined and _near_accepted(f)]
    candidates.sort(key=lambda f: combined[f]['cov_trace'])

    frames_to_read = [f for f in candidates
                      if combined[f]['cov_trace'] <= MAX_PRED_COV][:budget_redetections]
    imgs = _read_frames(video_path, frames_to_read)

    recovered = {}      # frame -> detection dict (ROI recovery)
    dropped_gated = set()
    redetect_log = []
    spent = 0
    for f in candidates:
        if spent >= budget_redetections:
            break
        c = combined[f]
        if c['cov_trace'] > MAX_PRED_COV:
            redetect_log.append({'frame': f, 'skipped': 'pred_cov_too_large',
                                 'cov_trace': round(c['cov_trace'], 1)})
            continue
        img = imgs.get(f)
        if img is None:
            redetect_log.append({'frame': f, 'skipped': 'frame_unreadable'})
            continue

        h, w = img.shape[:2]
        px, py = c['pos']
        st = fwd_by_frame.get(f)
        speed = math.hypot(*st['vel']) if st else 0.0
        contact = _in_contact_window(f)
        half = _roi_half(
            c['cov'], speed,
            motion_k=CONTACT_MOTION_K if contact else MOTION_K,
            gate_sigmas=CONTACT_GATE_SIGMAS if contact else GATE_SIGMAS,
            max_half=ROI_MAX_HALF_CONTACT if contact else ROI_MAX_HALF,
        )
        x0, y0, x1, y1 = _crop_box(px, py, half, w, h)
        if x1 <= x0 or y1 <= y0:
            redetect_log.append({'frame': f, 'skipped': 'degenerate_crop'})
            continue
        crop = img[y0:y1, x0:x1]
        up_crop, up_scale = _upscale(crop, ROI_UPSCALE_TARGET)

        conf = CONTACT_CONF if contact else ROI_CONF
        spent += 1
        box, box_conf = detect_ball(up_crop, conf_threshold=conf, imgsz=roi_imgsz)
        if box is None and contact:
            # one imgsz step up before giving up in the hard window
            box, box_conf = detect_ball(up_crop, conf_threshold=conf,
                                        imgsz=_snap32(roi_imgsz * 1.5))

        entry = {'frame': f, 'crop': [x0, y0, x1, y1], 'half': round(half, 1),
                 'contact_window': contact, 'conf': conf, 'pred_pos': [round(px, 1), round(py, 1)],
                 'cov_trace': round(c['cov_trace'], 1)}

        if box is None:
            entry['result'] = 'no_detection'
            redetect_log.append(entry)
            if f in gated_frames:
                dropped_gated.add(f)
            continue

        if not contact and (box_conf is None or box_conf < ROI_MIN_BOX_CONF):
            entry['result'] = 'rejected_low_conf'
            entry['box_conf'] = round(box_conf, 3) if box_conf is not None else None
            redetect_log.append(entry)
            if f in gated_frames:
                dropped_gated.add(f)
            continue

        # crop-edge rejection (racket / clutter hugging the border)
        bw, bh = box[2] - box[0], box[3] - box[1]
        edge = 2.0
        crop_w, crop_h = up_crop.shape[1], up_crop.shape[0]
        if (box[0] <= edge or box[1] <= edge
                or box[2] >= crop_w - edge or box[3] >= crop_h - edge) and (bw > crop_w * 0.6 or bh > crop_h * 0.6):
            entry['result'] = 'rejected_crop_edge'
            redetect_log.append(entry)
            if f in gated_frames:
                dropped_gated.add(f)
            continue

        # map the crop-space box back to original-frame space for the gate
        det_stub = {'crop_scale': up_scale, 'crop_x0': x0, 'crop_y0': y0}
        rec_center = _center_in_original_space(box, det_stub)
        ok, d2 = _accept_recovery(rec_center, c['pos'], c['cov'])
        entry['recovered_center'] = [round(rec_center[0], 1), round(rec_center[1], 1)]
        entry['accept_d2'] = round(d2, 2)
        entry['box_conf'] = round(box_conf, 3) if box_conf is not None else None
        if not ok:
            entry['result'] = 'rejected_filter_gate'
            redetect_log.append(entry)
            if f in gated_frames:
                dropped_gated.add(f)
            continue

        source = ('roi_contact' if contact
                  else 'roi_gated' if f in gated_frames else 'roi_missed')
        entry['result'] = 'accepted'
        entry['ball_source'] = source
        redetect_log.append(entry)
        recovered[f] = {
            'frame': f,
            'racket_box': None, 'racket_conf': None,
            'ball_box': list(box), 'ball_conf': box_conf,
            'crop_scale': up_scale, 'crop_x0': x0, 'crop_y0': y0,
            'ball_source': source,
        }

    # 7. Assembly ---------------------------------------------------------
    # A pass-1 box is NEVER removed -- only ADDED to or replaced by a
    # filter-validated ROI recovery. A gated frame whose ROI found nothing
    # keeps its original box (dropping it regressed pass-1's detect_rate on
    # the real population; the CV filter still ignores it internally).
    by_frame = {d['frame']: dict(d) for d in detections}
    for d in by_frame.values():
        d.setdefault('ball_source', 'pass1' if d.get('ball_box') else None)
    for f, rec in recovered.items():
        if f in by_frame:
            by_frame[f].update({k: rec[k] for k in
                                ('ball_box', 'ball_conf', 'crop_scale', 'crop_x0', 'crop_y0', 'ball_source')})
        else:
            by_frame[f] = rec

    augmented = [by_frame[f] for f in sorted(by_frame)]

    # contact_safe: withhold ROI recoveries within the guard window so
    # _find_gap_contact still sees the ball vanish at contact (that gap IS the
    # signal). Genuine pass-1 detections in the window are kept.
    contact_safe = []
    for d in augmented:
        if ((d.get('ball_source') or '').startswith('roi_') and _in_contact_guard(d['frame'])):
            d = dict(d)
            d['ball_box'] = None
            d['ball_conf'] = None
            d['ball_source'] = 'roi_withheld_contact'
        contact_safe.append(d)

    filled = track_ball(augmented, start_frame, end_frame, _center_in_original_space, max_gap_frames)
    return RefinedBallResult(
        filled_track=filled,
        filled_track_dense=_densify(filled, start_frame, end_frame),
        augmented_dets=augmented,
        contact_safe_dets=contact_safe,
        redetect_log=redetect_log,
        bootstrapped=True,
    )
