"""Phase C -- shared "visual contact evidence" pass.

Runs the geometric contact pipeline (pose wrist-peak anchor -> YOLO racket/ball
tracking -> racket_tracker.find_contact_frame + contact_frame_meta + a wrist
velocity/accel/jerk profile) and returns a row of the same shape
contact_frame_training_log.log_example() / train_contact_frame_model.
predict_contact_offset() expect.

Two callers share this so the feature computation lives once:
  - build_contact_student_dataset.py  (offline: build the student's training set)
  - compare_swing.py                  (live: audioless auto-detect fallback, C.4)

Landmarks are expected in name->dict form ({'right_wrist': {'x','y',
'visibility',...}, ...}) -- the shape extract_user_poses() returns and
build_contact_student_dataset normalises to. Uses the non-cropped
track_racket_and_ball() (not verify_shot_contact's cropped variant) so the
evidence matches what the offset model was trained on.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import racket_tracker as rt  # noqa: E402
from racket_tracker import find_contact_frame, contact_frame_meta  # noqa: E402

# YOLO only around the anchor -- find_contact_frame looks +-0.3s, give it slack.
TRACK_MARGIN_SEC = 0.8


def wrist_kinematics(frames, anchor_idx, fps):
    """velocity / accel / jerk of the dominant wrist around the anchor, plus
    the offset (frames) from the anchor to the peak-deceleration frame -- the
    hand brakes hard at impact, which the speed-peak anchor ignores.

    `frames`: list of {'landmarks': name->dict-or-None}. `anchor_idx`: index
    into that list. Returns {} if there isn't enough wrist signal.
    """
    def speed_series(name):
        s, prev = [0.0], None
        for fr in frames:
            lm = fr.get('landmarks')          # name->dict (or None)
            d = lm.get(name) if lm else None
            if d and prev and d.get('visibility', 1) > 0.5 and prev.get('visibility', 1) > 0.5:
                s.append(math.hypot(d['x'] - prev['x'], d['y'] - prev['y']))
            else:
                s.append(s[-1] if s else 0.0)
            prev = d
        return s[1:]

    rs, ls = speed_series('right_wrist'), speed_series('left_wrist')
    sp = rs if sum(rs) >= sum(ls) else ls
    if len(sp) < 5:
        return {}
    # light smoothing
    sm = [sum(sp[max(0, i - 1):i + 2]) / len(sp[max(0, i - 1):i + 2]) for i in range(len(sp))]
    a = anchor_idx if 0 <= anchor_idx < len(sm) else len(sm) // 2
    accel = [sm[i + 1] - sm[i] for i in range(len(sm) - 1)]
    jerk = [accel[i + 1] - accel[i] for i in range(len(accel) - 1)]
    # only look for the braking event within ~0.35s of the speed peak -- past
    # that it's follow-through noise, not the impact.
    win = max(2, int(0.35 * fps / 3))
    lo, hi = max(0, a - win), min(len(accel), a + win + 1)
    decel_i = min(range(lo, hi), key=lambda i: accel[i]) if lo < hi else a
    peak = max(sm[max(0, a - win):a + win + 1] or [1e-9]) or 1e-9
    drop_i = next((i for i in range(a, min(len(sm), a + win + 1)) if sm[i] < 0.5 * peak), None)
    return {
        'wrist_speed_at_anchor': round(sm[a], 5) if a < len(sm) else None,
        'wrist_accel_at_anchor': round(accel[a], 5) if a < len(accel) else None,
        'wrist_jerk_at_anchor': round(jerk[a], 5) if a < len(jerk) else None,
        'wrist_decel_offset_f': (decel_i - a) * 3,          # *3: pose sampled every 3
        'wrist_halfspeed_offset_f': ((drop_i - a) * 3) if drop_i is not None else None,
    }


def compute_contact_evidence(video_path, frames, fps, anchor_frame, anchor_list_idx):
    """Run the live visual contact pipeline on a clip window.

    `frames`: name->dict-landmark list (see module docstring).
    `anchor_frame`: the wrist-velocity-peak frame NUMBER (the rough anchor).
    `anchor_list_idx`: that frame's index within `frames` (for wrist_kinematics).

    Returns a dict {student_frame, student_confidence, student_method,
    student_meta} -- the shape features_from_record() / log_example() consume --
    or None if there's no usable racket/ball evidence.
    """
    lo = int(anchor_frame - TRACK_MARGIN_SEC * fps)
    hi = int(anchor_frame + TRACK_MARGIN_SEC * fps)
    dets, _ = rt.track_racket_and_ball(video_path, frame_range=(lo, hi))
    if not dets:
        return None

    frame, conf, method = find_contact_frame(dets, anchor_frame, fps)
    meta = contact_frame_meta(dets, anchor_frame, fps)
    meta.update(wrist_kinematics(frames, anchor_list_idx, fps))
    meta['anchor_frame'] = anchor_frame
    return {
        'student_frame': frame,
        'student_confidence': conf,
        'student_method': method,
        'student_meta': meta,
    }
