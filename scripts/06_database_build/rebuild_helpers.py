"""
Re-derive a pro-database entry's `trajectory` (and its skeleton `overlay`)
around a corrected contact time, straight from on-disk pose data -- NO video
decode, NO MediaPipe.

Why this exists: correct_contact_time.py / cut_pro_clip.py only ever rewrote
the scalar `clip_contact_time_sec` (a clip-playback seek target). The field
compare_swing.py's DTW distance is actually computed against --
`entry['trajectory']` -- stayed anchored to the ORIGINAL automated
wrist-velocity peak_frame, so 137 manual contact corrections were only
half-applied. This module is the missing half: shared by
rebuild_pro_database_from_verdicts.py (the one-time backlog pass) and by
correct_contact_time.py itself (so every future correction stays in sync).

Frame math: an entry's clip file frame 0 sits at `start_frame` in the source
compilation. The validated-swings JSON
(data/03_swing_detection/*_swings_validated.json) carries that start_frame
directly per swing_id -- that's the batch path. The single-entry path (Dev
route) instead re-derives it from `peak_time` and the pre-correction
contact time, which stays correct even if the clip was previously trimmed by
cut_pro_clip.py (a trim shifts clip_contact_time_sec by exactly the trimmed
amount, preserving `round(peak_time*fps) - round(clip_contact_time_sec*fps)`
as the clip's frame-0 position). Then
`new_peak_frame = clip_start_frame + round(corrected_contact_time_sec * fps)`.
"""
import functools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from trajectory_extraction import build_pose_index, extract_swing_trajectory, build_swing_overlay  # noqa: E402
from source_footage_lookup import (  # noqa: E402
    POSES_BY_SHOT_TYPE, SWINGS_VALIDATED_BY_SHOT_TYPE, poses_path_for,
    swings_validated_path_for,
)


def _start_frame_from_swings_file(shot_type, swing_id):
    """Read one swing's start_frame straight from its validated-swings JSON
    (small file). Fallback for the single-entry path when the pre-correction
    contact time isn't known."""
    path = swings_validated_path_for(shot_type, swing_id)
    if not path or not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    for sw in data['swings']:
        if sw['swing_id'] == swing_id:
            return sw['start_frame']
    return None


@functools.lru_cache(maxsize=2)
def _load_pose_index(poses_path):
    """Cached: a full pose file is tens of MB and its index a few hundred MB
    resident. maxsize=2 keeps peak memory bounded -- the batch rebuild
    processes entries in DB (= job) order, so in practice one job's pose
    index is live at a time."""
    with open(poses_path) as f:
        pose_data = json.load(f)
    return pose_data['fps'], build_pose_index(pose_data['frames'])


def build_swing_lookup():
    """(shot_type, swing_id) -> {'poses_path', 'fps', 'orig_peak_frame', 'start_frame'}.

    Reads only the small validated-swings JSONs (fps + start_frame +
    peak_frame per swing) -- pose files are loaded lazily by
    reextract_for_entry via _load_pose_index. Keyed on the swing's ORIGINAL
    shot type (swing_id // 1000 job bucketing depends on it); callers pass
    original_shot_type for entries that were later relabelled.
    """
    lookup = {}
    for shot_type, swings_paths in SWINGS_VALIDATED_BY_SHOT_TYPE.items():
        poses_paths = POSES_BY_SHOT_TYPE[shot_type]
        for job_index, swings_path in enumerate(swings_paths):
            if not os.path.exists(swings_path):
                continue
            with open(swings_path) as f:
                data = json.load(f)
            fps = data['fps']
            poses_path = poses_paths[job_index]
            for sw in data['swings']:
                lookup[(shot_type, sw['swing_id'])] = {
                    'poses_path': poses_path,
                    'fps': fps,
                    'orig_peak_frame': sw['peak_frame'],
                    'start_frame': sw['start_frame'],
                }
    return lookup


def reextract_for_entry(entry, lookup=None, single=False,
                        prior_contact_time_sec=None, original_shot_type=None):
    """Recompute entry['trajectory'] + its overlay around the CURRENT
    entry['clip_contact_time_sec']. Never mutates `entry`. Never touches
    video / MediaPipe.

    single=True: load just this entry's one pose file (Dev-route fast path);
      requires prior_contact_time_sec (the entry's contact time BEFORE this
      correction) to locate the clip's frame 0.
    single=False: use `lookup` from build_swing_lookup() (batch path).

    Returns {status, trajectory, overlay, new_peak_frame, new_peak_time}:
      status 'ok'            -- trajectory/overlay are fresh lists
      status 'missing_lookup'-- no pose/swings data for this (shot_type, swing_id)
                                (split entries, unresolved relabels); leave entry as-is
      status 'too_few_points'-- pose window too sparse to build a trajectory; leave as-is
    """
    shot_type = original_shot_type or entry['shot_type']
    swing_id = entry['swing_id']
    contact = entry['clip_contact_time_sec']

    # Practice-footage entries (ingest_practice_footage.py) carry their own
    # source pose file + clip frame-0 offset, because their swing_ids don't fit
    # source_footage_lookup's per-shot-type // 1000 scheme. Use those directly.
    if entry.get('poses_path') and entry.get('clip_start_frame') is not None:
        poses_abs = entry['poses_path']
        if not os.path.isabs(poses_abs):
            from paths import DATA_DIR  # noqa: PLC0415
            poses_abs = os.path.join(DATA_DIR, entry['poses_path'])
        if not os.path.exists(poses_abs):
            return {'status': 'missing_lookup', 'trajectory': None, 'overlay': None,
                    'new_peak_frame': None, 'new_peak_time': None}
        fps, pose_index = _load_pose_index(poses_abs)
        clip_start_frame = entry['clip_start_frame']
        new_peak_frame = clip_start_frame + round(contact * fps)
        trajectory = extract_swing_trajectory({'peak_frame': new_peak_frame}, pose_index, fps)
        if trajectory is None:
            return {'status': 'too_few_points', 'trajectory': None, 'overlay': None,
                    'new_peak_frame': new_peak_frame, 'new_peak_time': round(new_peak_frame / fps, 3)}
        overlay = build_swing_overlay(pose_index, fps, new_peak_frame, clip_start_frame)
        return {'status': 'ok', 'trajectory': trajectory, 'overlay': overlay,
                'new_peak_frame': new_peak_frame, 'new_peak_time': round(new_peak_frame / fps, 3)}

    if single:
        poses_path = poses_path_for(shot_type, swing_id)
        if not poses_path or not os.path.exists(poses_path):
            return {'status': 'missing_lookup', 'trajectory': None, 'overlay': None,
                    'new_peak_frame': None, 'new_peak_time': None}
        fps, pose_index = _load_pose_index(poses_path)
        if prior_contact_time_sec is not None:
            clip_start_frame = round(entry['peak_time'] * fps) - round(prior_contact_time_sec * fps)
        else:
            clip_start_frame = _start_frame_from_swings_file(shot_type, swing_id)
            if clip_start_frame is None:
                return {'status': 'missing_lookup', 'trajectory': None, 'overlay': None,
                        'new_peak_frame': None, 'new_peak_time': None}
    else:
        found = (lookup if lookup is not None else build_swing_lookup()).get((shot_type, swing_id))
        if not found:
            return {'status': 'missing_lookup', 'trajectory': None, 'overlay': None,
                    'new_peak_frame': None, 'new_peak_time': None}
        fps, pose_index = _load_pose_index(found['poses_path'])
        clip_start_frame = found['start_frame']

    new_peak_frame = clip_start_frame + round(contact * fps)

    trajectory = extract_swing_trajectory({'peak_frame': new_peak_frame}, pose_index, fps)
    if trajectory is None:
        return {'status': 'too_few_points', 'trajectory': None, 'overlay': None,
                'new_peak_frame': new_peak_frame, 'new_peak_time': round(new_peak_frame / fps, 3)}

    overlay = build_swing_overlay(pose_index, fps, new_peak_frame, clip_start_frame)
    return {'status': 'ok', 'trajectory': trajectory, 'overlay': overlay,
            'new_peak_frame': new_peak_frame, 'new_peak_time': round(new_peak_frame / fps, 3)}
