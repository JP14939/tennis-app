"""
Audit pro_database.json's high-angle (>65 deg) entries.

infer_angle.py's infer_camera_angle() already uses a trained net-keypoint
model (yolo_pose_run_v3) as its PRIMARY net detector, only falling back to
the older Hough-line heuristic when the keypoint model doesn't find the net
-- so there's no separate "better model" to cross-check stored angles
against. What's actually useful to check, for the 20 entries currently
labeled >65 degrees:

  1. Which of them relied on the Hough fallback (net_detection_method ==
     'hough_heuristic') when computed -- inherently the less reliable
     signal, and exactly the failure mode this angle range is most prone
     to (a camera behind the baseline can look geometrically identical to
     a true side view either way, per infer_angle.py's documented
     limitation).
  2. Whether re-running infer_camera_angle() fresh today gives a
     meaningfully different angle than what's stored (data drift, or the
     stored value predates some fix).

This script only reports -- it does not edit pro_database.json. Flagged
entries get a saved frame (with keypoints drawn, when the keypoint model
found the net) for manual visual review.

Usage: python audit_high_angle_entries.py
"""
import json
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '05_angle_detection'))
from infer_angle import (  # noqa: E402
    infer_camera_angle, extract_frame, run_net_keypoint_model,
    create_landmarker, angle_label,
)

DB_PATH     = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'
OUT_JSON    = r'C:\Users\jackp\tennis_app\data\07_audits\high_angle_net_audit.json'
REVIEW_DIR  = r'C:\Users\jackp\tennis_app\data\07_audits\high_angle_review'
ANGLE_THRESHOLD = 65
DISAGREEMENT_DEG = 15

KEYPOINT_COLORS = {
    'net_top_left':   (255, 0, 0),
    'net_top_right':  (0, 255, 0),
    'left_post_base': (0, 165, 255),
    'right_post_base': (0, 0, 255),
}


def save_review_frame(entry_id, clip_path):
    """Grab the clip's middle frame, draw whatever net keypoints are found
    (if any), save for manual review. Returns the saved path."""
    cap = cv2.VideoCapture(clip_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    frame = extract_frame(clip_path, total // 2)

    kp = run_net_keypoint_model(frame)
    h, w = frame.shape[:2]
    vis = frame.copy()
    for name, (x, y) in kp.items():
        cv2.circle(vis, (int(x * w), int(y * h)), 8, KEYPOINT_COLORS.get(name, (255, 255, 255)), -1)
    if not kp:
        cv2.putText(vis, 'no keypoints detected (Hough fallback)', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    out_path = os.path.join(REVIEW_DIR, f'{entry_id}.jpg')
    cv2.imwrite(out_path, vis)
    return out_path


def main():
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(DB_PATH, encoding='utf-8') as f:
        db = json.load(f)

    high_angle = [e for e in db['entries']
                  if e.get('camera_angle') is not None and e['camera_angle'] > ANGLE_THRESHOLD]
    print(f'{len(high_angle)} entries with camera_angle > {ANGLE_THRESHOLD}')

    landmarker = create_landmarker()
    results = []
    flagged = []

    for i, entry in enumerate(high_angle, 1):
        clip_path = entry.get('clip_path')
        print(f'  [{i}/{len(high_angle)}] {entry["id"]}...', end=' ')
        if not clip_path or not os.path.exists(clip_path):
            print('clip missing, skipping')
            continue

        fresh_angle, fresh_conf, debug = infer_camera_angle(clip_path, landmarker=landmarker)
        method = debug.get('net_detection_method') if isinstance(debug, dict) else None
        stored_angle = entry['camera_angle']
        delta = round(abs(fresh_angle - stored_angle), 1) if fresh_angle is not None else None

        is_flagged = (method == 'hough_heuristic') or (delta is not None and delta > DISAGREEMENT_DEG) or fresh_angle is None

        row = {
            'id': entry['id'],
            'shot_type': entry['shot_type'],
            'stored_angle': stored_angle,
            'stored_confidence': entry.get('angle_confidence'),
            'fresh_angle': fresh_angle,
            'fresh_confidence': fresh_conf,
            'fresh_label': angle_label(fresh_angle) if fresh_angle is not None else None,
            'net_detection_method': method,
            'delta_deg': delta,
            'flagged': is_flagged,
        }

        if is_flagged:
            try:
                row['review_frame'] = save_review_frame(entry['id'], clip_path)
            except Exception as e:
                row['review_frame_error'] = str(e)
            flagged.append(row)
            print(f'FLAGGED (method={method}, stored={stored_angle}, fresh={fresh_angle}, delta={delta})')
        else:
            print(f'ok (method={method}, stored={stored_angle}, fresh={fresh_angle}, delta={delta})')

        results.append(row)

    landmarker.close()

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump({'threshold_deg': ANGLE_THRESHOLD, 'disagreement_threshold_deg': DISAGREEMENT_DEG,
                    'total_audited': len(results), 'total_flagged': len(flagged),
                    'entries': results}, f, indent=2)

    print(f'\n{len(flagged)}/{len(results)} entries flagged for manual review')
    for row in flagged:
        print(f"  {row['id']}: stored={row['stored_angle']} fresh={row['fresh_angle']} "
              f"method={row['net_detection_method']} -> {row.get('review_frame', row.get('review_frame_error'))}")
    print(f'\nSaved audit summary to {OUT_JSON}')
    print(f'Review frames saved to {REVIEW_DIR}')


if __name__ == '__main__':
    main()
