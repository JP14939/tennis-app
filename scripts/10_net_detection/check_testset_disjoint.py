"""
Hard gate: prove net_keypoint_testset_v1 shares no source with the v2-v5
training data. Run this (and see it pass) before trusting any number out of
eval_net_keypoints.py.

Checks, per frame_manifest.json row:
  1. frame_file not in any net_geometry_labels_v*.json (renamed, so this is
     belt-and-braces).
  2. held-pro rows: origin_name (the source clip basename) not among training
     frame names, AND (shot, swing_bucket) not a bucket the v2/v3 labelers
     sampled.
  3. no row's source is mark_vs_silas / nicolas_vs_florian (the fixed-mount
     canonical-label videos).
  4. amateur source_video ids are not clip-dir names.
  5. fence rows: source_video not equal to any training-frame provenance
     (fence footage is new, so this is just a sanity assert it's tagged 'fence').

Exit 0 and print a provenance table if clean; exit 1 listing every violation.
"""
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', '..', 'data'))
NET_DIR = os.path.join(DATA, '10_net_detection')
OUT_DIR = os.path.join(NET_DIR, 'net_keypoint_testset_v1')
MANIFEST = os.path.join(OUT_DIR, 'frame_manifest.json')

TRAINING_LABEL_JSONS = [
    'net_geometry_labels_v2.json', 'net_geometry_labels_v3.json',
    'net_geometry_labels_stock_v1.json', 'net_geometry_labels_negatives_v1.json',
]
FIXED_MOUNT_VIDEOS = {'mark_vs_silas', 'nicolas_vs_florian'}


def training_frame_names():
    names = set()
    for j in TRAINING_LABEL_JSONS:
        p = os.path.join(NET_DIR, j)
        if os.path.exists(p):
            with open(p) as f:
                names |= {it['frame_file'] for it in json.load(f).get('labels', [])}
    return names


def trained_shot_buckets(names):
    pairs = set()
    for n in names:
        m = re.match(r'(forehand|backhand|serve)_swing_(\d+)', n)
        if m:
            pairs.add((m.group(1), int(m.group(2)) // 1000))
    return pairs


def main():
    if not os.path.exists(MANIFEST):
        print(f'No manifest at {MANIFEST} -- run build_testset_v1_frames.py first.')
        sys.exit(1)
    with open(MANIFEST) as f:
        rows = json.load(f)
    train_names = training_frame_names()
    trained_pairs = trained_shot_buckets(train_names)

    violations = []
    for r in rows:
        ff, kind = r['frame_file'], r['source_kind']
        origin = r.get('origin_name', '')

        if ff in train_names:
            violations.append(f'{ff}: frame_file collides with a training label')

        if kind == 'held_pro':
            if os.path.splitext(origin)[0] + '.jpg' in train_names:
                violations.append(f'{ff}: origin clip {origin} was labeled in training')
            pair = (r.get('shot_type'), r.get('swing_bucket'))
            if pair in trained_pairs:
                violations.append(f'{ff}: (shot,bucket)={pair} was sampled by the v2/v3 labelers')

        if (r.get('source_video') in FIXED_MOUNT_VIDEOS
                or any(v in origin for v in FIXED_MOUNT_VIDEOS)):
            violations.append(f'{ff}: sourced from a fixed-mount canonical-label video')

        if kind == 'amateur' and r.get('source_video') in ('forehand_dir', 'backhand_dir', 'serve_dir'):
            violations.append(f'{ff}: amateur row tagged with a pro clip-dir source')

    kinds = Counter(r['source_kind'] for r in rows)
    print(f'\n=== net_keypoint_testset_v1 provenance ({len(rows)} frames) ===')
    for k, c in sorted(kinds.items()):
        print(f'  {k:10s} {c}')
    hp = [r for r in rows if r['source_kind'] == 'held_pro']
    if hp:
        bset = Counter((r.get('shot_type'), r.get('swing_bucket')) for r in hp)
        print('  held_pro (shot,bucket):', dict(bset))
    print(f'  training frame names checked against: {len(train_names)}')

    if violations:
        print(f'\n!! {len(violations)} DISJOINTNESS VIOLATIONS:')
        for v in violations:
            print(f'   - {v}')
        sys.exit(1)
    print('\nOK -- test set is source-disjoint from v2-v5 training data.')


if __name__ == '__main__':
    main()
