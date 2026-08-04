"""
Fast, coarse camera-setup check -- catches genuinely broken framing (net not
visible/detected, or a banner mistaken for the net) and now also gives real
feedback on camera elevation via the trained net-keypoint model's
height_ratio signal (see infer_angle.py::height_ratio_from_keypoints).
This vertical signal was validated against real elevated footage this
session but is still based on only 2 known-elevated reference videos, so
'elevation_status' includes an 'uncertain' band rather than forcing a
confident call in the overlap zone -- the fence-mount tutorial remains the
primary defense (prevention), this is a best-effort secondary check.

Usage:
  python check_camera_setup.py <video_path>

Output (stdout): {"ok": bool, "angle": float|null, "confidence": float,
                   "height_ratio": float|null, "elevation_status": str,
                   "message": str}
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import infer_camera_angle, angle_label

MIN_CONFIDENCE = 0.5

ELEVATION_MESSAGES = {
    'level':              'Camera height looks good.',
    'uncertain':          "Camera height looks roughly OK, but we're not fully confident — double-check against the fence-mount guide.",
    'possibly_elevated':  'Your camera may be mounted too high — for best results, lower it closer to net height (see the fence-mount guide).',
    'unknown':            "Couldn't check camera height from this clip — make sure you followed the fence-mount guide.",
}


def check_camera_setup(video_path):
    angle, confidence, debug = infer_camera_angle(video_path)

    if angle is None:
        return {
            'ok': False, 'angle': None, 'confidence': 0.0,
            'height_ratio': None, 'elevation_status': 'unknown',
            'message': "Couldn't find the net in your video — try the fence-mount guide for a clearer shot.",
        }

    height_ratio = debug.get('height_ratio')
    elevation_status = debug.get('elevation_status', 'unknown')

    if confidence < MIN_CONFIDENCE:
        return {
            'ok': False, 'angle': angle, 'confidence': confidence,
            'height_ratio': height_ratio, 'elevation_status': elevation_status,
            'message': f"Camera setup looks uncertain ({angle_label(angle)}, low confidence) — see the fence-mount guide.",
        }

    return {
        'ok': True, 'angle': angle, 'confidence': confidence,
        'height_ratio': height_ratio, 'elevation_status': elevation_status,
        'message': f'Net detected OK ({angle_label(angle)}). {ELEVATION_MESSAGES.get(elevation_status, ELEVATION_MESSAGES["unknown"])}',
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'ok': False, 'angle': None, 'confidence': 0.0, 'height_ratio': None, 'elevation_status': 'unknown', 'message': 'No video path given'}))
        sys.exit(1)
    video_path = sys.argv[1]
    if not os.path.exists(video_path):
        print(json.dumps({'ok': False, 'angle': None, 'confidence': 0.0, 'height_ratio': None, 'elevation_status': 'unknown', 'message': f'Video not found: {video_path}'}))
        sys.exit(1)
    try:
        print(json.dumps(check_camera_setup(video_path)))
    except Exception as e:
        print(json.dumps({'ok': False, 'angle': None, 'confidence': 0.0, 'height_ratio': None, 'elevation_status': 'unknown', 'message': str(e)}))
        sys.exit(1)
