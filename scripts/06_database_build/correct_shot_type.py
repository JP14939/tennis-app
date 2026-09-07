"""
Corrects a mislabeled shot type on a pro-database entry from Jack's Pro Clip
Review tool (DevProClipReviewScreen.js "Wrong shot type?"). entry['shot_type']
is authoritative for DTW matching (compare_swing.py filters its whole
candidate pool by it), so a mislabeled entry isn't just cosmetically wrong,
it's being compared against the wrong shot type for every real user.

Moves the actual clip file(s) into the new shot type's folder rather than
just relabeling JSON -- confirmed directly that entry['shot_type'] always
matches clip_path's directory prefix for every existing entry, and two live
code paths (cut_pro_clip.py, clip_urls.py's attach_clip_urls()) reconstruct
the cropped-clip path by joining entry['shot_type'] with the clip's
basename rather than parsing clip_path -- leaving the file in its old
folder would silently break the cropped-clip lookup for this entry.

entry['id']/entry['swing_id'] are deliberately left untouched -- they're
opaque keys other logs/files (clip_review_log.jsonl, overlay_trajectories.json,
contact-frame training logs) reference by identity, not by shot type.

Known limitation, not solved here: a future full rebuild of
overlay_trajectories.json re-derives its lookup from the original offline
job recordings keyed by (original shot_type, swing_id) -- a corrected
entry's overlay would go missing on such a rebuild, since this can't
retroactively change which job/shot-type bucket the raw footage was
recorded under. overlay_trajectories.json is precomputed and id-keyed, so
this only matters if that build script is rerun later, not today.

Usage:
  echo '{"id": "forehand_0004", "new_shot_type": "backhand"}' \
      | python correct_shot_type.py

Output (stdout): {"corrected": true, "old_shot_type": ..., "new_shot_type": ..., "clip_path": ...}
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
import clip_review_log  # noqa: E402
from paths import DATA_DIR  # noqa: E402
from clip_urls import PRO_CLIPS_DIR, PRO_CLIPS_CROPPED_DIR  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')

SHOT_TYPES = ('forehand', 'backhand', 'serve')


def correct_shot_type(entry_id, new_shot_type, name=None):
    """
    Core logic, separate from main()'s stdin/CLI plumbing so it's directly
    unit-testable (see test_correct_shot_type_pytest.py). Raises ValueError
    with a user-facing message on any rejected input; on success returns
    {old_shot_type, new_shot_type, clip_path} and has already moved the
    clip file(s), rewritten pro_database.json, and logged the verdict.
    """
    if new_shot_type not in SHOT_TYPES:
        raise ValueError(f'Unknown shot type {new_shot_type!r}, expected one of {SHOT_TYPES}')

    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    entry = next((e for e in db['entries'] if e['id'] == entry_id), None)
    if entry is None:
        raise ValueError(f'No pro database entry with id {entry_id}')

    old_shot_type = entry['shot_type']
    if new_shot_type == old_shot_type:
        raise ValueError(f'{entry_id} is already labeled {old_shot_type}')

    # Practice-footage entries (ingest_practice_footage.py) keep their clip in
    # the flat practice/ folder -- clip_path isn't <shot_type>/basename, so
    # there's nothing to move; just relabel.
    if str(entry.get('clip_path', '')).startswith('practice/'):
        entry['shot_type'] = new_shot_type
        with open(PRO_DB_PATH, 'w') as f:
            json.dump(db, f)
        clip_review_log.log_verdict(
            entry_id, 'shot_type_corrected', note=f'{old_shot_type} -> {new_shot_type}', name=name)
        return {'old_shot_type': old_shot_type, 'new_shot_type': new_shot_type,
                'clip_path': entry['clip_path']}

    basename = os.path.basename(entry['clip_path'])

    old_main_path = os.path.join(PRO_CLIPS_DIR, entry['clip_path'])
    new_main_dir = os.path.join(PRO_CLIPS_DIR, new_shot_type)
    new_main_path = os.path.join(new_main_dir, basename)
    if not os.path.exists(old_main_path):
        raise ValueError(f'Clip file not found: {old_main_path}')
    os.makedirs(new_main_dir, exist_ok=True)
    os.rename(old_main_path, new_main_path)

    old_cropped_path = os.path.join(PRO_CLIPS_CROPPED_DIR, old_shot_type, basename)
    if os.path.exists(old_cropped_path):
        new_cropped_dir = os.path.join(PRO_CLIPS_CROPPED_DIR, new_shot_type)
        os.makedirs(new_cropped_dir, exist_ok=True)
        os.rename(old_cropped_path, os.path.join(new_cropped_dir, basename))

    entry['shot_type'] = new_shot_type
    entry['clip_path'] = f'{new_shot_type}/{basename}'

    with open(PRO_DB_PATH, 'w') as f:
        json.dump(db, f)

    clip_review_log.log_verdict(
        entry_id, 'shot_type_corrected',
        note=f'{old_shot_type} -> {new_shot_type}',
        name=name,
    )

    return {'old_shot_type': old_shot_type, 'new_shot_type': new_shot_type, 'clip_path': entry['clip_path']}


def main():
    payload = json.loads(sys.stdin.read())
    try:
        result = correct_shot_type(payload['id'], payload['new_shot_type'], payload.get('name'))
    except ValueError as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

    print(json.dumps({'corrected': True, **result}))


if __name__ == '__main__':
    main()
