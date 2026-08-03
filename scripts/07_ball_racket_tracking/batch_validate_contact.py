"""
Batch-validate the gap vs proximity contact-frame methods against the
existing wrist-velocity peak, across a sample of real clips, before
committing to a full database reprocessing run.
"""
import json
import os
import random

import cv2

from racket_tracker import track_racket_and_ball, find_contact_frame, _find_gap_contact, _dist, get_model

random.seed(7)

MODEL_NAME = os.environ.get('YOLO_MODEL', 'yolo11s.pt')
model = get_model(MODEL_NAME)
print(f'Using model: {MODEL_NAME}\n')

JOBS = [
    ('forehand', r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings_validated.json', 1.0, 8),
    ('backhand', r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings_validated.json', 1.0, 8),
    ('serve',    r'C:\Users\jackp\tennis_app\data\03_swing_detection\serve_swings_validated.json',    1.8, 6),
]

rows = []
for shot_type, path, pre_sec, n in JOBS:
    with open(path) as f:
        swings = json.load(f)['swings']
    valid = [s for s in swings if s.get('clip_path') and os.path.exists(s['clip_path'])]
    sample = random.sample(valid, min(n, len(valid)))

    for sw in sample:
        clip = sw['clip_path']
        cap = cv2.VideoCapture(clip)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()

        wrist_frame = round(pre_sec * fps)

        dets, _ = track_racket_and_ball(clip, model=model)
        window = int(0.3 * fps)
        window_dets = [d for d in dets if abs(d['frame'] - wrist_frame) <= window]

        gap = _find_gap_contact(window_dets)
        gap_frame = gap[0] if gap else None
        gap_gapsize = gap[2] if gap else None

        prox_candidates = [d for d in window_dets if d['racket_box'] and d['ball_box']]
        if prox_candidates:
            best = min(prox_candidates, key=lambda d: _dist(d['racket_box'], d['ball_box']))
            prox_frame = best['frame']
        else:
            prox_frame = None

        final_frame, final_conf, final_method = find_contact_frame(dets, wrist_frame, fps)

        rows.append({
            'shot': shot_type,
            'clip': os.path.basename(clip),
            'fps': round(fps, 1),
            'wrist_frame': wrist_frame,
            'gap_frame': gap_frame, 'gap_size': gap_gapsize,
            'prox_frame': prox_frame,
            'final_frame': final_frame, 'final_conf': final_conf, 'final_method': final_method,
        })

        gap_off = f'{gap_frame - wrist_frame:+d}' if gap_frame is not None else '  n/a'
        prox_off = f'{prox_frame - wrist_frame:+d}' if prox_frame is not None else '  n/a'
        print(f'{shot_type:9s} {os.path.basename(clip):35s} wrist={wrist_frame:3d}  '
              f'gap={gap_off:>5s}({gap_gapsize or "-"})  prox={prox_off:>5s}  '
              f'FINAL={final_method:26s} conf={final_conf}')

# ── summary ──────────────────────────────────────────────────────────────────
both = [r for r in rows if r['gap_frame'] is not None and r['prox_frame'] is not None]
agree_3 = [r for r in both if abs(r['gap_frame'] - r['prox_frame']) <= 3]
gap_available = [r for r in rows if r['gap_frame'] is not None]
prox_available = [r for r in rows if r['prox_frame'] is not None]
neither = [r for r in rows if r['gap_frame'] is None and r['prox_frame'] is None]

print(f'\n{"="*70}')
print(f'Total clips: {len(rows)}')
print(f'Gap method found a candidate:      {len(gap_available)}/{len(rows)}')
print(f'Proximity method found a candidate: {len(prox_available)}/{len(rows)}')
print(f'Both available:                     {len(both)}/{len(rows)}')
print(f'  of those, agree within 3 frames:  {len(agree_3)}/{len(both)}')
print(f'Neither available (fell back to wrist-velocity): {len(neither)}/{len(rows)}')

out_name = f'contact_validation_results_{MODEL_NAME.replace(".pt", "")}.json'
with open(os.path.join(r'C:\Users\jackp\tennis_app\data\07_audits', out_name), 'w') as f:
    json.dump(rows, f, indent=2)
print(f'\nSaved raw results to data/{out_name}')
