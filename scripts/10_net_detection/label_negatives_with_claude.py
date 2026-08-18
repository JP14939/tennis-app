"""
Batch driver: runs net_presence_verifier.py's Claude teacher over every
sourced candidate negative in data/10_net_detection/net_negatives_v1/raw/
and writes confirmed negatives (has_tennis_net == false) out in the same
{frame_file, usable, keypoints: {all null}} shape as
net_geometry_labels_v3.json's existing "usable: false" entries, so
prepare_net_pose_dataset_v4.py can treat both uniformly.

Candidates Claude flags as has_tennis_net == true (Openverse search results
are noisy -- a "badminton net court" query can return a real tennis photo)
are EXCLUDED, not force-labeled -- we only want confirmed true negatives in
training data, not mislabeled positives fed in as background images.

Usage:
  python label_negatives_with_claude.py
"""
import glob
import json
import os
import time

from net_presence_verifier import verify_net_presence

RAW_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\net_negatives_v1\raw'
OUT_PATH = r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_negatives_v1.json'


def main():
    images = sorted(glob.glob(os.path.join(RAW_DIR, '*.jpg')) + glob.glob(os.path.join(RAW_DIR, '*.jpeg')))
    print(f'{len(images)} candidate images to label\n')

    labels = []
    confirmed = rejected = errors = 0
    for path in images:
        fname = os.path.basename(path)
        try:
            result = verify_net_presence(path)
        except Exception as e:
            print(f'  ERROR {fname}: {e}')
            errors += 1
            time.sleep(1)
            continue

        has_net = result.get('has_tennis_net')
        reasoning = result.get('reasoning', '')
        if has_net:
            print(f'  REJECTED (Claude found a tennis net) {fname}: {reasoning}')
            rejected += 1
            continue

        print(f'  confirmed negative: {fname} -- {reasoning}')
        labels.append({
            'frame_file': fname,
            'usable': False,
            'has_tennis_net': False,
            'reasoning': reasoning,
            'keypoints': {'net_top_left': None, 'net_top_right': None,
                          'left_post_base': None, 'right_post_base': None},
        })
        confirmed += 1
        time.sleep(0.3)  # light pacing, not strictly required but polite to the API

    with open(OUT_PATH, 'w') as f:
        json.dump({'_meta': {'source_dir': RAW_DIR, 'labeler': 'claude-sonnet-5 (net_presence_verifier.py)'},
                    'labels': labels}, f, indent=2)

    print(f'\nConfirmed negatives: {confirmed}  Rejected (had a net): {rejected}  Errors: {errors}')
    print(f'Written to {OUT_PATH}')


if __name__ == '__main__':
    main()
