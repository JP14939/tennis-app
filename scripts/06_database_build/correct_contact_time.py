"""
Corrects a wrong clip_contact_time_sec on a pro-database entry from Jack's
Pro Clip Review tool (DevProClipReviewScreen.js "Fix contact time").

Two things change here:
  1. clip_contact_time_sec -- the clip-playback seek target (where the
     results screen scrubs the pro clip to). Cosmetic on its own.
  2. entry['trajectory'] -- the field compare_swing.py's DTW distance is
     ACTUALLY computed against, plus its raw skeleton `overlay`. Both are
     re-extracted here around the corrected contact frame, from on-disk pose
     data (no video decode / MediaPipe -- see rebuild_helpers.py). Before
     this was added, a correction only moved the seek target and left the
     trajectory anchored to the original automated wrist-velocity peak, so
     the two silently drifted apart. peak_time is updated to match.

The original clip_contact_time_sec was produced entirely by an automated
wrist-velocity peak detector (see backfill_clip_contact_time.py) -- never
manually verified at scale until this tool existed.

Unlike correct_shot_type.py, this never needs to move a clip file.

Usage:
  echo '{"id": "forehand_0004", "new_contact_time_sec": 1.24}' \
      | python correct_contact_time.py

Output (stdout): {"corrected": true, "old_contact_time_sec": ..., "new_contact_time_sec": ...,
  "trajectory_updated": true|false, "warning": ...}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
import clip_review_log  # noqa: E402
from paths import DATA_DIR  # noqa: E402
from rebuild_helpers import reextract_for_entry  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
OVERLAY_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'overlay_trajectories.json')

MIN_CONTACT_TIME_SEC = 0.0
# Generous ceiling, not derived from each clip's actual duration (this
# script doesn't probe the video file) -- just rejects obviously-bad input
# like a stray minutes-as-seconds typo; the review UI only ever sends a
# value it already scrubbed to within the loaded clip.
MAX_CONTACT_TIME_SEC = 60.0


def correct_contact_time(entry_id, new_contact_time_sec, name=None):
    """
    Core logic, separate from main()'s stdin/CLI plumbing so it's directly
    unit-testable (see test_correct_contact_time_pytest.py). Raises
    ValueError with a user-facing message on any rejected input; on success
    returns {old_contact_time_sec, new_contact_time_sec, trajectory_updated,
    warning?} and has already rewritten pro_database.json (+ the overlay
    file) and logged the verdict.
    """
    try:
        new_contact_time_sec = float(new_contact_time_sec)
    except (TypeError, ValueError):
        raise ValueError(f'Contact time must be a number, got {new_contact_time_sec!r}')
    if not (MIN_CONTACT_TIME_SEC <= new_contact_time_sec <= MAX_CONTACT_TIME_SEC):
        raise ValueError(
            f'Contact time {new_contact_time_sec}s out of expected range '
            f'({MIN_CONTACT_TIME_SEC}-{MAX_CONTACT_TIME_SEC}s)'
        )

    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    entry = next((e for e in db['entries'] if e['id'] == entry_id), None)
    if entry is None:
        raise ValueError(f'No pro database entry with id {entry_id}')

    old_contact_time_sec = entry.get('clip_contact_time_sec')
    if old_contact_time_sec is not None and abs(old_contact_time_sec - new_contact_time_sec) < 1e-6:
        raise ValueError(f'{entry_id} already has contact time {old_contact_time_sec}s')

    entry['clip_contact_time_sec'] = new_contact_time_sec

    # Re-anchor the DTW trajectory + skeleton overlay to the corrected
    # contact frame. On any non-'ok' status (split entry, missing source
    # pose data, too-sparse pose window) we still persist the scalar +
    # verdict -- the correction is not lost, it just couldn't propagate to
    # the trajectory, and the Dev tool surfaces the warning.
    res = reextract_for_entry(
        entry, single=True,
        prior_contact_time_sec=old_contact_time_sec,
        original_shot_type=clip_review_log.original_shot_type_for(entry_id),
    )
    trajectory_updated = res['status'] == 'ok'
    warning = None if trajectory_updated else res['status']
    if trajectory_updated:
        entry['trajectory'] = res['trajectory']
        entry['peak_time'] = res['new_peak_time']

    with open(PRO_DB_PATH, 'w') as f:
        json.dump(db, f)

    if trajectory_updated and os.path.exists(OVERLAY_DB_PATH):
        try:
            with open(OVERLAY_DB_PATH) as f:
                overlays = json.load(f)
        except json.JSONDecodeError:
            overlays = None  # corrupt file -- don't clobber it, leave the overlay stale
        if overlays is not None:
            overlays[entry_id] = res['overlay']
            with open(OVERLAY_DB_PATH, 'w') as f:
                json.dump(overlays, f)

    clip_review_log.log_verdict(
        entry_id, 'contact_time_corrected',
        note=f'{old_contact_time_sec} -> {new_contact_time_sec}',
        name=name,
    )

    result = {
        'old_contact_time_sec': old_contact_time_sec,
        'new_contact_time_sec': new_contact_time_sec,
        'trajectory_updated': trajectory_updated,
    }
    if warning:
        result['warning'] = warning
    return result


def main():
    payload = json.loads(sys.stdin.read())
    try:
        result = correct_contact_time(payload['id'], payload['new_contact_time_sec'], payload.get('name'))
    except ValueError as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

    print(json.dumps({'corrected': True, **result}))


if __name__ == '__main__':
    main()
