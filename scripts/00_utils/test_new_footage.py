import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '02_pose_extraction'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '03_swing_detection'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '04_clip_extraction'))

from extract_poses import extract_poses
from detect_swings import detect_swings
import cv2

# Runs a raw (already-trimmed) video through stages 02-04 of the pipeline:
# pose extraction -> swing detection -> per-swing clip extraction.
# Unlike the JOBS-list scripts in each stage, this takes an arbitrary video with
# unknown shot type — no confidence scoring is applied (that scoring assumes a known
# shot type), clips are cut for every detected swing peak for manual review.


def run(video_path, name, out_root):
    poses_dir = os.path.join(out_root, '02_pose_extraction', 'testing')
    swings_dir = os.path.join(out_root, '03_swing_detection', 'testing')
    clips_dir = os.path.join(out_root, '04_clips', 'testing', name)
    for d in (poses_dir, swings_dir, clips_dir):
        os.makedirs(d, exist_ok=True)

    poses_path = os.path.join(poses_dir, f'{name}_poses.json')
    swings_path = os.path.join(swings_dir, f'{name}_swings.json')

    print(f"\n=== {name}: pose extraction ===")
    extract_poses(video_path, poses_path, sample_every=3)

    print(f"\n=== {name}: swing detection ===")
    clips = detect_swings(poses_path, swings_path, pre_sec=1.0, post_sec=2.0)

    print(f"\n=== {name}: clip extraction ({len(clips)} swings) ===")
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    for sw in clips:
        fname = f"{name}_swing_{sw['swing_id']:04d}.mp4"
        out_path = os.path.join(clips_dir, fname)
        cap.set(cv2.CAP_PROP_POS_FRAMES, sw['start_frame'])
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
        for _ in range(sw['end_frame'] - sw['start_frame']):
            ret, frame = cap.read()
            if not ret:
                break
            writer.write(frame)
        writer.release()
        sw['clip_path'] = out_path
    cap.release()

    print(f"Clips written to {clips_dir}")
    return clips


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('video', help='Path to trimmed video')
    parser.add_argument('name', help='Short name for output files (e.g. mark_vs_silas)')
    parser.add_argument('--out-root', default=r'C:\Users\jackp\tennis_app\data')
    args = parser.parse_args()
    run(args.video, args.name, args.out_root)
