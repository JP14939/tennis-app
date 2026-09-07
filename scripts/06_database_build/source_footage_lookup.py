"""
Maps a pro-database entry (shot_type + swing_id) back to the exact position
in the original, uncut source compilation video it came from -- used by
Jack's Pro Clip Review tool's "View in source footage" button (Sprint 0 of
the 2026-08-27 ML reliability plan) to double-check a flagged clip against
full surrounding context (previous/next shots, camera framing, whether the
automated cut actually grabbed the right moment) rather than just the
isolated ~3s cut clip.

Deliberately does NOT import build_pro_database.py -- it pulls in mediapipe
via infer_angle.py at module level, too heavy for this tool's near-instant
response budget (list_pro_clip_review_candidates.py has a 30s ceiling for
what's otherwise just reading two JSON files). Duplicates just the
shot_type -> [source videos, in job order] mapping instead; keep this in
sync if JOBS in build_pro_database.py ever changes.

swing_id ranges are deliberately offset per job by build_pro_database.py's
own JOBS list order -- confirmed against every swings_validated.json file on
disk: job 0 in a shot type's list uses swing_id 1-999, job 1 uses
1001-1999, job 2 uses 2001-2999, etc. swing_id // 1000 recovers which job
(source video) a given entry came from.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

SOURCE_VIDEOS_DIR = os.path.join(DATA_DIR, '01_source_videos')

# Mirrors build_pro_database.py's JOBS list, grouped and ordered the same way.
SOURCE_VIDEOS_BY_SHOT_TYPE = {
    'forehand': [
        os.path.join(SOURCE_VIDEOS_DIR, 'forehand', 'forehand_compilation_1.mp4'),
        os.path.join(SOURCE_VIDEOS_DIR, 'forehand', 'forehand_compilation_2.mp4'),
        os.path.join(SOURCE_VIDEOS_DIR, 'forehand', 'forehand_compilation_3.mp4'),
    ],
    'backhand': [
        os.path.join(SOURCE_VIDEOS_DIR, 'backhand', 'backhand_compilation_1.mp4'),
        os.path.join(SOURCE_VIDEOS_DIR, 'backhand', 'backhand_compilation_2.mp4'),
        os.path.join(SOURCE_VIDEOS_DIR, 'backhand', 'backhand_compilation_3.mp4'),
        os.path.join(SOURCE_VIDEOS_DIR, 'backhand', 'backhand_compilation_4.mp4'),
    ],
    'serve': [
        os.path.join(SOURCE_VIDEOS_DIR, 'serve', 'serve_compilation_1.mp4'),
        os.path.join(SOURCE_VIDEOS_DIR, 'serve', 'serve_compilation_2.mp4'),
    ],
}


def source_video_for(shot_type, swing_id):
    """
    Returns the absolute path to the source compilation video a given
    pro-database entry's swing came from, or None if the shot type isn't a
    known one (there are none today outside forehand/backhand/serve, but
    this degrades safely rather than raising).
    """
    jobs = SOURCE_VIDEOS_BY_SHOT_TYPE.get(shot_type)
    if not jobs:
        return None
    job_index = swing_id // 1000
    if job_index >= len(jobs):
        return None
    return jobs[job_index]


POSES_DIR = os.path.join(DATA_DIR, '02_pose_extraction')

# Same per-shot-type job order as SOURCE_VIDEOS_BY_SHOT_TYPE above -- each
# job's full-resolution pose data (data/02_pose_extraction/extract_poses.py's
# output for that job's source video), needed by split_pro_clip.py to
# re-derive a trajectory for a manually-split second swing.
POSES_BY_SHOT_TYPE = {
    'forehand': [
        os.path.join(POSES_DIR, 'forehand_poses.json'),
        os.path.join(POSES_DIR, 'forehand_poses_2.json'),
        os.path.join(POSES_DIR, 'forehand_poses_3.json'),
    ],
    'backhand': [
        os.path.join(POSES_DIR, 'backhand_poses.json'),
        os.path.join(POSES_DIR, 'backhand_poses_2.json'),
        os.path.join(POSES_DIR, 'backhand_poses_3.json'),
        os.path.join(POSES_DIR, 'backhand_poses_4.json'),
    ],
    'serve': [
        os.path.join(POSES_DIR, 'serve_poses.json'),
        os.path.join(POSES_DIR, 'serve_poses_2.json'),
    ],
}


def poses_path_for(shot_type, swing_id):
    """Same job-bucketing as source_video_for(), for the pose-extraction
    JSON file instead of the source video -- both are indexed by job in the
    same JOBS order."""
    jobs = POSES_BY_SHOT_TYPE.get(shot_type)
    if not jobs:
        return None
    job_index = swing_id // 1000
    if job_index >= len(jobs):
        return None
    return jobs[job_index]


SWINGS_VALIDATED_DIR = os.path.join(DATA_DIR, '03_swing_detection')

# Same per-shot-type job order again -- the validated-swings JSON carries the
# authoritative start_frame/peak_frame for each swing_id, which
# rebuild_helpers.build_swing_lookup() needs to re-anchor a trajectory after
# a manual contact-time correction. Filenames match JOBS in build_pro_database.py
# (first job has no numeric suffix, subsequent jobs are _2/_3/_4).
SWINGS_VALIDATED_BY_SHOT_TYPE = {
    'forehand': [
        os.path.join(SWINGS_VALIDATED_DIR, 'forehand_swings_validated.json'),
        os.path.join(SWINGS_VALIDATED_DIR, 'forehand_swings_2_validated.json'),
        os.path.join(SWINGS_VALIDATED_DIR, 'forehand_swings_3_validated.json'),
    ],
    'backhand': [
        os.path.join(SWINGS_VALIDATED_DIR, 'backhand_swings_validated.json'),
        os.path.join(SWINGS_VALIDATED_DIR, 'backhand_swings_2_validated.json'),
        os.path.join(SWINGS_VALIDATED_DIR, 'backhand_swings_3_validated.json'),
        os.path.join(SWINGS_VALIDATED_DIR, 'backhand_swings_4_validated.json'),
    ],
    'serve': [
        os.path.join(SWINGS_VALIDATED_DIR, 'serve_swings_validated.json'),
        os.path.join(SWINGS_VALIDATED_DIR, 'serve_swings_2_validated.json'),
    ],
}


def swings_validated_path_for(shot_type, swing_id):
    """Same job-bucketing as poses_path_for(), for the validated-swings JSON."""
    jobs = SWINGS_VALIDATED_BY_SHOT_TYPE.get(shot_type)
    if not jobs:
        return None
    job_index = swing_id // 1000
    if job_index >= len(jobs):
        return None
    return jobs[job_index]
