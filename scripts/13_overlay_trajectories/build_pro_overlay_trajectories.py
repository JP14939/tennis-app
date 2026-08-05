"""
Precompute raw (non-DTW-normalized) per-frame skeleton landmarks for every
pro database entry, for the skeleton-overlay feature.

pro_database.json's `trajectory` field is shoulder-width-centered/rescaled
for DTW comparison purposes -- it deliberately throws away where a landmark
actually sits in the video frame. This script re-derives, per swing, the
RAW image-normalized (0-1) x/y coordinates for the same 9 upper-body
KEY_LANDMARKS and the same PRE_SEC..POST_SEC contact window, so a frontend
overlay can draw a skeleton that lines up with the clip's actual pixels.

Resumable: skips entries already present in the output file. Pure JSON
slicing over already-extracted pose data (data/02_pose_extraction/) -- no
video decode, no model inference, so this runs in well under a minute for
all ~631 entries, unlike the crop-to-subject precompute job.

Usage: python build_pro_overlay_trajectories.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '06_database_build'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from build_pro_database import JOBS, KEY_LANDMARKS, PRE_SEC, POST_SEC, MIN_CONFIDENCE  # noqa: E402
from paths import DATA_DIR  # noqa: E402

DB_PATH  = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
OUT_PATH = os.path.join(DATA_DIR, '06_pro_database', 'overlay_trajectories.json')


def build_pose_index(frames):
    index = {}
    for f in frames:
        if f['landmarks']:
            index[f['frame']] = {lm['name']: lm for lm in f['landmarks']}
    return index


def build_swing_overlay(pose_index, fps, peak_frame, clip_start_frame):
    """Same PRE_SEC/POST_SEC contact window as extract_swing_trajectory(),
    but keeps raw image-space x/y instead of normalising. 't' is seconds
    relative to the CLIP FILE's own frame 0 (clip_start_frame), not the
    contact frame -- the clip video that actually gets played back was cut
    starting at clip_start_frame (detect_swings.py's PRE_SWING_SEC/
    POST_SWING_SEC window, a *different* and wider window than PRE_SEC/
    POST_SEC below), so this is the timestamp convention that lines up with
    that video's own playhead position, not pro_database.json's
    contact-relative `trajectory[].t`."""
    lo = peak_frame - int(PRE_SEC * fps)
    hi = peak_frame + int(POST_SEC * fps)
    trajectory = []
    for f in sorted(fr for fr in pose_index if lo <= fr <= hi):
        lm_dict = pose_index[f]
        landmarks = {}
        for name in KEY_LANDMARKS:
            lm = lm_dict.get(name)
            landmarks[name] = {'x': lm['x'], 'y': lm['y']} if lm and lm.get('visibility', 0) >= 0.3 else None
        trajectory.append({'t': round((f - clip_start_frame) / fps, 4), 'landmarks': landmarks})
    return trajectory


def main():
    with open(DB_PATH, encoding='utf-8') as f:
        db = json.load(f)

    overlays = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, encoding='utf-8') as f:
            overlays = json.load(f)
        print(f'Resuming -- {len(overlays)} entries already done')

    # swing_id alone doesn't say which compilation/pose file a swing came
    # from (several JOBS share a shot_type) -- index every JOB's swings by
    # (shot_type, swing_id) up front, same lookup build_pro_database.py
    # implicitly does by processing one job at a time.
    print('Indexing source pose/swing files across all JOBS...')
    lookup = {}  # (shot_type, swing_id) -> (pose_index, fps, peak_frame, start_frame)
    for job in JOBS:
        with open(job['poses'], encoding='utf-8') as f:
            pose_data = json.load(f)
        fps = pose_data['fps']
        pose_index = build_pose_index(pose_data['frames'])
        with open(job['swings_validated'], encoding='utf-8') as f:
            swing_data = json.load(f)
        for sw in swing_data['swings']:
            if sw.get('confidence', 0) < MIN_CONFIDENCE:
                continue
            lookup[(job['shot_type'], sw['swing_id'])] = (pose_index, fps, sw['peak_frame'], sw['start_frame'])

    entries = db['entries']
    done = empty = missing = 0
    for entry in entries:
        if entry['id'] in overlays:
            continue
        found = lookup.get((entry['shot_type'], entry['swing_id']))
        if not found:
            missing += 1
            continue
        pose_index, fps, peak_frame, start_frame = found
        trajectory = build_swing_overlay(pose_index, fps, peak_frame, start_frame)
        if not trajectory:
            empty += 1
            continue
        overlays[entry['id']] = trajectory
        done += 1
        if done % 100 == 0:
            print(f'  {done} built so far...')

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(overlays, f)

    print(f'\nDone: {len(overlays)}/{len(entries)} entries have overlay trajectories')
    print(f'  ({done} newly built this run, {empty} empty window, {missing} swing_id not found in any JOB)')
    print(f'  Saved to {OUT_PATH}')


if __name__ == '__main__':
    main()
