"""
Turns real logged shot-type verdicts (shot_classifier_training_log.jsonl --
every real Claude call from detect_rallies.py/analyze_rallies_parallel.py
has logged clip_path+contact_frame alongside its verdict for a while now)
into the same feature-row shape extract_training_features.py produces from
the fixed 116-clip amateur dataset, so train_shot_classifier_model.py can
train on both together. This is the "improves as more gets labeled" half of
the shot-type classifier -- re-run this (then the trainer) any time to pick
up everything logged since the last run.

Dedupes by (clip_path, contact_frame) keeping the latest record (a swing
might get logged more than once, e.g. reprocessed) and skips any whose clip
file no longer exists on disk (uploaded videos aren't kept forever) or
without a valid claude_pick to use as the label.

Usage:
  python extract_training_features_from_log.py

Output: data/14_shot_classifier/training_features_from_log.json --
  [{clip_path, contact_frame, label, features: {...}}, ...]
"""
import contextlib
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))

import cv2  # noqa: E402

from paths import DATA_DIR  # noqa: E402
from extract_poses import extract_poses  # noqa: E402
from extract_training_features import extract_for_clip  # noqa: E402
from shot_classifier_training_log import LOG_PATH  # noqa: E402

# Separate from list_swing_candidates.py's POSES_CACHE_DIR (shot_verification_batch/)
# and the amateur dataset's (17_amateur_eval/poses/) -- own cache, own naming,
# but same "extract once, cache to disk forever" pattern as both.
POSES_CACHE_DIR = os.path.join(DATA_DIR, '14_shot_classifier', 'log_derived_poses')
OUTPUT_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'training_features_from_log.json')

VALID_LABELS = {'forehand', 'backhand', 'serve'}

# clip_path here can point at a full raw upload rather than a short per-swing
# clip (detect_rallies.py logs the source video path it was called on, which
# for a highlight job is the multi-minute/GB original) -- extract_for_clip()
# only ever looks at ~1.5s around contact_frame (extract_training_features.py's
# SERVE_WINDOW_PRE_SEC/POST_SEC + a few frames of nearest_pose() search slop),
# so pose-extracting the entire file is >99% wasted work. Pad generously
# either side and let extract_poses() restrict to just that range.
WINDOW_PRE_SEC = 2.0
WINDOW_POST_SEC = 1.0


def _cache_key(clip_path, contact_frame):
    # Python's built-in hash() is randomized per-process (PYTHONHASHSEED),
    # so it can't be used for a cache key meant to survive across separate
    # runs of this script -- a later re-run to pick up new log entries would
    # get a different key for the same clip_path and silently re-extract
    # poses it already has cached. md5 is stable across runs/processes.
    # normpath() first so 'C:\...\IMG_5755.MOV' and 'C:/.../IMG_5755.MOV'
    # (both appear in the log -- different code paths logged the same file
    # with different separators) collapse to the same key instead of each
    # triggering its own full pose-extraction of the same multi-GB video.
    #
    # Keyed on (clip_path, contact_frame), not clip_path alone: since
    # get_poses() now only extracts a small window around one contact_frame
    # (see module docstring), caching by clip_path alone would mean every
    # OTHER swing sharing that same source video silently reuses the first
    # swing's narrow window and finds no pose data near its own contact
    # frame -- exactly what happened the first time this ran (5 rows
    # written, 97 wrongly skipped as "no pose near contact frame", because
    # 6 clip_paths and ~102 distinct contact_frames means most swings hit a
    # cache entry windowed around a different swing's frame).
    import hashlib
    return hashlib.md5(f'{os.path.normpath(clip_path)}::{contact_frame}'.encode()).hexdigest()


def _probe_fps(video_path):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return fps if fps > 0 else 30.0


def get_poses(clip_path, contact_frame, cache_dir=POSES_CACHE_DIR):
    """cache_dir overridable so extract_training_features_from_pro_verdicts.py
    can reuse this with its own pro_derived_poses/ cache (different clip
    source, keep the caches separate)."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f'{_cache_key(clip_path, contact_frame)}.json')
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)
    fps = _probe_fps(clip_path)
    start_frame = max(0, int(contact_frame - WINDOW_PRE_SEC * fps))
    end_frame = int(contact_frame + WINDOW_POST_SEC * fps) + 1
    with contextlib.redirect_stdout(sys.stderr):
        extract_poses(clip_path, cache_path, sample_every=1, start_frame=start_frame, end_frame=end_frame)
    with open(cache_path) as f:
        return json.load(f)


def main():
    if not os.path.exists(LOG_PATH):
        print(json.dumps([]))
        return

    with open(LOG_PATH) as f:
        records = [json.loads(line) for line in f if line.strip()]

    # Dedupe by (clip_path, contact_frame), latest wins -- mirrors
    # clip_review_log.get_latest_verdicts()'s "latest logged line for this
    # identity" pattern. normpath() the clip_path first -- the same file has
    # been logged with both '\' and '/' separators (different code paths
    # wrote the log), which would otherwise dedupe as two distinct clips and
    # double the pose-extraction work for that video.
    latest = {}
    for r in records:
        clip_path, contact_frame = r.get('clip_path'), r.get('contact_frame')
        if not clip_path or contact_frame is None:
            continue
        if r.get('claude_pick') not in VALID_LABELS:
            continue
        clip_path = os.path.normpath(clip_path)
        latest[(clip_path, contact_frame)] = r

    rows, skipped = [], []
    for (clip_path, contact_frame), r in latest.items():
        if not os.path.exists(clip_path):
            skipped.append({'clip_path': clip_path, 'reason': 'clip no longer on disk'})
            continue
        try:
            pose_data = get_poses(clip_path, contact_frame)
        except Exception as e:
            skipped.append({'clip_path': clip_path, 'reason': f'pose extraction failed: {e}'})
            continue
        fps = pose_data['fps']
        features = extract_for_clip(
            os.path.join(POSES_CACHE_DIR, f'{_cache_key(clip_path, contact_frame)}.json'), contact_frame, fps,
        )
        if features is None:
            skipped.append({'clip_path': clip_path, 'reason': 'no pose near contact frame'})
            continue
        rows.append({
            'clip_path': clip_path, 'contact_frame': contact_frame,
            'label': r['claude_pick'], 'features': features,
        })

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(rows, f, indent=2)

    print(f'{len(rows)} feature rows written to {OUTPUT_PATH}')
    by_label = {}
    for r in rows:
        by_label[r['label']] = by_label.get(r['label'], 0) + 1
    print('by label:', by_label)
    if skipped:
        print(f'{len(skipped)} entries skipped:')
        for s in skipped[:20]:
            print(' ', s)


if __name__ == '__main__':
    main()
