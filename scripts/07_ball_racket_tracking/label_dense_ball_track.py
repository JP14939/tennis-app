"""
Build the DENSE ball-track evaluation set for ball_roi_tracker (plan stage 1).

Unlike the existing 354 scattered single-frame checkpoints
(manual_ball_label_log_server.jsonl), this labels CONSECUTIVE frames (every
2nd-3rd) across each clip's ball flight, so eval_ball_roi_tracker.py can
measure real per-frame track continuity, not just presence at isolated frames.

Reuses the proven proposer -> confirm pattern (freeform Claude localization is
documented to fail -- see ball_presence_verifier.py):
  motion-ROI bootstrap (frame differencing)
    -> find_ball_candidates(full frame) + find_ball_candidates(ROI crop)
       + detect_ball(ROI crop)                              (free/local proposals)
    -> ball_presence_verifier.verify_ball_candidate_crop     (Haiku binary confirm)
    -> label_ball_frames._candidate_to_box_norm              (circle -> box)
Frames where nothing is confirmed are written ball_visible=false with
needs_manual_review=true for a thin stdin-JSON pass (log_manual_ball_label.py
style). Idempotent / resumable; cost-logged via ball_presence_verifier
(expect < $1 for the whole set).

Usage:
  python label_dense_ball_track.py --seed [--n-hard 4 --n-easy 6]   # draft dense_eval_clips.json
  python label_dense_ball_track.py [--stride 2] [--limit N] [--only CLIP_ID]
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
for sub in ('00_utils',):
    p = os.path.join(SCRIPTS_DIR, sub)
    if p not in sys.path:
        sys.path.insert(0, p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from paths import DATA_DIR  # noqa: E402
from find_ball_candidates import find_ball_candidates  # noqa: E402
from ball_presence_verifier import verify_ball_candidate_crop, cost_summary  # noqa: E402
from label_ball_frames import _candidate_to_box_norm  # noqa: E402
from racket_tracker import detect_ball  # noqa: E402

BALL_DIR = os.path.join(DATA_DIR, '10b_ball_detection')
CLIPS_PATH = os.path.join(BALL_DIR, 'dense_eval_clips.json')
LABELS_PATH = os.path.join(BALL_DIR, 'dense_ball_track_labels.jsonl')
VISIBILITY_AUDIT = os.path.join(DATA_DIR, '07_audits', 'ball_visibility_audit.json')
CLIPS_04 = os.path.join(DATA_DIR, '04_clips')

STRIDE = 2
LABELER = 'label_dense_ball_track.py'


# --------------------------------------------------------------------------
# --seed: draft dense_eval_clips.json from the ball-visibility audit
# --------------------------------------------------------------------------
def _resolve_clip_path(clip_id):
    shot = clip_id.rsplit('_', 1)[0]
    num = clip_id.rsplit('_', 1)[1]
    folder = os.path.join(CLIPS_04, shot)
    if not os.path.isdir(folder):
        return None
    for f in os.listdir(folder):
        if f'_{int(num):04d}_' in f or f'_{num}_' in f:
            return os.path.join(folder, f)
    return None


def seed(n_hard, n_easy):
    audit = json.load(open(VISIBILITY_AUDIT, encoding='utf-8'))
    hard = [a for a in audit if a['ball_detections_in_window'] <= 2]
    easy = [a for a in audit if a['ball_detections_in_window'] >= 12]

    def _spread(pool, n):
        by_st = {}
        for a in pool:
            by_st.setdefault(a['shot_type'], []).append(a)
        picked, i = [], 0
        sts = sorted(by_st)
        while len(picked) < n and any(by_st.values()):
            st = sts[i % len(sts)]
            if by_st[st]:
                picked.append(by_st[st].pop(0))
            i += 1
        return picked

    chosen = _spread(hard, n_hard) + _spread(easy, n_easy)
    clips = []
    for a in chosen:
        path = _resolve_clip_path(a['id'])
        if not path or not os.path.exists(path):
            print(f'  skip {a["id"]}: clip file not found', file=sys.stderr)
            continue
        cap = cv2.VideoCapture(path)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        mid = n // 2
        clips.append({
            'clip_id': a['id'],
            'video_rel': os.path.relpath(path, DATA_DIR),
            'shot_type': a['shot_type'],
            'source_kind': 'broadcast' if a['shot_type'] == 'serve' else 'phone',
            'fps': round(fps, 3),
            'contact_frame': mid,
            'flight_frame_range': [max(0, mid - 12), min(n - 1, mid + 45)],
            'pass1_ball_detections_in_window': a['ball_detections_in_window'],
            'notes': 'seeded from ball_visibility_audit.json; VERIFY contact_frame + flight range by hand',
        })
    os.makedirs(BALL_DIR, exist_ok=True)
    with open(CLIPS_PATH, 'w', encoding='utf-8') as f:
        json.dump(clips, f, indent=2)
    print(f'wrote {CLIPS_PATH} ({len(clips)} clips) -- review contact_frame / flight_frame_range / '
          'source_kind by hand before labelling', file=sys.stderr)


# --------------------------------------------------------------------------
# labelling
# --------------------------------------------------------------------------
def _motion_roi(prev, cur, frame_w, frame_h):
    """Largest moving blob's centre + a generous half-size, or a full-frame
    ROI if motion differencing finds nothing usable."""
    diff = cv2.absdiff(cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY),
                       cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY))
    _, th = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
    th = cv2.dilate(th, np.ones((5, 5), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = [c for c in cnts if 6 < cv2.contourArea(c) < 0.2 * frame_w * frame_h]
    if not cnts:
        return (frame_w // 2, frame_h // 2, max(frame_w, frame_h) // 2)
    c = max(cnts, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)
    return (x + w // 2, y + h // 2, int(max(w, h) * 1.6) + 40)


def _crop(frame, cx, cy, half):
    h, w = frame.shape[:2]
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(w, cx + half), min(h, cy + half)
    return frame[y0:y1, x0:x1], x0, y0


def _load_done():
    done = set()
    if os.path.exists(LABELS_PATH):
        with open(LABELS_PATH, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    done.add((r['clip_id'], r['frame']))
    return done


def label(stride, limit, only):
    if not os.path.exists(CLIPS_PATH):
        sys.exit(f'{CLIPS_PATH} not found -- run --seed first, then review it by hand')
    clips = json.load(open(CLIPS_PATH, encoding='utf-8'))
    if only:
        clips = [c for c in clips if c['clip_id'] == only]
    done = _load_done()

    written = confirmed = manual = 0
    out = open(LABELS_PATH, 'a', encoding='utf-8')
    for clip in clips:
        video = os.path.join(DATA_DIR, clip['video_rel'])
        if not os.path.exists(video):
            print(f'  {clip["clip_id"]}: video missing', file=sys.stderr)
            continue
        lo, hi = clip['flight_frame_range']
        targets = [f for f in range(lo, hi + 1, stride) if (clip['clip_id'], f) not in done]
        if limit:
            targets = targets[:limit]
        if not targets:
            continue

        cap = cv2.VideoCapture(video)
        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        for f in targets:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, f - 1))
            ok0, prev = cap.read()
            ok1, cur = cap.read()
            if not (ok0 and ok1):
                continue
            cx, cy, half = _motion_roi(prev, cur, fw, fh)
            crop, x0, y0 = _crop(cur, cx, cy, half)

            proposals = list(find_ball_candidates(cur))
            for c in find_ball_candidates(crop):
                proposals.append({**c, 'x': c['x'] + x0, 'y': c['y'] + y0})
            box, _bc = detect_ball(crop)
            if box is not None:
                bx = (box[0] + box[2]) / 2 + x0
                by = (box[1] + box[3]) / 2 + y0
                br = max(4.0, max(box[2] - box[0], box[3] - box[1]) / 2)
                proposals.append({'x': bx, 'y': by, 'radius': br, 'area': br * br, 'fill_ratio': 1.0})

            row = {'clip_id': clip['clip_id'], 'video_rel': clip['video_rel'], 'frame': f,
                   'fps': clip['fps'], 'ball_visible': False, 'box_norm': None,
                   'is_live_ball': None, 'occluded': None, 'motion_blur': None,
                   'labeler': LABELER, 'reviewed_by': None, 'needs_manual_review': True,
                   'note': 'no confirmed candidate'}

            for c in proposals:
                try:
                    res = verify_ball_candidate_crop(cur, c)
                except Exception as e:  # noqa: BLE001
                    print(f'    {clip["clip_id"]} f{f}: verify error {e}', file=sys.stderr)
                    continue
                if res.get('is_ball'):
                    row.update({'ball_visible': True,
                                'box_norm': _candidate_to_box_norm(c, fw, fh),
                                'needs_manual_review': False,
                                'note': res.get('reasoning')})
                    break

            out.write(json.dumps(row) + '\n')
            out.flush()
            written += 1
            if row['needs_manual_review']:
                manual += 1
            else:
                confirmed += 1
            print(f'  {clip["clip_id"]} f{f}: '
                  f'{"BALL " + str(row["box_norm"]) if row["ball_visible"] else "needs manual review"}',
                  file=sys.stderr)
        cap.release()

    out.close()
    cost = cost_summary()
    print(f'\n{written} rows written ({confirmed} confirmed, {manual} need manual review)', file=sys.stderr)
    print(f'cost so far: {cost["calls"]} calls, ${cost["estimated_cost_usd"]}', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', action='store_true')
    ap.add_argument('--n-hard', type=int, default=4)
    ap.add_argument('--n-easy', type=int, default=6)
    ap.add_argument('--stride', type=int, default=STRIDE)
    ap.add_argument('--limit', type=int, default=None, help='max target frames per clip')
    ap.add_argument('--only', default=None, help='a single clip_id')
    args = ap.parse_args()
    if args.seed:
        seed(args.n_hard, args.n_easy)
    else:
        label(args.stride, args.limit, args.only)


if __name__ == '__main__':
    main()
