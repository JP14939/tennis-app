"""
Same measurement as audit_ball_confidence_at_contact.py (ball-detector
reliability right at the contact frame, on real saved user swings), but
against the Phase 3 fine-tuned weights (data/10b_ball_detection/
yolo_ball_run_v1/weights/best.pt) instead of the generic COCO model --
answers whether fine-tuning actually moved the needle on the 53.1%
detection / 0.40 avg confidence baseline before wiring it into production.

The fine-tuned model is single-class (ball only, class 0 -- see
prepare_ball_yolo_dataset.py), unlike the generic model's COCO classes
[38 racket, 32 ball], so this can't just reuse track_racket_and_ball()
with a swapped-in model (its classes=[RACKET_CLASS, BALL_CLASS] filter
would match nothing) -- this is the same per-frame detection loop, ball-only.

Usage:
  python audit_finetuned_ball_confidence.py [limit]
"""
import json
import os
import sqlite3
import sys

import cv2
from ultralytics import YOLO

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))

from paths import DATA_DIR, BACKEND_DIR, REPO_ROOT  # noqa: E402
from clip_urls import USER_CLIPS_DIR  # noqa: E402

DB_PATH = os.path.join(BACKEND_DIR, 'data', 'app.db')
FINETUNED_WEIGHTS = os.path.join(DATA_DIR, '10b_ball_detection', 'yolo_ball_run_v1', 'weights', 'best.pt')
BASELINE_WEIGHTS = os.path.join(REPO_ROOT, 'yolo11n.pt')

CONF_THRESHOLD = 0.15  # matches racket_tracker.py's, for a fair comparison
DEFAULT_LIMIT = 60
WINDOW_SEC = 0.15  # matches audit_ball_confidence_at_contact.py's


def _user_clip_path(user_clip_url):
    if not user_clip_url or not user_clip_url.startswith('/user-clips/'):
        return None
    rel = user_clip_url[len('/user-clips/'):]
    return os.path.join(USER_CLIPS_DIR, *rel.split('/'))


def best_ball_conf_in_window(model, clip_path, contact_time_sec, ball_class_id):
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not fps or total <= 0:
        cap.release()
        return None

    contact_frame = round(contact_time_sec * fps)
    window = max(1, int(WINDOW_SEC * fps))
    lo, hi = max(0, contact_frame - window), min(total - 1, contact_frame + window)

    cap.set(cv2.CAP_PROP_POS_FRAMES, lo)
    best_conf = None
    for idx in range(lo, hi + 1):
        ret, frame = cap.read()
        if not ret:
            break
        kwargs = {'conf': CONF_THRESHOLD, 'verbose': False}
        if ball_class_id is not None:
            kwargs['classes'] = [ball_class_id]
        results = model.predict(frame, **kwargs)
        for box in results[0].boxes:
            conf = float(box.conf[0])
            if best_conf is None or conf > best_conf:
                best_conf = conf
    cap.release()
    return {'detected': best_conf is not None, 'best_conf': round(best_conf, 3) if best_conf is not None else None}


def run_audit(model, ball_class_id, clips, limit):
    results = []
    for i, (analysis_id, clip_path, contact_time_sec) in enumerate(clips[:limit], 1):
        print(f'[{i}/{min(limit, len(clips))}] analysis {analysis_id}...', file=sys.stderr)
        try:
            r = best_ball_conf_in_window(model, clip_path, contact_time_sec, ball_class_id)
        except Exception as e:
            print(f'  FAILED: {e}', file=sys.stderr)
            continue
        if r is None:
            continue
        r['analysis_id'] = analysis_id
        results.append(r)
        print(f"  {'conf=' + str(r['best_conf']) if r['detected'] else 'NOT DETECTED'}", file=sys.stderr)

    detected = [r for r in results if r['detected']]
    total = len(results)
    detected_n = len(detected)
    avg_conf = round(sum(r['best_conf'] for r in detected) / detected_n, 3) if detected_n else None
    return {
        'total_checked': total,
        'detected_at_contact': detected_n,
        'detected_pct': round(100 * detected_n / total, 1) if total else None,
        'avg_conf_when_detected': avg_conf,
    }


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LIMIT

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT id, result_json FROM analyses ORDER BY id DESC LIMIT ?', (limit * 3,)).fetchall()
    conn.close()

    clips = []
    for row in rows:
        if len(clips) >= limit:
            break
        try:
            result = json.loads(row['result_json'])
        except (json.JSONDecodeError, TypeError):
            continue
        contact_time_sec = result.get('contact_time_sec')
        clip_path = _user_clip_path(result.get('user_clip_url'))
        if contact_time_sec is None or not clip_path or not os.path.exists(clip_path):
            continue
        clips.append((row['id'], clip_path, contact_time_sec))

    print(f'Auditing {len(clips)} real swings against BOTH models (same clips, fair comparison)...', file=sys.stderr)

    print('\n=== Fine-tuned (Phase 3) ===', file=sys.stderr)
    finetuned_model = YOLO(FINETUNED_WEIGHTS)
    finetuned_result = run_audit(finetuned_model, None, clips, limit)  # single-class, no filter needed

    print('\n=== Baseline (generic yolo11n.pt, COCO sports-ball class 32) ===', file=sys.stderr)
    baseline_model = YOLO(BASELINE_WEIGHTS)
    baseline_result = run_audit(baseline_model, 32, clips, limit)

    print(json.dumps({'finetuned': finetuned_result, 'baseline': baseline_result}, indent=2))


if __name__ == '__main__':
    main()
