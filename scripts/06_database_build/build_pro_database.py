"""
Build the pro swing feature database.

For each validated swing we extract normalised pose features at 3 key moments:
  - backswing  (0.5s before contact)
  - contact    (peak wrist velocity frame)
  - follow-through (1.0s after contact)

Normalisation: translate so shoulder midpoint = (0,0), scale so shoulder width = 1.0.
This makes comparison body-size and camera-distance invariant.

Output: data/pro_database.json
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '05_angle_detection'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from infer_angle import infer_camera_angle, infer_angle_from_source, create_landmarker
from paths import DATA_DIR

PRO_CLIPS_DIR = os.path.join(DATA_DIR, '04_clips')


def relative_clip_path(clip_path):
    """
    Stored clip_path used to be the raw absolute path extract_clips.py wrote
    (e.g. C:\\Users\\jackp\\...\\04_clips\\forehand\\swing_0004.mp4) -- fine
    on the machine that built the database, but backend/src/utils/videoCrop.js's
    toUrl() does path.relative() against that absolute string on whatever OS
    is actually serving the file, which silently breaks the moment the built
    database is deployed to a different machine (confirmed live: Linux server
    couldn't resolve a Windows path, every pro-clip video 404'd as "Video
    unavailable"). Storing a path relative to 04_clips instead means every
    consumer (this script, compare_swing.py, clip_urls.py, videoCrop.js) can
    just join it onto their own DATA_DIR, with no OS-specific parsing at all.
    """
    if not clip_path:
        return clip_path
    return os.path.relpath(clip_path, PRO_CLIPS_DIR).replace('\\', '/')

# Pure pose-math (KEY_LANDMARKS, build_pose_index, get_shoulder_ref,
# normalise_landmarks, trajectory_scale, PRE_SEC, POST_SEC,
# MIN_TRAJECTORY_POINTS, extract_swing_trajectory) moved to
# trajectory_extraction.py 2026-08-27 so split_pro_clip.py can reuse it
# without this file's own infer_angle.py (mediapipe) import. Re-imported
# here rather than redefined -- every name below is re-exported from this
# module's own namespace exactly as before, so compare_swing.py,
# compare_videos.py, track_racket_in_clip.py,
# train_tip_selector_on_amateur_footage.py,
# build_pro_overlay_trajectories.py, and test_build_pro_database_pytest.py
# (all of which do `from build_pro_database import <one of these names>`)
# keep working completely unchanged.
from trajectory_extraction import (  # noqa: E402
    KEY_LANDMARKS, MIN_LANDMARK_VISIBILITY, PRE_SEC, POST_SEC, MIN_TRAJECTORY_POINTS,
    build_pose_index, get_shoulder_ref, normalise_landmarks, trajectory_scale,
    extract_swing_trajectory,
)

JOBS = [
    {
        'shot_type':        'forehand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\forehand_poses.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\forehand\forehand_compilation_1.mp4',
    },
    {
        'shot_type':        'backhand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\backhand_poses.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\backhand\backhand_compilation_1.mp4',
    },
    {
        'shot_type':        'serve',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\serve_poses.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\serve_swings_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\serve\serve_compilation_1.mp4',
    },
    # Additional compilations added 2026-08-02 for footage diversity
    {
        'shot_type':        'forehand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\forehand_poses_2.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings_2_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\forehand\forehand_compilation_2.mp4',
    },
    {
        'shot_type':        'forehand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\forehand_poses_3.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings_3_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\forehand\forehand_compilation_3.mp4',
    },
    {
        'shot_type':        'backhand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\backhand_poses_2.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings_2_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\backhand\backhand_compilation_2.mp4',
    },
    {
        'shot_type':        'backhand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\backhand_poses_3.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings_3_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\backhand\backhand_compilation_3.mp4',
    },
    {
        'shot_type':        'backhand',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\backhand_poses_4.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings_4_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\backhand\backhand_compilation_4.mp4',
    },
    {
        'shot_type':        'serve',
        'poses':            r'C:\Users\jackp\tennis_app\data\02_pose_extraction\serve_poses_2.json',
        'swings_validated': r'C:\Users\jackp\tennis_app\data\03_swing_detection\serve_swings_2_validated.json',
        'source_video':     r'C:\Users\jackp\tennis_app\data\01_source_videos\serve\serve_compilation_2.mp4',
    },
]

MIN_CONFIDENCE = 0.5


# ── Main ──────────────────────────────────────────────────────────────────────

def build_database(out_path=r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'):
    all_entries = []

    print('Creating pose landmarker for angle inference...')
    angle_landmarker = create_landmarker()

    for job in JOBS:
        shot_type = job['shot_type']
        print(f'\n{shot_type.upper()}')

        with open(job['poses']) as f:
            pose_data = json.load(f)
        with open(job['swings_validated']) as f:
            swing_data = json.load(f)

        fps = pose_data['fps']
        pose_index = build_pose_index(pose_data['frames'])
        swings = [s for s in swing_data['swings'] if s.get('confidence', 0) >= MIN_CONFIDENCE]
        print(f'  {len(swings)} validated swings')

        source_video = job.get('source_video')
        ok = skipped = angle_ok = angle_fail = 0
        for sw in swings:
            trajectory = extract_swing_trajectory(sw, pose_index, fps)
            if trajectory is None:
                skipped += 1
                continue

            # Infer camera angle from the extracted clip
            camera_angle = None
            angle_confidence = None
            clip_path = sw.get('clip_path')
            if clip_path and os.path.exists(clip_path):
                try:
                    ang, conf, _ = infer_camera_angle(clip_path, landmarker=angle_landmarker)
                    if ang is not None:
                        camera_angle = ang
                        angle_confidence = round(conf, 3)
                        angle_ok += 1
                    elif source_video and os.path.exists(source_video):
                        # Clip-based detection failed — try wider window in source video
                        ang, conf, _ = infer_angle_from_source(
                            source_video, sw['peak_time_sec'], landmarker=angle_landmarker
                        )
                        if ang is not None:
                            camera_angle = ang
                            angle_confidence = round(conf, 3)
                            angle_ok += 1
                        else:
                            angle_fail += 1
                    else:
                        angle_fail += 1
                except Exception:
                    angle_fail += 1
            else:
                angle_fail += 1

            entry = {
                'id':               f"{shot_type}_{sw['swing_id']:04d}",
                'shot_type':        shot_type,
                'swing_id':         sw['swing_id'],
                'confidence':       sw['confidence'],
                'peak_time':        sw['peak_time_sec'],
                # Contact time WITHIN the cut clip file (clip_path), not the
                # source compilation -- clip_path's own frame 0 is
                # sw['start_frame'] in the source, so 'peak_time' above
                # (source-relative) is the wrong value to seek a player to
                # when playing clip_path. This is the one that should be used
                # for that purpose.
                'clip_contact_time_sec': round((sw['peak_frame'] - sw['start_frame']) / fps, 3),
                'clip_path':        relative_clip_path(clip_path),
                'camera_angle':     camera_angle,
                'angle_confidence': angle_confidence,
                'trajectory':       trajectory,
            }
            all_entries.append(entry)
            ok += 1

            if ok % 20 == 0:
                print(f'    {ok}/{len(swings)} processed...', end='\r')

        print(f'  {ok} entries built, {skipped} skipped  |  angles: {angle_ok} inferred, {angle_fail} failed')

    angle_landmarker.close()

    with open(out_path, 'w') as f:
        json.dump({
            'total': len(all_entries),
            'shots': {'forehand': 0, 'backhand': 0, 'serve': 0},
            'entries': all_entries,
        }, f)

    # Update shot counts
    with open(out_path) as f:
        db = json.load(f)
    for e in db['entries']:
        db['shots'][e['shot_type']] += 1
    with open(out_path, 'w') as f:
        json.dump(db, f)

    with_angle = sum(1 for e in db['entries'] if e.get('camera_angle') is not None)
    print(f'\nDatabase built: {len(all_entries)} entries')
    print(f"  Forehand:  {db['shots']['forehand']}")
    print(f"  Backhand:  {db['shots']['backhand']}")
    print(f"  Serve:     {db['shots']['serve']}")
    print(f'  Angles:    {with_angle}/{len(all_entries)} entries have camera_angle')
    print(f'  Saved to:  {out_path}')


if __name__ == '__main__':
    build_database()
