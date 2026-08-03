"""
Run the full pose extraction -> swing detection -> clip extraction pipeline
for newly-downloaded compilation videos, without disturbing the existing
compilation_1 data for each shot type. Each new video gets its own
poses/swings files and a swing_id offset so clip filenames never collide
with existing clips in the same data/04_clips/<shot> folder.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '02_pose_extraction'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '03_swing_detection'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '04_clip_extraction'))

from extract_poses import extract_poses
from detect_swings import detect_swings, SHOT_WINDOWS
from extract_clips import process_job

SRC = r'C:\Users\jackp\tennis_app\data\01_source_videos'
POSES_DIR = r'C:\Users\jackp\tennis_app\data\02_pose_extraction'
SWINGS_DIR = r'C:\Users\jackp\tennis_app\data\03_swing_detection'
CLIPS_DIR = r'C:\Users\jackp\tennis_app\data\04_clips'

# (video_filename, shot_type, suffix, swing_id_offset)
NEW_VIDEOS = [
    ('forehand_compilation_2.mp4', 'forehand', '2', 1000),
    ('forehand_compilation_3.mp4', 'forehand', '3', 2000),
    ('backhand_compilation_2.mp4', 'backhand', '2', 1000),
    ('backhand_compilation_3.mp4', 'backhand', '3', 2000),
    ('backhand_compilation_4.mp4', 'backhand', '4', 3000),
    ('serve_compilation_2.mp4',    'serve',    '2', 1000),
]


def main():
    for video_file, shot_type, suffix, offset in NEW_VIDEOS:
        video_path = os.path.join(SRC, shot_type, video_file)
        poses_path = os.path.join(POSES_DIR, f'{shot_type}_poses_{suffix}.json')
        swings_path = os.path.join(SWINGS_DIR, f'{shot_type}_swings_{suffix}.json')

        print(f'\n{"="*60}\n{video_file}\n{"="*60}')

        if not os.path.exists(video_path):
            print(f'  MISSING video: {video_path} — skipping')
            continue

        print('  [1/3] Extracting poses...')
        extract_poses(video_path, poses_path, sample_every=3)

        print('  [2/3] Detecting swings...')
        pre_sec, post_sec = SHOT_WINDOWS[shot_type]
        detect_swings(poses_path, swings_path, pre_sec=pre_sec, post_sec=post_sec, swing_id_offset=offset)

        print('  [3/3] Extracting clips...')
        job = {
            'shot_type': shot_type,
            'video': video_path,
            'poses': poses_path,
            'swings': swings_path,
            'out_dir': os.path.join(CLIPS_DIR, shot_type),
        }
        process_job(job)

    print('\nAll new videos processed.')


if __name__ == '__main__':
    main()
