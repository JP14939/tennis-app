"""
Applies a manual trim to a pro-database clip from Jack's Pro Clip Review
tool (DevProClipReviewScreen.js "Cut" mode) -- for clips where extra footage
at the start/end (e.g. spans into a different swing/player) is fixable by
trimming rather than excluding the whole clip.

Re-encodes the main clip (04_clips/) and its cropped counterpart
(04_clips_cropped/), when one exists, to real H.264 with the new bounds
(same reencode-in-place pattern as video_io.reencode_to_h264, just with a
trim added), and shifts pro_database.json's clip_contact_time_sec by
-start_sec so it still points at the right instant in the trimmed clip.
The trajectory data itself (already-extracted pose landmarks, keyed by time
relative to contact, not clip-file time) is untouched -- DTW comparisons run
against that, not the raw video, so a trim never affects match quality, only
what plays back.

Usage:
  echo '{"id": "forehand_0004", "start_sec": 0.5, "end_sec": 2.1}' \
      | python cut_pro_clip.py

Output (stdout): {"cut": true, "new_duration_sec": ..., "new_contact_time_sec": ...}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
import clip_review_log  # noqa: E402
from paths import DATA_DIR  # noqa: E402
from clip_urls import PRO_CLIPS_DIR, PRO_CLIPS_CROPPED_DIR  # noqa: E402
from clip_trim import get_duration_sec, trim_in_place  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')

MIN_CLIP_SEC = 0.2  # guard against a degenerate/empty cut


def main():
    payload = json.loads(sys.stdin.read())
    entry_id = payload['id']
    start_sec = max(0.0, float(payload['start_sec']))
    end_sec = float(payload['end_sec'])
    name = payload.get('name')

    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    entry = next((e for e in db['entries'] if e['id'] == entry_id), None)
    if entry is None:
        print(json.dumps({'error': f'No pro database entry with id {entry_id}'}))
        sys.exit(1)

    main_path = os.path.join(PRO_CLIPS_DIR, entry['clip_path'])
    if not os.path.exists(main_path):
        print(json.dumps({'error': f'Clip file not found: {main_path}'}))
        sys.exit(1)

    duration = get_duration_sec(main_path)
    end_sec = min(duration, end_sec)
    if end_sec - start_sec < MIN_CLIP_SEC:
        print(json.dumps({'error': f'Trimmed clip would be under {MIN_CLIP_SEC}s (requested [{start_sec:.2f}, {end_sec:.2f}]s of {duration:.2f}s original)'}))
        sys.exit(1)

    trim_in_place(main_path, start_sec, end_sec)

    cropped_path = os.path.join(PRO_CLIPS_CROPPED_DIR, entry['shot_type'], os.path.basename(entry['clip_path']))
    if os.path.exists(cropped_path):
        trim_in_place(cropped_path, start_sec, end_sec)

    old_contact = entry.get('clip_contact_time_sec')
    new_contact = round(max(0.0, old_contact - start_sec), 3) if old_contact is not None else None
    if new_contact is not None:
        entry['clip_contact_time_sec'] = new_contact

    with open(PRO_DB_PATH, 'w') as f:
        json.dump(db, f)

    clip_review_log.log_verdict(
        entry_id, 'cut',
        note=f'trimmed to [{start_sec:.2f}, {end_sec:.2f}]s of {duration:.2f}s original',
        name=name,
    )

    print(json.dumps({
        'cut': True,
        'new_duration_sec': round(end_sec - start_sec, 3),
        'new_contact_time_sec': new_contact,
    }))


if __name__ == '__main__':
    main()
