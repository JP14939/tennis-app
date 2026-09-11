"""
Interactive contact-frame marking tool for Jack's own raw amateur footage
(data/runtime/raw_footage_ingest/IMG_5822/, IMG_5823/ -- already cut into
per-swing clips and shot-type-reviewed via DevAmateurClipReviewScreen.js, but
never contact-time-marked; see list_amateur_clip_review_candidates.py's
docstring: "amateur candidate clips never need... contact-time correction" --
true for the amateur_eval (shot-type-only) stream, NOT true for what THIS
tool needs: real contact-frame ground truth for the no-audio visual-contact
eval, plan swirling-popping-flame.md Phase 4).

Neither existing marking tool fits these clips: ContactMarkingScreen.js needs
a running app + device; correct_contact_time.py is hard-wired to
pro_database.json entries (rewrites `trajectory`/`overlay` there) and these
raw-ingest clips aren't pro-database entries at all. This is a standalone
desk tool instead, same interactive cv2-window + keyboard pattern as
label_net_keypoints.py (10_net_detection/) -- resumable, atomic-write-per-clip.

Source: every non-'skip' entry across data/runtime/raw_footage_ingest/*/
ingest_report.json. `contact_time_in_clip` there is only a rough, UNVERIFIED
auto-detect guess (the raw footage went through /api/analyse with no manual
contactTime -- see ingest_raw_footage_to_history.py) -- used only to seed
where playback starts, never trusted as the answer.

Writes one row per marked clip to
data/07_ball_racket_tracking/amateur_contact_labels.jsonl:
  {clip_path, source_video, shot_type, contact_frame, contact_time_sec, fps,
   total_frames, marked_at}
Already-labeled clip_paths are skipped on resume.

Controls
  a / d          step 1 frame back / forward
  A / D          step 10 frames back / forward
  space / enter  confirm this frame as contact, save, move to next clip
  s              skip this clip (not a clean/usable swing) -- logged, won't
                 resurface
  q / esc        save progress and quit

Usage
  python mark_amateur_contact_time.py
  python mark_amateur_contact_time.py --limit 40
  python mark_amateur_contact_time.py --shot-type forehand
"""
import argparse
import datetime as _dt
import glob
import json
import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), '00_utils'))
from paths import DATA_DIR  # noqa: E402

RAW_INGEST_DIR = os.path.join(DATA_DIR, 'runtime', 'raw_footage_ingest')
OUT_PATH = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'amateur_contact_labels.jsonl')

SEED_WINDOW_FRAMES = 20  # how far past/before the seed guess to preload for smooth stepping


def _iso_now():
    return _dt.datetime.now().isoformat(timespec='seconds')


def load_candidates(shot_type_filter=None):
    """One row per real (non-'skip') swing across every ingest_report.json,
    each carrying its own absolute clip_path (as ingest_raw_footage_to_history.py
    wrote it) and the source video's folder name for provenance."""
    candidates = []
    for report_path in sorted(glob.glob(os.path.join(RAW_INGEST_DIR, '*', 'ingest_report.json'))):
        source_video = os.path.basename(os.path.dirname(report_path))
        with open(report_path) as f:
            entries = json.load(f)
        for e in entries:
            if e.get('shot_type') in (None, 'skip'):
                continue
            if shot_type_filter and e['shot_type'] != shot_type_filter:
                continue
            candidates.append({
                'clip_path': e['clip_path'],
                'source_video': source_video,
                'shot_type': e['shot_type'],
                'seed_time_sec': e.get('contact_time_in_clip'),
            })
    return candidates


def load_done():
    if not os.path.exists(OUT_PATH):
        return set()
    done = set()
    with open(OUT_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                done.add(json.loads(line)['clip_path'])
    return done


def append_row(row):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'a') as f:
        f.write(json.dumps(row) + '\n')


def _read_frame(cap, idx):
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    return frame if ok else None


def mark_clip(cand):
    """Returns 'marked', 'skipped', or 'quit'."""
    cap = cv2.VideoCapture(cand['clip_path'])
    if not cap.isOpened():
        print(f"  [skip] cannot open {cand['clip_path']}", file=sys.stderr)
        return 'skipped'
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    seed = cand.get('seed_time_sec')
    idx = max(0, min(total - 1, round(seed * fps))) if seed else total // 2

    win = 'mark_amateur_contact_time  --  a/d step, A/D x10, space=confirm, s=skip, q=quit'
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    result = None
    while result is None:
        frame = _read_frame(cap, idx)
        if frame is None:
            idx = max(0, idx - 1)
            continue
        disp = frame.copy()
        label = (f"{cand['source_video']}  {cand['shot_type']:<9}  "
                 f"frame {idx}/{total - 1}  t={idx / fps:.3f}s")
        cv2.rectangle(disp, (0, 0), (disp.shape[1], 34), (0, 0, 0), -1)
        cv2.putText(disp, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 120), 2)
        cv2.imshow(win, disp)
        key = cv2.waitKey(0) & 0xFF
        if key in (ord('d'),):
            idx = min(total - 1, idx + 1)
        elif key in (ord('a'),):
            idx = max(0, idx - 1)
        elif key == ord('D'):
            idx = min(total - 1, idx + 10)
        elif key == ord('A'):
            idx = max(0, idx - 10)
        elif key in (32, 13):  # space / enter
            result = ('marked', idx)
        elif key == ord('s'):
            result = ('skipped', None)
        elif key in (ord('q'), 27):  # q / esc
            result = ('quit', None)

    cap.release()
    status, marked_idx = result
    if status == 'marked':
        append_row({
            'clip_path': cand['clip_path'],
            'source_video': cand['source_video'],
            'shot_type': cand['shot_type'],
            'contact_frame': marked_idx,
            'contact_time_sec': round(marked_idx / fps, 4),
            'fps': round(fps, 4),
            'total_frames': total,
            'marked_at': _iso_now(),
        })
    elif status == 'skipped':
        append_row({
            'clip_path': cand['clip_path'],
            'source_video': cand['source_video'],
            'shot_type': cand['shot_type'],
            'contact_frame': None,
            'skipped': True,
            'marked_at': _iso_now(),
        })
    return status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--shot-type', choices=['forehand', 'backhand', 'serve'])
    args = ap.parse_args()

    candidates = load_candidates(shot_type_filter=args.shot_type)
    done = load_done()
    todo = [c for c in candidates if c['clip_path'] not in done]
    if args.limit:
        todo = todo[:args.limit]

    print(f'{len(candidates)} real-swing candidates total | {len(done)} already done | '
          f'{len(todo)} to mark this session', file=sys.stderr)
    if not todo:
        print('Nothing to do.', file=sys.stderr)
        return

    marked = skipped = 0
    for i, cand in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {cand['source_video']} {cand['shot_type']} "
              f"{os.path.basename(cand['clip_path'])}", file=sys.stderr)
        status = mark_clip(cand)
        if status == 'marked':
            marked += 1
        elif status == 'skipped':
            skipped += 1
        elif status == 'quit':
            break

    cv2.destroyAllWindows()
    print(f'\nDone this session: {marked} marked, {skipped} skipped. '
          f'Total in {OUT_PATH}: {len(load_done())}.', file=sys.stderr)


if __name__ == '__main__':
    main()
