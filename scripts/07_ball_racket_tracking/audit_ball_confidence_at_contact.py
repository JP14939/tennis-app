"""
Audits how reliable the generic (unfine-tuned) YOLO ball detector actually
is right at the contact frame, on REAL saved user swings -- not just the
pro database, which already has a stale audit
(data/07_audits/ball_visibility_audit.json, pro side only, 631/914
visible, avg conf 0.66) that may not reflect real user footage (different
camera quality/distance/motion blur than the pro clips).

Read-only measurement -- no pipeline/UI changes. Answers one question:
is the ball detector bad enough, specifically at the moment that matters
(contact), to justify the bigger fine-tuning investment flagged in
TODO_MANUAL.md's pipeline backlog (item 3)?

Usage:
  python audit_ball_confidence_at_contact.py [limit]
"""
import json
import os
import sqlite3
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paths import DATA_DIR, BACKEND_DIR  # noqa: E402
from clip_urls import USER_CLIPS_DIR  # noqa: E402
from racket_tracker import track_racket_and_ball  # noqa: E402

DB_PATH = os.path.join(BACKEND_DIR, 'data', 'app.db')
PRO_AUDIT_PATH = os.path.join(DATA_DIR, '07_audits', 'ball_visibility_audit.json')

DEFAULT_LIMIT = 60
# How close to the marked/detected contact frame counts as "at contact" --
# same order of magnitude as find_contact_frame()'s own default search
# window (0.3s), tight enough to be a real "at the moment of contact"
# measurement rather than "somewhere in the swing".
WINDOW_SEC = 0.15


def _user_clip_path(user_clip_url):
    if not user_clip_url or not user_clip_url.startswith('/user-clips/'):
        return None
    rel = user_clip_url[len('/user-clips/'):]
    return os.path.join(USER_CLIPS_DIR, *rel.split('/'))


def audit_one(clip_path, contact_time_sec):
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if not fps or total <= 0:
        return None

    contact_frame = round(contact_time_sec * fps)
    window = max(1, int(WINDOW_SEC * fps))
    lo, hi = max(0, contact_frame - window), min(total - 1, contact_frame + window)

    dets, _ = track_racket_and_ball(clip_path, frame_range=(lo, hi + 1))
    ball_dets = [d for d in dets if d['ball_box']]
    if not ball_dets:
        return {'detected': False, 'best_conf': None}

    best = max(ball_dets, key=lambda d: d['ball_conf'])
    return {'detected': True, 'best_conf': round(best['ball_conf'], 3)}


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LIMIT

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, result_json FROM analyses ORDER BY id DESC LIMIT ?', (limit * 3,)
    ).fetchall()
    conn.close()

    results = []
    checked = 0
    for row in rows:
        if checked >= limit:
            break
        try:
            result = json.loads(row['result_json'])
        except (json.JSONDecodeError, TypeError):
            continue

        contact_time_sec = result.get('contact_time_sec')
        clip_path = _user_clip_path(result.get('user_clip_url'))
        if contact_time_sec is None or not clip_path or not os.path.exists(clip_path):
            continue

        checked += 1
        print(f"[{checked}/{limit}] analysis {row['id']}...", file=sys.stderr)
        try:
            r = audit_one(clip_path, contact_time_sec)
        except Exception as e:
            print(f'  FAILED: {e}', file=sys.stderr)
            continue
        if r is None:
            continue
        r['analysis_id'] = row['id']
        results.append(r)
        tag = f"conf={r['best_conf']}" if r['detected'] else 'NOT DETECTED'
        print(f'  {tag}', file=sys.stderr)

    detected = [r for r in results if r['detected']]
    total = len(results)
    detected_n = len(detected)
    avg_conf = round(sum(r['best_conf'] for r in detected) / detected_n, 3) if detected_n else None

    pro_audit = None
    if os.path.exists(PRO_AUDIT_PATH):
        with open(PRO_AUDIT_PATH) as f:
            pro = json.load(f)
        pro_visible = [r for r in pro if r.get('ball_visible')]
        pro_audit = {
            'total': len(pro),
            'visible': len(pro_visible),
            'visible_pct': round(100 * len(pro_visible) / len(pro), 1) if pro else None,
            'avg_conf_when_visible': round(
                sum(r['best_ball_conf'] for r in pro_visible if r.get('best_ball_conf')) /
                max(1, sum(1 for r in pro_visible if r.get('best_ball_conf'))), 3
            ) if pro_visible else None,
        }

    summary = {
        'real_user_swings': {
            'total_checked': total,
            'detected_at_contact': detected_n,
            'detected_pct': round(100 * detected_n / total, 1) if total else None,
            'avg_conf_when_detected': avg_conf,
            'window_sec': WINDOW_SEC,
        },
        'pro_database_audit_for_comparison': pro_audit,
    }
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
