"""
Sample frames from our own 9 compilation videos for net-end keypoint
labeling. Unlike random stock photos, these are guaranteed to be broadcast
tennis footage — most frames are the main court-level view where the net
line is visible edge-to-edge, which is exactly the framing infer_angle.py
needs. Full frames are saved (not cropped) since we don't have a net
detector to crop around yet — that's what we're building.
"""
import glob
import json
import os
import random

import cv2

SOURCE_DIR = r'C:\Users\jackp\tennis_app\data\01_source_videos'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_keypoints\own_footage_frames'
META_PATH = r'C:\Users\jackp\tennis_app\data\10_net_keypoints\own_footage_metadata.json'

FRAMES_PER_VIDEO = 12
random.seed(42)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    videos = sorted(glob.glob(os.path.join(SOURCE_DIR, '*', '*.mp4')))
    print(f'{len(videos)} source videos found')

    metadata = []
    idx = 0
    for video_path in videos:
        shot_type = os.path.basename(os.path.dirname(video_path))
        video_name = os.path.splitext(os.path.basename(video_path))[0]

        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total < 100:
            cap.release()
            continue

        # Sample spread across the video, avoiding the very start/end
        sample_frames = sorted(random.sample(range(int(total * 0.05), int(total * 0.95)), FRAMES_PER_VIDEO))

        for frame_num in sample_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                continue
            fname = f'own_{idx:04d}.jpg'
            cv2.imwrite(os.path.join(OUT_DIR, fname), frame)
            metadata.append({
                'local_file': fname, 'source_video': video_path,
                'shot_type': shot_type, 'video_name': video_name, 'frame': frame_num,
            })
            idx += 1
        cap.release()
        print(f'  {video_name}: sampled {FRAMES_PER_VIDEO} frames')

    with open(META_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f'\nSaved {len(metadata)} frames to {OUT_DIR}')


if __name__ == '__main__':
    main()
