"""
Match Jack's own hand-cropped, hand-labeled video chunks back to
pro_database.json entries, by exact frame matching against the 9 source
compilation videos -- not visual/color guessing. Each chunk is a literal
crop of one source video (same pixels, same encode lineage), so a simple
resized-grayscale signature with a tight distance threshold is enough;
no perceptual-hashing library needed.

Workflow:
  1. Jack watches a source compilation, confirms a stretch is all one
     player, crops/exports that stretch with any tool, and drops the file
     in data/07_audits/pro_name_chunks/ named after the player, e.g.
     "Roger Federer.mp4".
  2. This script locates which source video + frame range each chunk came
     from, finds every swing in that range, and labels the matching
     pro_database entries in data/06_pro_database/player_names.json.

Usage:
  python match_pro_name_chunks.py [--threshold 6.0]
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from build_pro_database import JOBS  # noqa: E402
from paths import DATA_DIR  # noqa: E402

CHUNK_DIR = os.path.join(DATA_DIR, '07_audits', 'pro_name_chunks')
DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
NAMES_PATH = os.path.join(DATA_DIR, '06_pro_database', 'player_names.json')

SIG_SIZE = 32
DEFAULT_THRESHOLD = 6.0  # mean absolute grayscale pixel difference (0-255 scale)
N_CHUNK_SAMPLES = 5      # signatures taken across the chunk's own duration, for the refine pass


def frame_signature(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (SIG_SIZE, SIG_SIZE), interpolation=cv2.INTER_AREA)
    return small.astype(np.float32)


def mad(a, b):
    return float(np.abs(a - b).mean())


def video_info(path):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return total, fps


def read_signatures_evenly(path, n):
    """n evenly-spaced frame signatures across the whole video/chunk."""
    total, fps = video_info(path)
    if total <= 0 or fps <= 0:
        return [], fps
    positions = [int(total * i / max(1, n - 1)) if n > 1 else 0 for i in range(n)]
    positions = [min(p, total - 1) for p in positions]

    cap = cv2.VideoCapture(path)
    sigs = []
    idx = 0
    pos_set = set(positions)
    pos_iter = iter(sorted(pos_set))
    target = next(pos_iter, None)
    while target is not None:
        ret = cap.grab()
        if not ret:
            break
        if idx == target:
            ok, frame = cap.retrieve()
            if ok:
                sigs.append((idx, frame_signature(frame)))
            target = next(pos_iter, None)
        idx += 1
    cap.release()
    return sigs, fps


def coarse_scan(source_path, query_sig, step_sec=1.0):
    """Sequentially walk the source video (grab-only for skipped frames --
    reliable on compressed video, unlike random CAP_PROP_POS_FRAMES seeks),
    sampling roughly once per step_sec, tracking the best match position."""
    total, fps = video_info(source_path)
    if total <= 0 or fps <= 0:
        return None, None, fps
    step = max(1, int(fps * step_sec))

    cap = cv2.VideoCapture(source_path)
    best_pos, best_score = None, float('inf')
    idx = 0
    while True:
        ret = cap.grab()
        if not ret:
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                score = mad(frame_signature(frame), query_sig)
                if score < best_score:
                    best_score, best_pos = score, idx
        idx += 1
    cap.release()
    return best_pos, best_score, fps


def refine(source_path, chunk_sigs, chunk_fps, coarse_pos, fps, window_sec=3.0, step_frames=3):
    """Fine local scan around coarse_pos, scoring EVERY sampled chunk
    signature (not just the first) at each candidate offset to confirm
    real alignment rather than a single coincidental frame lookalike."""
    total, _ = video_info(source_path)
    window = int(fps * window_sec)
    lo = max(0, coarse_pos - window)
    hi = min(total - 1, coarse_pos + window)

    # chunk signature relative offsets (in source-fps frames)
    chunk_positions = [p for p, _ in chunk_sigs]
    chunk_duration_frames = chunk_positions[-1] if chunk_positions else 0
    chunk_duration_sec = chunk_duration_frames / chunk_fps if chunk_fps else 0
    rel_offsets = [int((p / chunk_fps) * fps) if chunk_fps else 0 for p, _ in chunk_sigs] if chunk_positions else []

    cap = cv2.VideoCapture(source_path)
    best_start, best_score = None, float('inf')
    for start in range(lo, hi + 1, step_frames):
        scores = []
        for (_, sig), offset in zip(chunk_sigs, rel_offsets):
            frame_idx = start + offset
            if frame_idx < 0 or frame_idx >= total:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok:
                continue
            scores.append(mad(frame_signature(frame), sig))
        if scores:
            avg = sum(scores) / len(scores)
            if avg < best_score:
                best_score, best_start = avg, start
    cap.release()
    return best_start, best_score, chunk_duration_sec


def load_swings_for_job(job):
    with open(job['swings_validated'], encoding='utf-8') as f:
        return json.load(f)['swings']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--threshold', type=float, default=DEFAULT_THRESHOLD,
                         help='Max mean pixel-difference (0-255) to accept a match (default: %(default)s)')
    args = parser.parse_args()

    os.makedirs(CHUNK_DIR, exist_ok=True)
    chunk_files = [f for f in os.listdir(CHUNK_DIR) if f.lower().endswith(('.mp4', '.mov', '.m4v'))]
    if not chunk_files:
        print(f'No chunk files found in {CHUNK_DIR}')
        print('Drop a cropped video there, named after the player, e.g. "Roger Federer.mp4"')
        return

    with open(DB_PATH, encoding='utf-8') as f:
        db = json.load(f)
    valid_ids = {e['id'] for e in db['entries']}

    player_names = {}
    if os.path.exists(NAMES_PATH):
        with open(NAMES_PATH, encoding='utf-8') as f:
            player_names = json.load(f)

    for fname in chunk_files:
        name = os.path.splitext(fname)[0].replace('_', ' ').strip()
        chunk_path = os.path.join(CHUNK_DIR, fname)
        print(f'\n=== {fname}  ->  "{name}" ===')

        chunk_sigs, chunk_fps = read_signatures_evenly(chunk_path, N_CHUNK_SAMPLES)
        if not chunk_sigs:
            print('  Could not read chunk video, skipping.')
            continue
        query_sig = chunk_sigs[0][1]

        best_overall = None  # (job, coarse_pos, coarse_score, fps)
        for job in JOBS:
            print(f'  scanning {os.path.basename(job["source_video"])}...', end=' ', flush=True)
            pos, score, fps = coarse_scan(job['source_video'], query_sig)
            print(f'best coarse score={score}')
            if pos is not None and (best_overall is None or score < best_overall[2]):
                best_overall = (job, pos, score, fps)

        if best_overall is None:
            print('  No candidate source video found, skipping.')
            continue

        job, coarse_pos, coarse_score, fps = best_overall
        print(f'  best candidate: {os.path.basename(job["source_video"])} near frame {coarse_pos} (coarse score {coarse_score:.2f})')

        refined_pos, refined_score, chunk_duration_sec = refine(
            job['source_video'], chunk_sigs, chunk_fps, coarse_pos, fps)

        if refined_pos is None or refined_score > args.threshold:
            print(f'  Refined match score {refined_score} exceeds threshold {args.threshold} -- not confident, skipping.')
            print('  (Try a different crop, or rerun with a higher --threshold if you\'re confident this is right.)')
            continue

        start_frame = refined_pos
        end_frame = start_frame + int(chunk_duration_sec * fps)
        print(f'  MATCHED: {os.path.basename(job["source_video"])} frames [{start_frame}, {end_frame}] (score {refined_score:.2f})')

        swings = load_swings_for_job(job)
        labeled = 0
        for sw in swings:
            if sw['end_frame'] < start_frame or sw['start_frame'] > end_frame:
                continue  # no overlap with the chunk's range
            entry_id = f"{job['shot_type']}_{sw['swing_id']:04d}"
            if entry_id not in valid_ids:
                continue
            if entry_id in player_names and player_names[entry_id] != name:
                print(f'    (overwriting existing label "{player_names[entry_id]}" -> "{name}" for {entry_id})')
            player_names[entry_id] = name
            labeled += 1
        print(f'  Labeled {labeled} swing(s) as "{name}"')

    with open(NAMES_PATH, 'w', encoding='utf-8') as f:
        json.dump(player_names, f, indent=2)
    print(f'\nSaved {len(player_names)} total labeled entries to {NAMES_PATH}')


if __name__ == '__main__':
    main()
