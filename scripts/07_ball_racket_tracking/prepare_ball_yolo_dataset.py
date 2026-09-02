"""
Build the YOLO detection dataset for Phase 3 ball-detector fine-tuning, from
Jack's real manual labels (`manual_ball_label_log.jsonl` -- 354 frames, all
logged against the hosted server since that's where the Dev Page Ball Label
tool was used; see HANDOVER.md item #43).

Excludes the 5 clips / 16 labels `audit_ball_label_motion.py` flagged as
fully-static (a static decoy boxed instead of the real in-play ball) --
Jack confirmed all 5 as real decoys 2026-08-25 (TODO_MANUAL.md). A frame
with `ball_visible: false` becomes a genuine negative (empty label file),
same convention `prepare_net_pose_dataset_v5.py` uses for net negatives.

Usage:
  python prepare_ball_yolo_dataset.py [path/to/manual_ball_label_log.jsonl]

  Defaults to data/10b_ball_detection/manual_ball_label_log.jsonl -- pass an
  explicit path when using a copy pulled from the hosted server (local dev's
  own copy is a handful of test entries, not the real 354).
"""
import collections
import json
import math
import os
import random
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

DEFAULT_LOG_PATH = os.path.join(DATA_DIR, '10b_ball_detection', 'manual_ball_label_log.jsonl')
FRAMES_DIR = os.path.join(DATA_DIR, '10b_ball_detection', 'candidate_frames')
DATASET_DIR = os.path.join(DATA_DIR, '10b_ball_detection', 'yolo_dataset_v1')

FILE_PATTERN = re.compile(r'^(analysis\d+)_f(\d+)_')
STATIONARY_THRESHOLD_PER_FRAME = 0.004  # matches audit_ball_label_motion.py
VAL_FRAC = 0.2

random.seed(9)


def box_center(box_norm):
    return (box_norm['x1'] + box_norm['x2']) / 2, (box_norm['y1'] + box_norm['y2']) / 2


def find_fully_static_files(records):
    """Reimplements audit_ball_label_motion.py's flagging so this script has
    no dependency on that one having been run first / its output file being
    fresh. Same logic, same threshold, same clip grouping."""
    groups = collections.defaultdict(list)
    for r in records:
        if not r.get('ball_visible') or not r.get('box_norm'):
            continue
        m = FILE_PATTERN.match(r['file'])
        if not m:
            continue
        groups[m.group(1)].append((int(m.group(2)), r))
    for clip_id in groups:
        groups[clip_id].sort(key=lambda pair: pair[0])

    static_files = set()
    for clip_id, items in groups.items():
        if len(items) < 2:
            continue
        pair_flags = []
        for (f0, r0), (f1, r1) in zip(items, items[1:]):
            gap = f1 - f0
            if gap <= 0:
                continue
            (x0, y0), (x1, y1) = box_center(r0['box_norm']), box_center(r1['box_norm'])
            pair_flags.append(math.hypot(x1 - x0, y1 - y0) / gap < STATIONARY_THRESHOLD_PER_FRAME)
        if pair_flags and all(pair_flags):
            static_files.update(r['file'] for _, r in items)
    return static_files


def write_example(record, out_img, out_lbl):
    src = os.path.join(FRAMES_DIR, record['bucket'], record['file'])
    if not os.path.exists(src):
        return False
    shutil.copy(src, out_img)
    if record.get('ball_visible') and record.get('box_norm'):
        b = record['box_norm']
        cx, cy = (b['x1'] + b['x2']) / 2, (b['y1'] + b['y2']) / 2
        bw, bh = b['x2'] - b['x1'], b['y2'] - b['y1']
        with open(out_lbl, 'w') as f:
            f.write(f'0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n')
    else:
        open(out_lbl, 'w').close()  # negative: no ball in this frame
    return True


def main():
    log_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG_PATH
    with open(log_path, encoding='utf-8') as f:
        records = [json.loads(line) for line in f if line.strip()]

    excluded = find_fully_static_files(records)
    usable = [r for r in records if r['file'] not in excluded]

    positives = [r for r in usable if r.get('ball_visible') and r.get('box_norm')]
    negatives = [r for r in usable if not (r.get('ball_visible') and r.get('box_norm'))]
    random.shuffle(positives)
    random.shuffle(negatives)

    n_val_pos = max(6, int(len(positives) * VAL_FRAC))
    n_val_neg = max(2, int(len(negatives) * VAL_FRAC))
    pos_splits = {'val': positives[:n_val_pos], 'train': positives[n_val_pos:]}
    neg_splits = {'val': negatives[:n_val_neg], 'train': negatives[n_val_neg:]}

    for split in ['train', 'val']:
        os.makedirs(os.path.join(DATASET_DIR, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, 'labels', split), exist_ok=True)

    counts = {}
    for split in ['train', 'val']:
        n_pos = n_neg = 0
        for r in pos_splits[split]:
            out_img = os.path.join(DATASET_DIR, 'images', split, r['file'])
            out_lbl = os.path.join(DATASET_DIR, 'labels', split, os.path.splitext(r['file'])[0] + '.txt')
            if write_example(r, out_img, out_lbl):
                n_pos += 1
        for r in neg_splits[split]:
            out_img = os.path.join(DATASET_DIR, 'images', split, r['file'])
            out_lbl = os.path.join(DATASET_DIR, 'labels', split, os.path.splitext(r['file'])[0] + '.txt')
            if write_example(r, out_img, out_lbl):
                n_neg += 1
        counts[split] = {'positive': n_pos, 'negative': n_neg}

    yaml_content = f"""path: {DATASET_DIR}
train: images/train
val: images/val

names:
  0: ball
"""
    with open(os.path.join(DATASET_DIR, 'data.yaml'), 'w') as f:
        f.write(yaml_content)

    print(f'Excluded {len(excluded)} labels from {len(set(r["file"] for r in records) & excluded)} static-decoy files')
    print(f'Train: {counts["train"]["positive"]} positive + {counts["train"]["negative"]} negative')
    print(f'Val:   {counts["val"]["positive"]} positive + {counts["val"]["negative"]} negative')
    print(f'Dataset written to {DATASET_DIR}')


if __name__ == '__main__':
    main()
