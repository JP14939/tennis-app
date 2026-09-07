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
  python prepare_ball_yolo_dataset.py <log.jsonl> [<log2.jsonl> ...]

  Defaults to data/10b_ball_detection/manual_ball_label_log_server.jsonl (the
  real 354 hand-drawn labels pulled from the hosted server -- local dev's
  `manual_ball_label_log.jsonl` is an 18-row stub and is rejected). Pass extra
  logs (e.g. wide_court_ball_labels.jsonl) and they're concatenated + deduped
  by `file`.

The output dir is wiped and rebuilt every run. The train/val split is by
CLIP (analysis id), not by frame -- adjacent frames of one swing are
near-duplicates, and a frame-level split leaks them across the boundary
(the pre-2026-09-07 version did exactly that -- 76 images in both splits).
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

DEFAULT_LOG_PATH = os.path.join(DATA_DIR, '10b_ball_detection', 'manual_ball_label_log_server.jsonl')
MIN_ROWS = 100  # guard against an accidental run on the 18-row local stub
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


def _clip_id(file_name):
    """Group key for the train/val split. `analysisNNN_...` frames of one
    swing share a key (they're near-duplicates -- must not straddle the
    split); anything else (wide_court_*, IMG_5755_* negatives) is its own
    group."""
    m = FILE_PATTERN.match(file_name)
    return m.group(1) if m else file_name


def main():
    log_paths = sys.argv[1:] or [DEFAULT_LOG_PATH]

    records, seen = [], set()
    for lp in log_paths:
        with open(lp, encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r['file'] in seen:
                    continue
                seen.add(r['file'])
                records.append(r)
    if len(records) < MIN_ROWS:
        sys.exit(f'Only {len(records)} label rows from {log_paths} -- refusing to build a '
                 f'dataset (looks like the local stub, not the real server log).')

    excluded = find_fully_static_files(records)
    usable = [r for r in records if r['file'] not in excluded]

    # split by CLIP, not by frame
    by_clip = collections.defaultdict(list)
    for r in usable:
        by_clip[_clip_id(r['file'])].append(r)
    clip_ids = sorted(by_clip)
    random.shuffle(clip_ids)
    n_val_clips = max(1, int(len(clip_ids) * VAL_FRAC))
    val_clip_ids = set(clip_ids[:n_val_clips])

    split_recs = {'train': [], 'val': []}
    for cid, recs in by_clip.items():
        split_recs['val' if cid in val_clip_ids else 'train'].extend(recs)

    # rebuild the dataset dir from scratch every run -- a stale file from a
    # prior run with a different input set is how 76 images ended up in both
    # train and val (pre-2026-09-07).
    shutil.rmtree(DATASET_DIR, ignore_errors=True)
    for split in ['train', 'val']:
        os.makedirs(os.path.join(DATASET_DIR, 'images', split))
        os.makedirs(os.path.join(DATASET_DIR, 'labels', split))

    counts = {}
    written_files = {'train': set(), 'val': set()}
    for split in ['train', 'val']:
        n_pos = n_neg = 0
        for r in split_recs[split]:
            out_img = os.path.join(DATASET_DIR, 'images', split, r['file'])
            out_lbl = os.path.join(DATASET_DIR, 'labels', split, os.path.splitext(r['file'])[0] + '.txt')
            if not write_example(r, out_img, out_lbl):
                continue
            written_files[split].add(r['file'])
            if r.get('ball_visible') and r.get('box_norm'):
                n_pos += 1
            else:
                n_neg += 1
        counts[split] = {'positive': n_pos, 'negative': n_neg}

    # hard guarantees
    assert not (written_files['train'] & written_files['val']), 'train/val image overlap'
    train_clips = {_clip_id(f) for f in written_files['train']}
    val_clips = {_clip_id(f) for f in written_files['val']}
    assert not (train_clips & val_clips), 'train/val clip-id overlap'

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
