"""
Assemble the source-disjoint net-keypoint test set (net_keypoint_testset_v1).

Produces data/10_net_detection/net_keypoint_testset_v1/
  frames/                one .jpg per test frame
  frame_manifest.json    [{frame_file, source_kind, source_video, origin_name,
                           shot_type, swing_bucket, frame_idx, notes}]

Then label frames/ with label_net_keypoints.py and gate with
check_testset_disjoint.py before trusting any eval number.

Buckets:
  A amateur   -- data/04_clips/amateur/ (9 YouTube match videos). Never used in
                 any net_geometry_labels_v*.json. ~12 clips/video, 1 frame each.
  B held-pro  -- data/04_clips/{forehand,backhand,serve}/ clips whose basename is
                 NOT in any training label file AND whose (shot, swing_id//1000)
                 bucket was never sampled by the v2/v3 labelers. May be empty --
                 that's a finding, not a bug.
  D negatives -- streettest_negatives/ + downloads_test_negatives/ copied as-is
                 (already held out of training; for FP / return-rate context).

Bucket C (Jack's fence footage) is added later by a separate call once the 0c
footage exists -- see --fence-dir.

Usage
  python build_testset_v1_frames.py
  python build_testset_v1_frames.py --amateur-per-video 12 --held-pro 30 --seed 7
  python build_testset_v1_frames.py --fence-dir PATH --fence-per-video 8   # bucket C, later
"""
import argparse
import glob
import json
import os
import random
import re
import shutil
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', '..', 'data'))
NET_DIR = os.path.join(DATA, '10_net_detection')
CLIPS = os.path.join(DATA, '04_clips')
OUT_DIR = os.path.join(NET_DIR, 'net_keypoint_testset_v1')
FRAMES_DIR = os.path.join(OUT_DIR, 'frames')
MANIFEST = os.path.join(OUT_DIR, 'frame_manifest.json')

TRAINING_LABEL_JSONS = [
    'net_geometry_labels_v2.json', 'net_geometry_labels_v3.json',
    'net_geometry_labels_stock_v1.json', 'net_geometry_labels_negatives_v1.json',
]
NEG_DIRS = ['streettest_negatives', 'downloads_test_negatives']


def training_frame_names():
    names = set()
    for j in TRAINING_LABEL_JSONS:
        p = os.path.join(NET_DIR, j)
        if not os.path.exists(p):
            continue
        with open(p) as f:
            data = json.load(f)
        names |= {it['frame_file'] for it in data.get('labels', [])}
    return names


def swing_id_of(name):
    m = re.search(r'_swing_(\d+)', name)
    return int(m.group(1)) if m else None


def trained_shot_buckets(train_names):
    """(shot, swing_id//1000) pairs that appear among training frame names."""
    pairs = set()
    for n in train_names:
        m = re.match(r'(forehand|backhand|serve)_swing_(\d+)', n)
        if m:
            pairs.add((m.group(1), int(m.group(2)) // 1000))
    return pairs


def grab_frame(video_path, frac):
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return None, None
    fi = max(0, min(int(total * frac), total - 1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ok, frame = cap.read()
    cap.release()
    return (frame, fi) if ok else (None, None)


def bucket_a(rows, per_video, seed):
    man_path = os.path.join(CLIPS, 'amateur', 'manifest.json')
    with open(man_path) as f:
        manifest = json.load(f)
    by_vid = {}
    for m in manifest:
        by_vid.setdefault(m['video_id'], []).append(m)
    rng = random.Random(seed)
    for vid, items in sorted(by_vid.items()):
        picks = rng.sample(items, min(per_video, len(items)))
        for m in picks:
            clip = os.path.join(CLIPS, 'amateur', os.path.basename(m['clip_path']))
            if not os.path.exists(clip):
                continue
            frame, fi = grab_frame(clip, 0.20)
            if frame is None:
                continue
            fn = f'A_amateur_{vid}_swing_{m["swing_id"]}.jpg'
            cv2.imwrite(os.path.join(FRAMES_DIR, fn), frame)
            rows.append({'frame_file': fn, 'source_kind': 'amateur', 'source_video': vid,
                         'origin_name': os.path.basename(clip), 'shot_type': None,
                         'swing_bucket': None, 'frame_idx': fi, 'notes': ''})


def bucket_b(rows, n_total, seed, train_names, loose=False):
    trained_pairs = trained_shot_buckets(train_names)
    rng = random.Random(seed + 1)
    cands = []
    for shot in ('forehand', 'backhand', 'serve'):
        for clip in glob.glob(os.path.join(CLIPS, shot, '*.mp4')):
            base = os.path.basename(clip)
            if os.path.splitext(base)[0] + '.jpg' in train_names:
                continue
            sid = swing_id_of(base)
            if sid is None:
                continue
            m = re.match(r'(forehand|backhand|serve)_swing_', base)
            name_shot = m.group(1) if m else shot
            # strict: exclude any clip sharing a (shot, compilation-bucket) with
            # training. loose: only exclude exact labeled clips (weaker -- same
            # match, different swing can still leak). Jack's call (plan open #2).
            if not loose and (name_shot, sid // 1000) in trained_pairs:
                continue
            cands.append((shot, name_shot, sid, clip))
    rng.shuffle(cands)
    picked = cands[:n_total]
    if not picked:
        print('  bucket B: NO leakage-free held-out pro clips found '
              '(every (shot,bucket) pair was sampled in training). Skipping bucket B.',
              file=sys.stderr)
    for shot, name_shot, sid, clip in picked:
        frame, fi = grab_frame(clip, 0.15)
        if frame is None:
            continue
        fn = f'B_pro_{name_shot}_swing_{sid}.jpg'
        cv2.imwrite(os.path.join(FRAMES_DIR, fn), frame)
        rows.append({'frame_file': fn, 'source_kind': 'held_pro', 'source_video': f'{shot}_dir',
                     'origin_name': os.path.basename(clip), 'shot_type': name_shot,
                     'swing_bucket': sid // 1000, 'frame_idx': fi, 'notes': ''})


def bucket_d(rows):
    for d in NEG_DIRS:
        src = os.path.join(NET_DIR, d)
        if not os.path.isdir(src):
            continue
        for img in sorted(glob.glob(os.path.join(src, '*'))):
            if not img.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            fn = f'D_neg_{d}_{os.path.basename(img)}'
            fn = os.path.splitext(fn)[0] + '.jpg'
            im = cv2.imread(img)
            if im is None:
                continue
            cv2.imwrite(os.path.join(FRAMES_DIR, fn), im)
            rows.append({'frame_file': fn, 'source_kind': 'negative', 'source_video': d,
                         'origin_name': os.path.basename(img), 'shot_type': None,
                         'swing_bucket': None, 'frame_idx': 0, 'notes': 'no-net'})


def bucket_c(rows, fence_dir, per_video, seed):
    rng = random.Random(seed + 2)
    vids = [d for d in glob.glob(os.path.join(fence_dir, '*')) if d.lower().endswith(('.mp4', '.mov'))]
    for v in sorted(vids):
        cap = cv2.VideoCapture(v)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        if total <= 0:
            continue
        stem = os.path.splitext(os.path.basename(v))[0]
        fracs = sorted(rng.uniform(0.05, 0.95) for _ in range(per_video))
        for j, fr in enumerate(fracs):
            frame, fi = grab_frame(v, fr)
            if frame is None:
                continue
            fn = f'C_fence_{stem}_{j:02d}.jpg'
            cv2.imwrite(os.path.join(FRAMES_DIR, fn), frame)
            rows.append({'frame_file': fn, 'source_kind': 'fence', 'source_video': stem,
                         'origin_name': os.path.basename(v), 'shot_type': None,
                         'swing_bucket': None, 'frame_idx': fi, 'notes': 'bucket C fence footage'})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--amateur-per-video', type=int, default=12)
    ap.add_argument('--held-pro', type=int, default=30)
    ap.add_argument('--held-pro-loose', action='store_true',
                    help='bucket B: only exclude exact labeled clips, not whole (shot,bucket) pairs')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--fence-dir', default=None, help='bucket C: dir of fence-footage videos (added later)')
    ap.add_argument('--fence-per-video', type=int, default=8)
    ap.add_argument('--only', choices=['A', 'B', 'C', 'D'], default=None)
    args = ap.parse_args()

    os.makedirs(FRAMES_DIR, exist_ok=True)
    rows = []
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as f:
            rows = json.load(f)
        have = {r['frame_file'] for r in rows}
        print(f'Existing manifest: {len(rows)} rows. New frames will be appended.')
    else:
        have = set()

    train_names = training_frame_names()
    print(f'{len(train_names)} training frame names loaded for disjointness.')

    def keep_new(new_rows):
        for r in new_rows:
            if r['frame_file'] not in have:
                rows.append(r); have.add(r['frame_file'])

    if args.only in (None, 'A'):
        tmp = []; bucket_a(tmp, args.amateur_per_video, args.seed); keep_new(tmp)
    if args.only in (None, 'B'):
        tmp = []; bucket_b(tmp, args.held_pro, args.seed, train_names, args.held_pro_loose); keep_new(tmp)
    if args.only in (None, 'D'):
        tmp = []; bucket_d(tmp); keep_new(tmp)
    if args.fence_dir and args.only in (None, 'C'):
        tmp = []; bucket_c(tmp, args.fence_dir, args.fence_per_video, args.seed); keep_new(tmp)

    with open(MANIFEST, 'w') as f:
        json.dump(rows, f, indent=2)

    from collections import Counter
    kinds = Counter(r['source_kind'] for r in rows)
    print(f'\nWrote {len(rows)} frames to {FRAMES_DIR}')
    for k, c in sorted(kinds.items()):
        print(f'  {k}: {c}')
    print(f'\nNext: python label_net_keypoints.py --frames-dir {FRAMES_DIR} '
          f'--out {os.path.join(OUT_DIR, "net_keypoint_testset_v1_labels.json")} '
          f'--prefill-model yolo_pose_run_v4')
    print(f'Then: python check_testset_disjoint.py')


if __name__ == '__main__':
    main()
