"""
Turn Jack's Pro Clip Review shot-type verdicts into shot-classifier feature
rows.

Every pro-DB entry whose latest clip_review_log.jsonl verdict is in
LABEL_REVIEW_VERDICTS ({shot_type_corrected, contact_time_corrected,
label_confirmed}) has a hand-verified shot type -- either corrected
("forehand -> backhand") or explicitly confirmed correct this pass. This
extracts the same feature-row shape extract_training_features.py /
extract_training_features_from_log.py produce, into a third file that
train_shot_classifier_model.py concatenates (down-weighted -- these are
broadcast clips, not the phone footage the amateur set is).

Reuses get_poses/_probe_fps/_cache_key from extract_training_features_from_log.py
(with a separate pro_derived_poses/ cache) and extract_for_clip from
extract_training_features.py -- same MediaPipe-on-the-clip path.

Usage:
  python extract_training_features_from_pro_verdicts.py [--verdicts shot_type_corrected ...]

Output: data/14_shot_classifier/training_features_from_pro.json --
  [{clip_path, contact_frame, label, features, source, verdict, id}, ...]
"""
import argparse
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))

from paths import DATA_DIR  # noqa: E402
from clip_urls import PRO_CLIPS_DIR  # noqa: E402
import clip_review_log  # noqa: E402
from extract_training_features import extract_for_clip  # noqa: E402
from extract_training_features_from_log import get_poses, _probe_fps, _cache_key  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
PRO_POSES_CACHE_DIR = os.path.join(DATA_DIR, '14_shot_classifier', 'pro_derived_poses')
OUTPUT_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'training_features_from_pro.json')

VALID_LABELS = {'forehand', 'backhand', 'serve'}


def extract(verdict_filter=None):
    keep_verdicts = set(verdict_filter) if verdict_filter else set(clip_review_log.LABEL_REVIEW_VERDICTS)

    with open(PRO_DB_PATH, encoding='utf-8') as f:
        db = json.load(f)
    by_id = {e['id']: e for e in db['entries']}

    verdicts = clip_review_log.get_latest_verdicts()
    targets = [(eid, v) for eid, v in verdicts.items() if v in keep_verdicts and eid in by_id]

    rows, skipped = [], []
    for eid, verdict in targets:
        entry = by_id[eid]
        label = entry['shot_type']
        if label not in VALID_LABELS:
            skipped.append({'id': eid, 'reason': f'label {label!r}'})
            continue

        clip_path = os.path.join(PRO_CLIPS_DIR, entry['clip_path'])
        if not os.path.exists(clip_path):
            skipped.append({'id': eid, 'reason': 'clip not on disk'})
            continue

        fps = _probe_fps(clip_path)
        contact_frame = round(entry['clip_contact_time_sec'] * fps)
        try:
            pose_data = get_poses(clip_path, contact_frame, cache_dir=PRO_POSES_CACHE_DIR)
        except Exception as e:
            skipped.append({'id': eid, 'reason': f'pose extraction failed: {e}'})
            continue

        cache_path = os.path.join(PRO_POSES_CACHE_DIR, f'{_cache_key(clip_path, contact_frame)}.json')
        features = extract_for_clip(cache_path, contact_frame, pose_data['fps'])
        if features is None:
            skipped.append({'id': eid, 'reason': 'no pose near contact frame'})
            continue

        rows.append({
            'clip_path': clip_path, 'contact_frame': contact_frame, 'label': label,
            'features': features, 'source': 'pro_review', 'verdict': verdict, 'id': eid,
        })

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(rows, f, indent=2)

    by_label, by_verdict = {}, {}
    for r in rows:
        by_label[r['label']] = by_label.get(r['label'], 0) + 1
        by_verdict[r['verdict']] = by_verdict.get(r['verdict'], 0) + 1
    print(f'{len(rows)} feature rows written to {OUTPUT_PATH}')
    print('by label:  ', by_label)
    print('by verdict:', by_verdict)
    if skipped:
        print(f'{len(skipped)} skipped:')
        by_reason = {}
        for s in skipped:
            by_reason[s['reason']] = by_reason.get(s['reason'], 0) + 1
        for reason, n in sorted(by_reason.items(), key=lambda kv: -kv[1]):
            print(f'  {n:>3}  {reason}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verdicts', nargs='+', default=None,
                    help=f'restrict to these verdicts (default: all of {sorted(clip_review_log.LABEL_REVIEW_VERDICTS)})')
    args = ap.parse_args()
    extract(verdict_filter=args.verdicts)


if __name__ == '__main__':
    main()
