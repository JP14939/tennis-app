"""
v10 dataset -- the recall-focused retrain (see plan
~/.claude/plans/okay-yes-lets-write-majestic-wilkinson.md progress log 2026-09-08).

Three changes from v4/v6:
  1. TWO keypoints only -- net_top_left, net_top_right. Post bases are dropped:
     eval_net_keypoints.py showed them ~1x net-width off in every model (the
     build_labels_v3.py post-base labels are synthetic), and their only
     consumers (net elevation, homography azimuth) are being retired.
  2. The 105 hand-labeled amateur frames (net_keypoint_testset_v1) are folded in
     as TRAINING data -- they're the real target domain and v4 only finds a net
     on 21% of them.
  3. Source-group split that holds out 3 whole amateur videos as the val/test
     set, so we get an honest generalization number with no fence footage yet.

Groups (whole group -> train xor val):
  amat_<video_id>       one amateur video's frames  (3 held out to val)
  real_mark / real_nico fixed-mount pro match videos
  pro_<shot>_b<bucket>  pro clips by (shot, swing_id//1000)
  neg_<0..2>            confirmed no-net images, hashed

Output: data/10_net_detection/yolo_pose_dataset_v10/  (kpt_shape [2,3], flip_idx [1,0])
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

PRO_SOURCES = [
    (os.path.join(NET_DIR, 'net_geometry_labels_v2.json'), os.path.join(NET_DIR, 'own_footage_frames_v2')),
    (os.path.join(NET_DIR, 'net_geometry_labels_v3.json'), os.path.join(NET_DIR, 'own_footage_frames_v3')),
    (os.path.join(NET_DIR, 'net_geometry_labels_stock_v1.json'), os.path.join(NET_DIR, 'stock_frames_v1')),
]
AMATEUR_LABELS = os.path.join(NET_DIR, 'net_keypoint_testset_v1', 'net_keypoint_testset_v1_labels.json')
AMATEUR_FRAMES = os.path.join(NET_DIR, 'net_keypoint_testset_v1', 'frames')
NEG_SOURCE = (os.path.join(NET_DIR, 'net_geometry_labels_negatives_v1.json'),
              os.path.join(NET_DIR, 'net_negatives_v1', 'raw'))
DATASET_DIR = os.path.join(NET_DIR, 'yolo_pose_dataset_v10')

TOP = ['net_top_left', 'net_top_right']
PAD_FRAC = 0.20
SEED = 10
# 3 amateur videos held out entirely as val (rest of the val target filled with negs)
HELDOUT_AMATEUR = {'AQvVlROWI2k', 'PnIwyWDY76k', 'xDNUeZ6Svw0'}


def group_for_pro(fn):
    if fn.startswith('mark_vs_silas'):
        return 'real_mark'
    if fn.startswith('nicolas_vs_florian'):
        return 'real_nico'
    m = re.match(r'(forehand|backhand|serve)_swing_(\d+)', fn)
    return f'pro_{m.group(1)}_b{int(m.group(2)) // 1000}' if m else f'pro_other_{fn[:6]}'


def write_top2(frame_path, kp, out_img, out_lbl):
    img = cv2.imread(frame_path)
    if img is None:
        return False
    h, w = img.shape[:2]
    if kp.get('net_top_left') is None or kp.get('net_top_right') is None:
        return False
    pts = {p: (min(max(kp[p][0], 0), w - 1), min(max(kp[p][1], 0), h - 1)) for p in TOP}
    xs = [p[0] for p in pts.values()]; ys = [p[1] for p in pts.values()]
    x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    pad_x = max((x2 - x1) * PAD_FRAC, 15); pad_y = max((y2 - y1) * PAD_FRAC, 25)
    x1, x2 = max(0, x1 - pad_x), min(w, x2 + pad_x)
    y1, y2 = max(0, y1 - pad_y), min(h, y2 + pad_y)
    cx, cy, bw, bh = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h, (x2 - x1) / w, (y2 - y1) / h
    kp_str = ''.join(f' {pts[p][0] / w:.6f} {pts[p][1] / h:.6f} 2' for p in TOP)
    shutil.copy(frame_path, out_img)
    with open(out_lbl, 'w') as f:
        f.write(f'0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}{kp_str}\n')
    return True


def main():
    for s in ('train', 'val'):
        os.makedirs(os.path.join(DATASET_DIR, 'images', s), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, 'labels', s), exist_ok=True)

    items = []  # (frame_path, kp_or_None, group, is_neg)
    for lp, fd in PRO_SOURCES:
        if not os.path.exists(lp):
            continue
        for it in json.load(open(lp))['labels']:
            if it.get('usable') and it['keypoints'].get('net_top_left') and it['keypoints'].get('net_top_right'):
                items.append((os.path.join(fd, it['frame_file']), it['keypoints'],
                              group_for_pro(it['frame_file']), False))
    for it in json.load(open(AMATEUR_LABELS))['labels']:
        if it.get('usable') and it['keypoints'].get('net_top_left') and it['keypoints'].get('net_top_right'):
            vid = it.get('source_video') or 'amat_unknown'
            items.append((os.path.join(AMATEUR_FRAMES, it['frame_file']), it['keypoints'], f'amat_{vid}', False))
    nlp, nfd = NEG_SOURCE
    for it in json.load(open(nlp))['labels']:
        if it.get('has_tennis_net') is False:
            g = f"neg_{int(hashlib.md5(it['frame_file'].encode()).hexdigest(), 16) % 3}"
            items.append((os.path.join(nfd, it['frame_file']), None, g, True))

    groups = {}
    for rec in items:
        groups.setdefault(rec[2], []).append(rec)

    rng = random.Random(SEED)
    val_groups = {f'amat_{v}' for v in HELDOUT_AMATEUR}
    neg_gs = sorted(g for g in groups if g.startswith('neg_'))
    if neg_gs:
        val_groups.add(rng.choice(neg_gs))

    counts = {'train': [0, 0], 'val': [0, 0]}
    split_map = {}
    for g, recs in groups.items():
        split = 'val' if g in val_groups else 'train'
        split_map[g] = split
        for fp, kp, _, is_neg in recs:
            stem = os.path.splitext(os.path.basename(fp))[0]
            oi = os.path.join(DATASET_DIR, 'images', split, os.path.basename(fp))
            ol = os.path.join(DATASET_DIR, 'labels', split, stem + '.txt')
            if is_neg:
                img = cv2.imread(fp)
                if img is None:
                    continue
                shutil.copy(fp, oi); open(ol, 'w').close()
                counts[split][1] += 1
            elif write_top2(fp, kp, oi, ol):
                counts[split][0] += 1

    with open(os.path.join(DATASET_DIR, 'data.yaml'), 'w') as f:
        f.write(f"path: {DATASET_DIR}\ntrain: images/train\nval: images/val\n\n"
                f"kpt_shape: [2, 3]\nflip_idx: [1, 0]\n\nnames:\n  0: net\n")
    with open(os.path.join(DATASET_DIR, 'group_split.json'), 'w') as f:
        json.dump({'seed': SEED, 'heldout_amateur': sorted(HELDOUT_AMATEUR),
                   'val_groups': sorted(val_groups), 'split': split_map,
                   'group_sizes': {g: len(v) for g, v in groups.items()}}, f, indent=2)

    print(f'{len(groups)} groups; val = {sorted(val_groups)}')
    print(f'Train: {counts["train"][0]} pos + {counts["train"][1]} neg')
    print(f'Val:   {counts["val"][0]} pos + {counts["val"][1]} neg')
    print(f'-> {DATASET_DIR}')


if __name__ == '__main__':
    main()
