"""
v6 dataset -- SAME labels as v4 (v2+v3 positives + v1 negatives), but split by
SOURCE GROUP instead of per-frame.

Why: v2-v5 all do `random.shuffle` + per-frame 20% val. The two fixed-mount
match videos (mark_vs_silas, nicolas_vs_florian) use ONE identical canonical
label for every sampled frame, so near-duplicate frames land in both train and
val and the reported Pose mAP (0.955 for v4) is inflated. A group split -- whole
source videos / compilation buckets go entirely to train xor val -- gives an
honest number and lets early-stopping work against real signal.

Groups:
  real_mark              all mark_vs_silas_* frames
  real_nico              all nicolas_vs_florian_* frames
  pro_<shot>_b<bucket>   pro clips, grouped by (shot in filename, swing_id // 1000)
  neg_<0..2>             confirmed negatives, hashed into 3 groups

Whole groups are assigned to val until ~VAL_FRAC of frames are covered
(seeded, deterministic). Everything else trains.

Output: data/10_net_detection/yolo_pose_dataset_v6/
"""
import hashlib
import json
import os
import random
import re
import shutil

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
NET_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'data', '10_net_detection'))

POSITIVE_SOURCES = [
    (os.path.join(NET_DIR, 'net_geometry_labels_v2.json'), os.path.join(NET_DIR, 'own_footage_frames_v2')),
    (os.path.join(NET_DIR, 'net_geometry_labels_v3.json'), os.path.join(NET_DIR, 'own_footage_frames_v3')),
]
NEGATIVE_SOURCE = (os.path.join(NET_DIR, 'net_geometry_labels_negatives_v1.json'),
                   os.path.join(NET_DIR, 'net_negatives_v1', 'raw'))
DATASET_DIR = os.path.join(NET_DIR, 'yolo_pose_dataset_v6')

POINTS = ['net_top_left', 'net_top_right', 'left_post_base', 'right_post_base']
PAD_FRAC = 0.15
VAL_FRAC = 0.22
SEED = 9


def group_for_positive(frame_file):
    if frame_file.startswith('mark_vs_silas'):
        return 'real_mark'
    if frame_file.startswith('nicolas_vs_florian'):
        return 'real_nico'
    m = re.match(r'(forehand|backhand|serve)_swing_(\d+)', frame_file)
    if m:
        return f'pro_{m.group(1)}_b{int(m.group(2)) // 1000}'
    return f'pro_other_{frame_file[:6]}'


def group_for_negative(frame_file):
    h = int(hashlib.md5(frame_file.encode()).hexdigest(), 16)
    return f'neg_{h % 3}'


def write_positive(item, frames_dir, out_img, out_lbl):
    img = cv2.imread(os.path.join(frames_dir, item['frame_file']))
    if img is None:
        return False
    h, w = img.shape[:2]
    present = {p: item['keypoints'][p] for p in POINTS if item['keypoints'].get(p) is not None}
    if 'net_top_left' not in present or 'net_top_right' not in present:
        return False
    clamped = {p: (min(max(pt[0], 0), w - 1), min(max(pt[1], 0), h - 1)) for p, pt in present.items()}
    xs = [pt[0] for pt in clamped.values()]; ys = [pt[1] for pt in clamped.values()]
    x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    pad_x, pad_y = (x2 - x1) * PAD_FRAC, max((y2 - y1) * PAD_FRAC, 10)
    x1, x2 = max(0, x1 - pad_x), min(w, x2 + pad_x)
    y1, y2 = max(0, y1 - pad_y), min(h, y2 + pad_y)
    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
    bw, bh = (x2 - x1) / w, (y2 - y1) / h
    kp_str = ''
    for p in POINTS:
        if p in clamped:
            kx, ky = clamped[p]
            kp_str += f' {kx / w:.6f} {ky / h:.6f} 2'
        else:
            kp_str += ' 0.000000 0.000000 0'
    shutil.copy(os.path.join(frames_dir, item['frame_file']), out_img)
    with open(out_lbl, 'w') as f:
        f.write(f'0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}{kp_str}\n')
    return True


def write_negative(item, frames_dir, out_img, out_lbl):
    img = cv2.imread(os.path.join(frames_dir, item['frame_file']))
    if img is None:
        return False
    shutil.copy(os.path.join(frames_dir, item['frame_file']), out_img)
    open(out_lbl, 'w').close()
    return True


def main():
    for split in ('train', 'val'):
        os.makedirs(os.path.join(DATASET_DIR, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, 'labels', split), exist_ok=True)

    items = []  # (kind, item, frames_dir, group)
    for labels_path, frames_dir in POSITIVE_SOURCES:
        with open(labels_path) as f:
            for it in json.load(f)['labels']:
                if it['usable']:
                    items.append(('pos', it, frames_dir, group_for_positive(it['frame_file'])))
    neg_labels_path, neg_frames_dir = NEGATIVE_SOURCE
    with open(neg_labels_path) as f:
        for it in json.load(f)['labels']:
            if it.get('has_tennis_net') is False:
                items.append(('neg', it, neg_frames_dir, group_for_negative(it['frame_file'])))

    groups = {}
    for rec in items:
        groups.setdefault(rec[3], []).append(rec)
    total = len(items)

    # Deterministic group selection for val: one negative group (so val keeps an
    # FP signal) + positive groups until ~VAL_FRAC of frames are covered. The
    # robust version is group-k-fold -- with ~9 groups a single split is
    # high-variance; see eval_net_keypoints.py for the real keep/ship gate.
    rng = random.Random(SEED)
    pos_groups = sorted(g for g in groups if g.startswith(('pro_', 'real_')))
    neg_groups = sorted(g for g in groups if g.startswith('neg_'))
    rng.shuffle(pos_groups)
    val_groups, n_val = set(), 0
    if neg_groups:
        val_groups.add(neg_groups[0]); n_val += len(groups[neg_groups[0]])
    for g in pos_groups:
        if n_val >= VAL_FRAC * total:
            break
        val_groups.add(g); n_val += len(groups[g])

    counts = {'train': {'pos': 0, 'neg': 0}, 'val': {'pos': 0, 'neg': 0}}
    group_split = {}
    for g, recs in groups.items():
        split = 'val' if g in val_groups else 'train'
        group_split[g] = split
        for kind, item, frames_dir, _ in recs:
            out_img = os.path.join(DATASET_DIR, 'images', split, item['frame_file'])
            out_lbl = os.path.join(DATASET_DIR, 'labels', split,
                                   os.path.splitext(item['frame_file'])[0] + '.txt')
            ok = (write_positive if kind == 'pos' else write_negative)(item, frames_dir, out_img, out_lbl)
            if ok:
                counts[split][kind] += 1

    with open(os.path.join(DATASET_DIR, 'data.yaml'), 'w') as f:
        f.write(f"path: {DATASET_DIR}\ntrain: images/train\nval: images/val\n\n"
                f"kpt_shape: [4, 3]\nflip_idx: [1, 0, 3, 2]\n\nnames:\n  0: net\n")
    with open(os.path.join(DATASET_DIR, 'group_split.json'), 'w') as f:
        json.dump({'val_frac_target': VAL_FRAC, 'seed': SEED,
                   'group_split': group_split,
                   'group_sizes': {g: len(v) for g, v in groups.items()}}, f, indent=2)

    print(f'{len(groups)} groups, {len(val_groups)} to val')
    print(f'Train: {counts["train"]["pos"]} pos + {counts["train"]["neg"]} neg')
    print(f'Val:   {counts["val"]["pos"]} pos + {counts["val"]["neg"]} neg')
    print(f'val groups: {sorted(val_groups)}')
    print(f'Dataset -> {DATASET_DIR}')


if __name__ == '__main__':
    main()
