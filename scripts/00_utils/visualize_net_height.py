"""
Mandatory visual verification for detect_net_mesh_height() BEFORE any batch
calibration run -- draws the detected net top (from detect_net_endpoints)
and bottom (from detect_net_mesh_height) onto sample frames so a human can
actually confirm the detection looks right, rather than discovering it
doesn't work after a full 631-entry statistical pass (what happened with the
earlier post-height attempt).

Usage:
  python visualize_net_height.py
"""
import glob
import os
import random
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import detect_net_endpoints, detect_net_mesh_height, extract_frame

OUT_DIR = r'C:\Users\jackp\tennis_app\data\runtime\testing_viz\net_height_check'

# IMPORTANT: sample from short SWING CLIPS (what the real pipeline actually runs
# against), not the raw multi-minute source videos -- an earlier version of this
# script sampled random frames from data/01_source_videos/ and got nonsense net
# detections (background fences/trees, not the actual net), which turned out to be
# because those long raw videos contain scene cuts/moments the short-clip pipeline
# never sees, not a real flaw in detect_net_endpoints().
random.seed(9)


def pick_samples():
    picks = []
    for pattern, n in [
        (r'C:\Users\jackp\tennis_app\data\04_clips\forehand\*.mp4', 2),
        (r'C:\Users\jackp\tennis_app\data\04_clips\backhand\*.mp4', 2),
        (r'C:\Users\jackp\tennis_app\data\04_clips\serve\*.mp4', 1),
    ]:
        candidates = glob.glob(pattern)
        picks.extend(random.sample(candidates, min(n, len(candidates))))
    picks.append(r'C:\Users\jackp\tennis_app\data\04_clips\testing\nicolas_vs_florian\nicolas_vs_florian_swing_0009.mp4')
    picks.append(r'C:\Users\jackp\tennis_app\data\04_clips\testing\nicolas_vs_florian\nicolas_vs_florian_swing_0017.mp4')
    return picks


SAMPLE_VIDEOS = pick_samples()


def annotate(video_path, frame_number, out_path):
    frame = extract_frame(video_path, frame_number)
    h, w = frame.shape[:2]
    net = detect_net_endpoints(frame)
    if net is None:
        cv2.putText(frame, 'NO NET DETECTED', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.imwrite(out_path, frame)
        return False

    left_x, right_x, net_y = net
    height_frac = detect_net_mesh_height(frame, left_x, right_x, net_y)

    vis = frame.copy()
    top_y = int(net_y * h)
    cv2.line(vis, (int(left_x * w), top_y), (int(right_x * w), top_y), (0, 255, 0), 2)  # top = green

    if height_frac is not None:
        bottom_y = int((net_y + height_frac) * h)
        cv2.line(vis, (int(left_x * w), bottom_y), (int(right_x * w), bottom_y), (0, 0, 255), 2)  # bottom = red
        cv2.putText(vis, f'height_frac={height_frac:.3f}', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    else:
        cv2.putText(vis, 'NO BOTTOM DETECTED', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    cv2.imwrite(out_path, vis)
    return height_frac is not None


if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)

    ok_count = 0
    total = 0
    for video in SAMPLE_VIDEOS:
        if not os.path.exists(video):
            print(f'Skipping (not found): {video}')
            continue
        cap = cv2.VideoCapture(video)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        if frame_count < 10:
            continue

        sample_frame = random.randint(int(frame_count * 0.2), int(frame_count * 0.8))
        name = os.path.splitext(os.path.basename(video))[0]
        out_path = os.path.join(OUT_DIR, f'{name}_f{sample_frame}.jpg')
        total += 1
        if annotate(video, sample_frame, out_path):
            ok_count += 1
        print(f'{name}: frame {sample_frame} -> {out_path}')

    print(f'\n{ok_count}/{total} frames got a bottom-of-net detection.')
    print(f'View the images in {OUT_DIR} before trusting this numerically.')
