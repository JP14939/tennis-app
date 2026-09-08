"""
Fast, coarse camera-setup check -- catches genuinely broken framing (net not
visible/detected, or a banner mistaken for the net) and flags a wrong-side
(front / heavily side-on) setup via the view gate.

Elevation retired (Section 8 item 2): the v10 net model has no post-base
keypoints, so `elevation_status` is always 'unknown' and no longer surfaced
in `message`. The key is still in the output shape for schema stability.

Usage:
  python check_camera_setup.py <video_path>

Output (stdout): {"ok": bool, "angle": float|null, "confidence": float,
                   "height_ratio": float|null, "elevation_status": str,
                   "framing_status": str, "message": str}
"""
import json
import os
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import (
    infer_camera_angle, angle_label, detect_view_direction, evaluate_view_usable,
)

MIN_CONFIDENCE = 0.5


def _detect_view_direction_for_video(video_path):
    """One mid-video frame through detect_view_direction() -- enough for the
    coarse behind/front call the view gate needs (infer_camera_angle already
    did the robust multi-frame work for the angle itself)."""
    try:
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
        ok, frame = cap.read()
        cap.release()
        if ok and frame is not None:
            return detect_view_direction(frame)
    except Exception:
        pass
    return 'unknown'

# Elevation retired (Section 8 item 2) -- kept only so nothing importing it
# breaks; every value is now '' and it is not folded into `message`.
ELEVATION_MESSAGES = {
    'level': '', 'uncertain': '', 'possibly_elevated': '', 'unknown': '',
}

# NOT surfaced in `message` here, deliberately -- see check_camera_setup_frame()
# in infer_angle.py (the live pre-recording path) for where this check is
# actually validated and live. Spot-checking this session against ~60 real
# swing clips found shoulder_tilt_deg gives clean, tight results (0-14 deg
# for the vast majority) when read from a frame BEFORE the swing starts
# (the live-calibration assumption: player standing still, positioning the
# camera) but produces real false positives when sampled from arbitrary
# points across an already-recorded swing clip (this function's actual
# input) -- a player rotating through their stroke gets misread as a
# tilted camera. `framing_status`/`stance_width_ratio`/`shoulder_tilt_deg`
# are still returned below as raw data (harmless, might be useful later),
# just not folded into the user-facing message on this path.
FRAMING_MESSAGES = {
    'ok': '', 'tilted': '', 'compressed_stance': '', 'unknown': '',
}


def check_camera_setup(video_path):
    angle, confidence, debug = infer_camera_angle(video_path)

    if angle is None:
        return {
            'ok': False, 'angle': None, 'confidence': 0.0,
            'height_ratio': None, 'elevation_status': 'unknown', 'framing_status': 'unknown',
            'message': "Couldn't find the net in your video — try the fence-mount guide for a clearer shot.",
        }

    height_ratio = debug.get('height_ratio')
    elevation_status = debug.get('elevation_status', 'unknown')
    framing_status = debug.get('framing_status', 'unknown')

    if confidence < MIN_CONFIDENCE:
        return {
            'ok': False, 'angle': angle, 'confidence': confidence,
            'height_ratio': height_ratio, 'elevation_status': elevation_status,
            'framing_status': framing_status,
            'message': f"Camera setup looks uncertain ({angle_label(angle)}, low confidence) — see the fence-mount guide.",
        }

    # Behind-the-baseline view gate -- same verdict compare_swing.py applies to
    # the analysed upload, surfaced here so the post-pick banner catches a
    # wrong-side setup before the user marks contact and submits.
    view_direction = _detect_view_direction_for_video(video_path)
    view_gate = evaluate_view_usable(view_direction, angle, confidence)
    if not view_gate['usable']:
        return {
            'ok': False, 'angle': angle, 'confidence': confidence,
            'height_ratio': height_ratio, 'elevation_status': elevation_status,
            'framing_status': framing_status,
            'view_direction': view_direction, 'view_reason': view_gate['reason'],
            'message': view_gate['message'],
        }

    return {
        'ok': True, 'angle': angle, 'confidence': confidence,
        'height_ratio': height_ratio, 'elevation_status': elevation_status,
        'framing_status': framing_status,
        'view_direction': view_direction, 'view_reason': None,
        'message': (
            f'Net detected OK ({angle_label(angle)}).'
            f'{FRAMING_MESSAGES.get(framing_status, "")}'
        ),
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'ok': False, 'angle': None, 'confidence': 0.0, 'height_ratio': None, 'elevation_status': 'unknown', 'framing_status': 'unknown', 'message': 'No video path given'}))
        sys.exit(1)
    video_path = sys.argv[1]
    if not os.path.exists(video_path):
        print(json.dumps({'ok': False, 'angle': None, 'confidence': 0.0, 'height_ratio': None, 'elevation_status': 'unknown', 'framing_status': 'unknown', 'message': f'Video not found: {video_path}'}))
        sys.exit(1)
    try:
        print(json.dumps(check_camera_setup(video_path)))
    except Exception as e:
        # Some underlying failures (e.g. "Cannot open video: <path>") echo
        # this process's own argv -- the full server-side upload path --
        # straight into the exception message, which then flows unmodified
        # through routes/calibration.js's nonzero_exit branch back to any
        # authenticated caller of POST /api/check-setup. Redact the known
        # argv path down to its basename before it leaves this process.
        message = str(e).replace(video_path, os.path.basename(video_path))
        print(json.dumps({'ok': False, 'angle': None, 'confidence': 0.0, 'height_ratio': None, 'elevation_status': 'unknown', 'framing_status': 'unknown', 'message': message}))
        sys.exit(1)
