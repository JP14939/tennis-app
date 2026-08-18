"""
Ad hoc accuracy check requested directly: 9 real tennis-net photos the user
dropped in their Downloads folder (tennis_net.jpg, tennis_net1.jpg,
tennis_net3.jpg..tennis_net9.jpeg -- no tennis_net2, a gap in their own
naming) as the positive set, plus a freshly-sourced batch of random non-net
images (different queries from both the training negatives and the earlier
streettest_negatives held-out set, so this is a genuinely independent check,
not a re-test of images the model has any exposure to) as the negative set.

Reuses evaluate_image()/annotate_and_save() from
test_net_detector_labeled_set.py rather than duplicating detection logic.

Usage:
  python test_net_detector_downloads.py
"""
import glob
import os
import sys

from test_net_detector_labeled_set import evaluate_image, annotate_and_save
import infer_angle

DOWNLOADS_DIR = os.path.expanduser('~/Downloads')
NEG_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\downloads_test_negatives'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\downloads_test_results'


def main():
    if len(sys.argv) > 1:
        infer_angle.NET_KEYPOINT_MODEL_PATH = sys.argv[1]
        infer_angle._net_kp_model = None
        print(f'Using net-keypoint model: {sys.argv[1]}\n')
    os.makedirs(OUT_DIR, exist_ok=True)

    positives = sorted(glob.glob(os.path.join(DOWNLOADS_DIR, 'tennis_net*.jpg'))) + \
        sorted(glob.glob(os.path.join(DOWNLOADS_DIR, 'tennis_net*.jpeg')))
    negatives = sorted(glob.glob(os.path.join(NEG_DIR, '*.jpg'))) + \
        sorted(glob.glob(os.path.join(NEG_DIR, '*.jpeg')))

    print(f'{len(positives)} known-net images from Downloads, {len(negatives)} random no-net images\n')

    rows = []
    for label, paths, src_dir in (('net', positives, DOWNLOADS_DIR), ('no_net', negatives, NEG_DIR)):
        for path in paths:
            result = evaluate_image(path)
            rows.append((label, os.path.basename(path), path, result))

    print(f'{"label":8} {"file":30} {"ok":6} {"conf":6} {"method":16} message')
    print('-' * 100)
    tp = fp = tn = fn = 0
    misclassified = []
    for label, fname, path, r in rows:
        print(f'{label:8} {fname:30} {str(r["ok"]):6} {r["confidence"]:<6.2f} {r["method"]:16} {r["message"][:50]}')
        is_net_truth = (label == 'net')
        predicted_net = r['ok']
        if is_net_truth and predicted_net:
            tp += 1
        elif is_net_truth and not predicted_net:
            fn += 1
            misclassified.append((label, fname, path, r))
        elif not is_net_truth and predicted_net:
            fp += 1
            misclassified.append((label, fname, path, r))
        else:
            tn += 1

    total = len(rows)
    correct = tp + tn
    print('\n--- Summary ---')
    print(f'Total: {total}  |  Correct: {correct}/{total} = {correct / total:.1%}')
    print(f'True positives: {tp}/{len(positives)}   True negatives: {tn}/{len(negatives)}   '
          f'False positives: {fp}   False negatives: {fn}')

    if misclassified:
        print(f'\nSaving {len(misclassified)} misclassified images to {OUT_DIR}...')
        for label, fname, path, r in misclassified:
            out_path = os.path.join(OUT_DIR, f'MISCLASSIFIED_{label}_{fname}')
            annotate_and_save(path, r, out_path)
            print(f'  {out_path}')
    else:
        print('\nNo misclassifications -- 100% correct.')


if __name__ == '__main__':
    main()
