"""
Splits a pro-database clip that actually contains TWO swings into two
separate, independently-usable database entries, instead of Cut mode's
normal behavior of trimming away the extra footage and discarding it
(DevProClipReviewScreen.js's "Split into 2 shots", 2026-08-27).

Why this needs more than a video trim: entry['trajectory'] -- the field
compare_swing.py's DTW comparison actually runs against -- is a list of
pose-landmark snapshots built once around one peak_frame when the pro
database was originally built. clip_contact_time_sec (what cut_pro_clip.py/
correct_contact_time.py adjust) is a separate, purely cosmetic seek target;
it never touches trajectory. So a hidden second swing in a clip's tail has
NO trajectory of its own -- it was never detected as its own candidate by
the original pipeline (that's exactly why it got merged into this entry's
clip instead of being cut out separately). Splitting properly means
re-deriving a real trajectory for the second half from the underlying pose
data, not just cutting the video file.

How the split half's position in the source video is found: every entry's
swing_id encodes which build job (source compilation) it came from via a
clean offset scheme confirmed on disk (job 0 uses swing_id 1-999, job 1
uses 1001-1999, etc. -- see source_footage_lookup.py). An entry's
peak_time (source-relative) and clip_contact_time_sec (clip-relative) were
both derived from the same peak_frame/start_frame pair, so
start_frame_in_source = round(peak_time * fps) - round(clip_contact_time_sec * fps),
and any clip-relative time T maps to source_frame ~= start_frame_in_source +
round(T * fps). Within the marked window for the new half, this script
takes the frame of maximum wrist speed (compute_wrist_velocity()'s argmax,
not detect_swings.py's percentile-threshold find_swing_peaks() -- Jack has
already visually confirmed a real swing is in this window, so a plain local
maximum is the right amount of complexity) as that swing's contact frame,
then builds its trajectory the same way build_pro_database.py originally
built every other entry's.

New entry's swing_id is allocated in a reserved 900-999 sub-range of the
SAME 1000-wide job band the original entry's job already uses, so
swing_id // 1000 still resolves to the right job for source_footage_lookup.py
-- confirmed safe against real data (no job's real swing_ids get anywhere
near .900-.999 today).

The new entry inherits camera_angle/angle_confidence/confidence from the
original rather than re-inferring them -- a documented simplification, not
an oversight; angle inference is a slow, separate concern this feature
deliberately doesn't re-run.

Usage:
  echo '{"id": "forehand_0004", "start_sec": 0.0, "split_sec": 1.6, "end_sec": 3.1}' \
      | python split_pro_clip.py

Output (stdout): {"split": true, "original_id": ..., "new_id": ..., "new_swing_id": ...,
  "original_new_duration_sec": ..., "new_entry_duration_sec": ...}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '03_swing_detection'))
import clip_review_log  # noqa: E402
from paths import DATA_DIR  # noqa: E402
from clip_urls import to_url, PRO_CLIPS_DIR, PRO_CLIPS_CROPPED_DIR  # noqa: E402
from clip_trim import get_duration_sec, get_fps, trim_in_place, trim_to_file  # noqa: E402
from trajectory_extraction import build_pose_index, extract_swing_trajectory  # noqa: E402
from source_footage_lookup import poses_path_for  # noqa: E402
from detect_swings import compute_wrist_velocity  # noqa: E402

PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
MIN_CLIP_SEC = 0.2  # same floor cut_pro_clip.py already uses

SPLIT_BAND_START = 900  # within a job's 1000-wide swing_id band
SPLIT_BAND_END = 999    # inclusive; reserved for manually-split entries


def _next_split_swing_id(db, shot_type, original_swing_id):
    job_base = (original_swing_id // 1000) * 1000
    lo, hi = job_base + SPLIT_BAND_START, job_base + SPLIT_BAND_END
    used = {e['swing_id'] for e in db['entries']
            if e['shot_type'] == shot_type and lo <= e['swing_id'] <= hi}
    for candidate in range(lo, hi + 1):
        if candidate not in used:
            return candidate
    raise ValueError(f'No free split swing_id left in job band {job_base}-{job_base + 999} for {shot_type}')


def split_pro_clip(entry_id, start_sec, split_sec, end_sec, name=None):
    """
    Core logic, separate from main()'s stdin/CLI plumbing so it's directly
    unit-testable (see test_split_pro_clip_pytest.py). Validates fully
    before touching any file -- a failure at any step leaves
    pro_database.json and every clip file untouched. Raises ValueError with
    a user-facing message on any rejected input.
    """
    start_sec = max(0.0, float(start_sec))
    split_sec = float(split_sec)
    end_sec = float(end_sec)
    if not (start_sec < split_sec < end_sec):
        raise ValueError(f'Points must be in order: start ({start_sec}) < split ({split_sec}) < end ({end_sec})')

    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    entry = next((e for e in db['entries'] if e['id'] == entry_id), None)
    if entry is None:
        raise ValueError(f'No pro database entry with id {entry_id}')

    main_path = os.path.join(PRO_CLIPS_DIR, entry['clip_path'])
    if not os.path.exists(main_path):
        raise ValueError(f'Clip file not found: {main_path}')

    duration = get_duration_sec(main_path)
    end_sec = min(duration, end_sec)
    if not (start_sec < split_sec < end_sec):
        raise ValueError(f'Split point {split_sec}s must fall strictly between start and the (possibly clamped) end {end_sec}s')

    half_a = (start_sec, split_sec)
    half_b = (split_sec, end_sec)
    if half_a[1] - half_a[0] < MIN_CLIP_SEC or half_b[1] - half_b[0] < MIN_CLIP_SEC:
        raise ValueError(
            f'Both halves must be at least {MIN_CLIP_SEC}s '
            f'(got {half_a[1] - half_a[0]:.2f}s and {half_b[1] - half_b[0]:.2f}s)'
        )

    old_contact = entry.get('clip_contact_time_sec')
    if old_contact is None:
        raise ValueError(f'{entry_id} has no clip_contact_time_sec -- cannot determine which half is the known swing')
    if half_a[0] <= old_contact <= half_a[1]:
        original_half, new_half = half_a, half_b
    elif half_b[0] <= old_contact <= half_b[1]:
        original_half, new_half = half_b, half_a
    else:
        raise ValueError(f'Existing contact time {old_contact}s falls outside [{start_sec}, {end_sec}]s')

    # Locate the new half's window in the source video's pose data.
    poses_path = poses_path_for(entry['shot_type'], entry['swing_id'])
    if not poses_path or not os.path.exists(poses_path):
        raise ValueError(f'No source pose data found for {entry_id} -- cannot locate the second swing')
    with open(poses_path) as f:
        pose_data = json.load(f)
    fps = pose_data['fps']

    start_frame_in_source = round(entry['peak_time'] * fps) - round(old_contact * fps)
    new_lo_frame = start_frame_in_source + round(new_half[0] * fps)
    new_hi_frame = start_frame_in_source + round(new_half[1] * fps)

    frames_in_window = sorted(
        (f for f in pose_data['frames'] if new_lo_frame <= f['frame'] <= new_hi_frame),
        key=lambda f: f['frame'],
    )
    if not frames_in_window:
        raise ValueError('No pose data found in the marked window -- cannot locate the second swing')

    velocities = compute_wrist_velocity(frames_in_window)
    if not velocities or max(velocities) <= 0:
        raise ValueError('Could not detect any wrist motion in the marked window -- try a wider split window')
    new_peak_frame = frames_in_window[velocities.index(max(velocities))]['frame']

    pose_index = build_pose_index(pose_data['frames'])
    new_trajectory = extract_swing_trajectory({'peak_frame': new_peak_frame}, pose_index, fps)
    if new_trajectory is None:
        raise ValueError(
            f'Could not build a trajectory for the second swing '
            f'(too few usable pose frames around frame {new_peak_frame}) -- try a wider split window'
        )

    new_swing_id = _next_split_swing_id(db, entry['shot_type'], entry['swing_id'])
    new_half_start_frame_in_source = start_frame_in_source + round(new_half[0] * fps)
    new_clip_contact_time_sec = round((new_peak_frame - new_half_start_frame_in_source) / fps, 3)
    new_peak_time = round(new_peak_frame / fps, 3)
    new_basename = f"{entry['shot_type']}_swing_{new_swing_id:04d}_conf{int(entry['confidence'] * 100)}.mp4"
    new_id = f"{entry['shot_type']}_{new_swing_id:04d}"

    # Everything above is pure validation/computation -- only now touch files.
    new_main_path = os.path.join(PRO_CLIPS_DIR, entry['shot_type'], new_basename)
    trim_to_file(main_path, new_main_path, new_half[0], new_half[1])
    trim_in_place(main_path, original_half[0], original_half[1])

    cropped_path = os.path.join(PRO_CLIPS_CROPPED_DIR, entry['shot_type'], os.path.basename(entry['clip_path']))
    if os.path.exists(cropped_path):
        new_cropped_path = os.path.join(PRO_CLIPS_CROPPED_DIR, entry['shot_type'], new_basename)
        trim_to_file(cropped_path, new_cropped_path, new_half[0], new_half[1])
        trim_in_place(cropped_path, original_half[0], original_half[1])

    entry['clip_contact_time_sec'] = round(max(0.0, old_contact - original_half[0]), 3)

    db['entries'].append({
        'id': new_id,
        'shot_type': entry['shot_type'],
        'swing_id': new_swing_id,
        'confidence': entry['confidence'],
        'peak_time': new_peak_time,
        'clip_contact_time_sec': new_clip_contact_time_sec,
        'clip_path': f"{entry['shot_type']}/{new_basename}",
        'camera_angle': entry.get('camera_angle'),
        'angle_confidence': entry.get('angle_confidence'),
        'trajectory': new_trajectory,
    })
    if 'shots' in db and entry['shot_type'] in db['shots']:
        db['shots'][entry['shot_type']] = db['shots'][entry['shot_type']] + 1
    db['total'] = len(db['entries'])

    with open(PRO_DB_PATH, 'w') as f:
        json.dump(db, f)

    clip_review_log.log_verdict(
        entry_id, 'split',
        note=(
            f'split into {entry_id} [{original_half[0]:.2f},{original_half[1]:.2f}]s '
            f'and {new_id} [{new_half[0]:.2f},{new_half[1]:.2f}]s (auto contact frame {new_peak_frame})'
        ),
        name=name,
    )

    return {
        'original_id': entry_id,
        'new_id': new_id,
        'new_swing_id': new_swing_id,
        'original_new_duration_sec': round(original_half[1] - original_half[0], 3),
        'new_entry_duration_sec': round(new_half[1] - new_half[0], 3),
        # The re-trimmed original's shifted contact time (already written to
        # entry above), plus a candidate-shaped payload for the new second half
        # -- DevProClipReviewScreen.js drops both straight into its in-memory
        # review queue so the split halves get reviewed without a refetch.
        'original_new_contact_time_sec': entry['clip_contact_time_sec'],
        'new_entry': {
            'id': new_id,
            'shot_type': entry['shot_type'],
            'clip_url': to_url('/pro-clips', PRO_CLIPS_DIR, new_main_path),
            'fps': get_fps(new_main_path),
            'clip_contact_time_sec': new_clip_contact_time_sec,
            'camera_angle': entry.get('camera_angle'),
            'confidence': entry['confidence'],
        },
    }


def main():
    payload = json.loads(sys.stdin.read())
    try:
        result = split_pro_clip(
            payload['id'], payload['start_sec'], payload['split_sec'], payload['end_sec'],
            payload.get('name'),
        )
    except ValueError as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

    print(json.dumps({'split': True, **result}))


if __name__ == '__main__':
    main()
