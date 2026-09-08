"""
Section 8 item 8 (first half): where should VIEW_GATE_MIN_ANGLE_CONF /
ANGLE_FILTER_MIN_CONF sit on the *new* (item 3) confidence distribution?

Runs check_camera_setup_frame (the single-frame path, whose confidence is the
same 0.85/0.35-base + player_vis*0.3 blend the aggregation uses per frame) over:
  - the net_keypoint_testset_v1 usable frames   -> "has net" bucket
  - the 24 downloads_test_negatives              -> "no net" bucket

Prints a coarse confidence histogram per bucket and the separation.

NOT covered here (needs assets this repo doesn't have): a labelled
"filmed from the net" / "deliberately side-on" behind-baseline set. Those
buckets, and the final threshold, wait on 0c fence footage + Jack's
front/side example clips (roadmap 1a-val).

Usage:
  python eval_view_gate_conf.py
"""
import json
import os
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import check_camera_setup_frame, create_landmarker  # noqa: E402

TESTSET = os.path.join(
    SCRIPTS_DIR, '..', 'data', '10_net_detection', 'net_keypoint_testset_v1')
TESTSET_LABELS = os.path.join(TESTSET, 'net_keypoint_testset_v1_labels.json')
NEGATIVES = os.path.join(
    SCRIPTS_DIR, '..', 'data', '10_net_detection', 'downloads_test_negatives')

BINS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.45, 0.5, 0.6, 0.7, 0.85, 1.01]


def _hist(vals):
    counts = [0] * (len(BINS) - 1)
    for v in vals:
        for i in range(len(BINS) - 1):
            if BINS[i] <= v < BINS[i + 1]:
                counts[i] += 1
                break
    return counts


def _report(name, vals):
    vals = sorted(vals)
    n = len(vals)
    print(f'\n{name}  (n={n})')
    if not n:
        return
    counts = _hist(vals)
    for i, c in enumerate(counts):
        bar = '#' * c
        print(f'  [{BINS[i]:.2f}, {BINS[i+1]:.2f})  {c:>3}  {bar}')
    print(f'  min={vals[0]:.2f}  median={vals[n // 2]:.2f}  max={vals[-1]:.2f}')
    for thr in (0.25, 0.40, 0.45, 0.50):
        print(f'  frac >= {thr}: {sum(v >= thr for v in vals) / n:.2f}')


def main():
    lm = create_landmarker()

    with open(TESTSET_LABELS) as f:
        rows = json.load(f)['labels']
    has_net, no_net_lbl = [], []
    for r in rows:
        fp = os.path.join(TESTSET, 'frames', r['frame_file'])
        img = cv2.imread(fp)
        if img is None:
            continue
        res = check_camera_setup_frame(img, landmarker=lm)
        conf = res.get('confidence', 0.0)
        if r.get('no_net'):
            no_net_lbl.append(conf)
        elif r.get('usable'):
            has_net.append(conf)

    neg = []
    if os.path.isdir(NEGATIVES):
        for fn in sorted(os.listdir(NEGATIVES)):
            if not fn.lower().endswith(('.jpg', '.png', '.jpeg')):
                continue
            img = cv2.imread(os.path.join(NEGATIVES, fn))
            if img is None:
                continue
            neg.append(check_camera_setup_frame(img, landmarker=lm).get('confidence', 0.0))

    lm.close()

    _report('has-net (testset usable)', has_net)
    _report('no-net (testset no_net label)', no_net_lbl)
    _report('no-net (downloads_test_negatives)', neg)

    print('\n--- read ---')
    print('VIEW_GATE_MIN_ANGLE_CONF is the "angle estimate is noise below this"')
    print('floor. Pick it above the bulk of the no-net confidences and below the')
    print('bulk of the has-net ones. Front / side-on behind-baseline buckets are')
    print('NOT measured here -- final value waits on 0c + Jack\'s example clips.')


if __name__ == '__main__':
    main()
