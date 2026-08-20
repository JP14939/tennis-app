"""
Phase 1 (data sourcing) of the fine-tuned ball detector project -- see the
approved plan for the full scope. Pulls candidate frames into three raw
buckets for Claude-vision labeling in a later step (not done here -- this
is purely local/free, no API calls):

  near_contact/  -- full frames within ~0.15s of a REAL saved swing's known
                    contact time (same source as audit_ball_confidence_at_
                    contact.py: backend/data/app.db's analyses, filtered to
                    ones with a still-present clip). This is exactly the
                    window the generic detector measured at only 50%/0.41.
  mid_flight/    -- other frames spread across the same clips -- ball may
                    be approaching/departing even where it isn't the
                    labeled contact moment, useful positive diversity
                    beyond "ball right next to a racket".
  negative_candidates/ -- frames from moments Claude ITSELF already
                    characterized as non-shot (walking/idle/no ball
                    contact) during this session's real detect_rallies.py
                    verification runs on IMG_5822.MOV/IMG_5755.MOV --
                    reusing real, already-paid-for Claude reasoning
                    instead of guessing at negative sources. Not yet
                    confirmed ball-free (a ball could still be in play,
                    just not being struck) -- that confirmation is the
                    labeling step's job, this is candidate sourcing only.

Usage:
  python sample_ball_frames.py [limit_per_bucket]
"""
import json
import os
import re
import sqlite3
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))

from paths import DATA_DIR, BACKEND_DIR  # noqa: E402
from clip_urls import USER_CLIPS_DIR  # noqa: E402

DB_PATH = os.path.join(BACKEND_DIR, 'data', 'app.db')
OUT_ROOT = os.path.join(DATA_DIR, '10b_ball_detection', 'candidate_frames')
NEAR_CONTACT_DIR = os.path.join(OUT_ROOT, 'near_contact')
MID_FLIGHT_DIR = os.path.join(OUT_ROOT, 'mid_flight')
NEGATIVE_DIR = os.path.join(OUT_ROOT, 'negative_candidates')
META_PATH = os.path.join(OUT_ROOT, 'candidate_metadata.json')

WINDOW_SEC = 0.15  # matches audit_ball_confidence_at_contact.py's own window

# Real "not a real shot" moments from this session's actual Claude-verified
# detect_rallies.py runs -- reused as free negative candidates rather than
# spending new API calls or guessing at negative sources.
NEGATIVE_SOURCES = [
    (r'C:\Users\jackp\Downloads\IMG_5822.MOV',
     r'C:\Users\jackp\AppData\Local\Temp\claude\c--Users-jackp-tennis-app\1c23584a-db3a-43da-bf3b-f7f8cbcdb542\scratchpad\detect_rallies_5822.log'),
    (r'C:\Users\jackp\Downloads\IMG_5755.MOV',
     r'C:\Users\jackp\AppData\Local\Temp\claude\c--Users-jackp-tennis-app\1c23584a-db3a-43da-bf3b-f7f8cbcdb542\scratchpad\detect_rallies_5755.log'),
]


def _user_clip_path(user_clip_url):
    if not user_clip_url or not user_clip_url.startswith('/user-clips/'):
        return None
    rel = user_clip_url[len('/user-clips/'):]
    return os.path.join(USER_CLIPS_DIR, *rel.split('/'))


def _extract_frame(video_path, frame_idx, out_path):
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return False
    cv2.imwrite(out_path, frame)
    return True


def source_positives(limit):
    """near_contact + mid_flight buckets, from real saved user swings."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, result_json FROM analyses ORDER BY id DESC LIMIT ?', (limit * 3,)
    ).fetchall()
    conn.close()

    near_contact_meta, mid_flight_meta = [], []
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

        cap = cv2.VideoCapture(clip_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        if not fps or total <= 0:
            continue

        checked += 1
        analysis_id = row['id']

        # near_contact: the exact contact frame plus one on either side of
        # the ±WINDOW_SEC window (3 frames -- enough diversity per swing
        # without over-sampling any single clip).
        contact_frame = round(contact_time_sec * fps)
        window = max(1, int(WINDOW_SEC * fps))
        for offset, tag in ((-window, 'before'), (0, 'contact'), (window, 'after')):
            fi = max(0, min(total - 1, contact_frame + offset))
            out_name = f'analysis{analysis_id}_f{fi}_{tag}.jpg'
            out_path = os.path.join(NEAR_CONTACT_DIR, out_name)
            if _extract_frame(clip_path, fi, out_path):
                near_contact_meta.append({
                    'file': out_name, 'bucket': 'near_contact', 'analysis_id': analysis_id,
                    'source_clip': clip_path, 'frame': fi, 'fps': fps,
                })

        # mid_flight: a frame well outside the contact window, near each end
        # of the clip (backswing / recovery) -- ball may or may not be
        # visible there, that's for the labeling step to determine.
        for fi, tag in ((max(0, contact_frame - window * 4), 'early'),
                        (min(total - 1, contact_frame + window * 4), 'late')):
            out_name = f'analysis{analysis_id}_f{fi}_{tag}.jpg'
            out_path = os.path.join(MID_FLIGHT_DIR, out_name)
            if _extract_frame(clip_path, fi, out_path):
                mid_flight_meta.append({
                    'file': out_name, 'bucket': 'mid_flight', 'analysis_id': analysis_id,
                    'source_clip': clip_path, 'frame': fi, 'fps': fps,
                })

    return near_contact_meta, mid_flight_meta


def source_negatives(limit):
    """negative_candidates bucket, from real Claude-verified 'not a real
    shot' timestamps in this session's detect_rallies.py logs."""
    meta = []
    per_source_limit = max(1, limit // len(NEGATIVE_SOURCES))

    for video_path, log_path in NEGATIVE_SOURCES:
        if not os.path.exists(video_path) or not os.path.exists(log_path):
            print(f'  skipping (missing): {video_path} / {log_path}', file=sys.stderr)
            continue
        with open(log_path, encoding='utf-8', errors='ignore') as f:
            log_text = f.read()
        times = [float(m) for m in re.findall(r'at ([\d.]+)s: not a real shot', log_text)]
        times = times[:per_source_limit]

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if not fps:
            continue

        video_name = os.path.splitext(os.path.basename(video_path))[0]
        for t in times:
            fi = round(t * fps)
            out_name = f'{video_name}_f{fi}.jpg'
            out_path = os.path.join(NEGATIVE_DIR, out_name)
            if _extract_frame(video_path, fi, out_path):
                meta.append({
                    'file': out_name, 'bucket': 'negative_candidates',
                    'source_clip': video_path, 'frame': fi, 'fps': fps,
                    'source_reasoning': 'claude_verified_not_a_real_shot',
                })
    return meta


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 60

    for d in (NEAR_CONTACT_DIR, MID_FLIGHT_DIR, NEGATIVE_DIR):
        os.makedirs(d, exist_ok=True)

    print('Sourcing positives (near_contact + mid_flight) from real saved swings...', file=sys.stderr)
    near_contact_meta, mid_flight_meta = source_positives(limit)
    print(f'  near_contact: {len(near_contact_meta)} frames', file=sys.stderr)
    print(f'  mid_flight:   {len(mid_flight_meta)} frames', file=sys.stderr)

    print('Sourcing negative candidates from real Claude-verified non-shot moments...', file=sys.stderr)
    negative_meta = source_negatives(limit)
    print(f'  negative_candidates: {len(negative_meta)} frames', file=sys.stderr)

    all_meta = near_contact_meta + mid_flight_meta + negative_meta
    with open(META_PATH, 'w') as f:
        json.dump(all_meta, f, indent=2)

    print(f'\nDone. {len(all_meta)} candidate frames total.', file=sys.stderr)
    print(f'Metadata: {META_PATH}', file=sys.stderr)


if __name__ == '__main__':
    main()
