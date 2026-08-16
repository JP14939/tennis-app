"""
Group pro_database.json clips by clothing color, as a batch-labeling aid --
NOT a player-identification tool. This only clusters visually similar
outfits so a human (Jack) can label a whole group of clips as one player
at once instead of watching all 631 individually.

IMPORTANT CAVEAT (also printed at the end): same clothing color doesn't
guarantee the same player (sponsor kits repeat across pros, especially at
the same tournament), and the same player can land in multiple groups if
they wore different outfits across the source footage. Every group still
needs a human glance to confirm before labeling.

Uses overlay_trajectories.json (built for the skeleton-overlay feature) to
find each clip's torso region without any new pose extraction.

Usage:
  python group_clips_by_clothing_color.py [--threshold 28]
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
OVERLAY_PATH = os.path.join(DATA_DIR, '06_pro_database', 'overlay_trajectories.json')
OUT_DIR = os.path.join(DATA_DIR, '07_audits', 'clothing_groups')

TORSO_LANDMARKS = ['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip']
MARGIN = 0.06  # extra crop margin as a fraction of torso box size, avoids clipping fabric edges
THUMB_SIZE = 90
GRID_COLS = 6
DEFAULT_THRESHOLD = 28.0  # Euclidean RGB distance; tune via --threshold if groups look too coarse/fine


def nearest_torso_frame(trajectory):
    """The trajectory sample closest to contact (t=0) that has all 4 torso landmarks."""
    candidates = [p for p in trajectory if all(p['landmarks'].get(k) for k in TORSO_LANDMARKS)]
    if not candidates:
        return None
    return min(candidates, key=lambda p: abs(p['t']))


def torso_crop(frame, landmarks):
    h, w = frame.shape[:2]
    xs = [landmarks[k]['x'] for k in TORSO_LANDMARKS]
    ys = [landmarks[k]['y'] for k in TORSO_LANDMARKS]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    mx = (x_hi - x_lo) * MARGIN
    my = (y_hi - y_lo) * MARGIN
    x1 = max(0, int((x_lo - mx) * w))
    x2 = min(w, int((x_hi + mx) * w))
    y1 = max(0, int((y_lo - my) * h))
    y2 = min(h, int((y_hi + my) * h))
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]


def median_color(crop):
    """Median BGR (cv2 native order) over the crop -- robust to small
    highlight/shadow/racket-edge outliers within mostly-uniform shirt fabric."""
    pixels = crop.reshape(-1, 3).astype(np.float32)
    return np.median(pixels, axis=0)  # (B, G, R)


def complete_linkage_clusters(points_idx, colors, threshold):
    """
    Agglomerative clustering with COMPLETE linkage (a merge is only allowed
    if every pairwise distance between the two groups' members stays under
    threshold), not single linkage -- single linkage (naive union-find on
    pairwise distances below a threshold) chains transitively: if red is
    close to orange and orange is close to yellow, red and yellow end up in
    the same group even though they're nothing alike. Complete linkage
    doesn't have that failure mode.

    Returns a list of lists of original indices (one list per final cluster).
    """
    n = len(points_idx)
    if n == 0:
        return []
    pts = colors[points_idx]
    D = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)
    np.fill_diagonal(D, np.inf)

    members = {i: [i] for i in range(n)}
    active = np.ones(n, dtype=bool)

    while True:
        masked = np.where(active[:, None] & active[None, :], D, np.inf)
        i, j = np.unravel_index(np.argmin(masked), masked.shape)
        if masked[i, j] >= threshold:
            break
        # complete linkage: distance from the merged cluster to any other k
        # is the MAX of the two clusters' distances to k (worst case, not
        # best case) -- this is what prevents chaining.
        D[i, :] = np.maximum(D[i, :], D[j, :])
        D[:, i] = D[i, :]
        members[i].extend(members[j])
        del members[j]
        active[j] = False

    return [[points_idx[p] for p in group] for group in members.values()]


def build_contact_sheet(members, colors_by_id):
    thumbs = []
    for m in members:
        img = m.get('_thumb')
        if img is None:
            continue
        resized = cv2.resize(img, (THUMB_SIZE, THUMB_SIZE))
        cv2.putText(resized, m['entry_id'], (3, THUMB_SIZE - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 255, 255), 1, cv2.LINE_AA)
        thumbs.append(resized)
    if not thumbs:
        return None

    rows = []
    for i in range(0, len(thumbs), GRID_COLS):
        row = thumbs[i:i + GRID_COLS]
        while len(row) < GRID_COLS:
            row.append(np.zeros((THUMB_SIZE, THUMB_SIZE, 3), dtype=np.uint8))
        rows.append(np.hstack(row))
    return np.vstack(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--threshold', type=float, default=DEFAULT_THRESHOLD,
                         help='Max Euclidean RGB distance to join the same group (default: %(default)s)')
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    with open(DB_PATH, encoding='utf-8') as f:
        db = json.load(f)
    with open(OVERLAY_PATH, encoding='utf-8') as f:
        overlays = json.load(f)

    entries = db['entries']
    colors = np.full((len(entries), 3), np.nan, dtype=np.float32)
    thumbs = [None] * len(entries)

    print(f'Computing torso colors for {len(entries)} entries...')
    for i, entry in enumerate(entries):
        traj = overlays.get(entry['id'])
        clip_path = entry.get('clip_path')
        if not traj or not clip_path or not os.path.exists(clip_path):
            continue
        sample = nearest_torso_frame(traj)
        if sample is None:
            continue

        cap = cv2.VideoCapture(clip_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        # sample['t'] is clip-relative seconds (matches this clip's own playback timeline)
        target_frame = max(0, min(total - 1, round(sample['t'] * fps)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            continue

        crop = torso_crop(frame, sample['landmarks'])
        if crop is None or crop.size == 0:
            continue

        colors[i] = median_color(crop)
        thumbs[i] = crop

        if (i + 1) % 100 == 0:
            print(f'  {i + 1}/{len(entries)}...')

    valid = ~np.isnan(colors).any(axis=1)
    print(f'{valid.sum()}/{len(entries)} entries got a usable torso color')

    print(f'Clustering by color (threshold={args.threshold}, complete linkage)...')
    valid_idx = np.where(valid)[0].tolist()
    clusters = complete_linkage_clusters(valid_idx, colors, args.threshold)
    # entries with no usable color each get their own singleton group
    clusters += [[i] for i in np.where(~valid)[0]]

    ordered_groups = sorted(clusters, key=len, reverse=True)

    manifest = {}
    sheet_count = 0
    for gi, members_idx in enumerate(ordered_groups):
        group_id = f'group_{gi:04d}'
        members = []
        for i in members_idx:
            entry = entries[i]
            members.append({
                'entry_id': entry['id'],
                'shot_type': entry['shot_type'],
                'clip_path': entry.get('clip_path'),
                '_thumb': thumbs[i],
            })
        manifest[group_id] = [{k: v for k, v in m.items() if k != '_thumb'} for m in members]

        if len(members) >= 2:
            sheet = build_contact_sheet(members, colors)
            if sheet is not None:
                cv2.imwrite(os.path.join(OUT_DIR, f'{group_id}_contact_sheet.jpg'), sheet)
                sheet_count += 1

    with open(os.path.join(OUT_DIR, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    sizes = [len(m) for m in ordered_groups]
    singletons = sum(1 for s in sizes if s == 1)
    print(f'\n{len(ordered_groups)} groups from {len(entries)} clips')
    print(f'  largest group: {sizes[0] if sizes else 0} clips')
    print(f'  singletons: {singletons}')
    print(f'  contact sheets written: {sheet_count}')
    print(f'\nSaved to {OUT_DIR}')
    print('\nReminder: these are groups by CLOTHING COLOR ONLY, not confirmed')
    print('player identity -- glance at each contact sheet before labeling a')
    print('whole group as one player. Same-color != same player (shared')
    print('sponsor kits); a real player can also split across groups if they')
    print('wore different outfits in the source footage.')


if __name__ == '__main__':
    main()
