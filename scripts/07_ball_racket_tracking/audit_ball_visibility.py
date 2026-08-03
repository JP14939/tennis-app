"""
Audit every pro database entry: is the ball visible anywhere near the
estimated contact point? If not, we can't verify/calibrate that clip's
contact frame against the user's manually-marked contact frame, so it
should be excluded when rebuilding the database.

Does NOT delete any clip files — just produces a report used to filter
entries when the database is rebuilt.
"""
import json
import os

import cv2

from racket_tracker import track_racket_and_ball, get_model

DB_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'
OUT_PATH = r'C:\Users\jackp\tennis_app\data\07_audits\ball_visibility_audit.json'

# pre_sec from SHOT_WINDOWS in detect_swings.py — how far into the clip the
# estimated contact point sits
PRE_SEC = {'forehand': 1.0, 'backhand': 1.0, 'serve': 1.8}
SEARCH_WINDOW_SEC = 0.35

model = get_model('yolo11n.pt')


def audit_entry(entry):
    clip_path = entry.get('clip_path')
    if not clip_path or not os.path.exists(clip_path):
        return {'id': entry['id'], 'ball_visible': False, 'reason': 'clip_missing'}

    cap = cv2.VideoCapture(clip_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    pre_sec = PRE_SEC.get(entry['shot_type'], 1.0)
    contact_frame = round(pre_sec * fps)
    window = int(SEARCH_WINDOW_SEC * fps)

    dets, _ = track_racket_and_ball(clip_path, model=model,
                                     frame_range=(contact_frame - window, contact_frame + window))
    ball_frames = [d for d in dets if d['ball_box']]
    ball_visible = len(ball_frames) > 0
    best_ball_conf = max((d['ball_conf'] for d in ball_frames), default=None)

    return {
        'id': entry['id'],
        'shot_type': entry['shot_type'],
        'ball_visible': ball_visible,
        'ball_detections_in_window': len(ball_frames),
        'window_size_frames': len(dets),
        'best_ball_conf': round(best_ball_conf, 3) if best_ball_conf else None,
    }


def main():
    with open(DB_PATH) as f:
        db = json.load(f)

    results = []
    for i, entry in enumerate(db['entries']):
        r = audit_entry(entry)
        results.append(r)
        tag = 'OK  ' if r['ball_visible'] else 'MISS'
        print(f"[{i+1}/{len(db['entries'])}] {tag} {r['id']}")

    with open(OUT_PATH, 'w') as f:
        json.dump(results, f, indent=2)

    by_shot = {}
    for r in results:
        st = r.get('shot_type', 'unknown')
        by_shot.setdefault(st, {'total': 0, 'visible': 0})
        by_shot[st]['total'] += 1
        if r['ball_visible']:
            by_shot[st]['visible'] += 1

    print(f'\n{"="*50}')
    print('BALL VISIBILITY AUDIT SUMMARY')
    print(f'{"="*50}')
    for st, counts in by_shot.items():
        print(f'  {st:10s}: {counts["visible"]}/{counts["total"]} have ball visible near contact')
    total_visible = sum(c['visible'] for c in by_shot.values())
    total = sum(c['total'] for c in by_shot.values())
    print(f'  {"TOTAL":10s}: {total_visible}/{total}')
    print(f'\nSaved to {OUT_PATH}')


if __name__ == '__main__':
    main()
