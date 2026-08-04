"""
Cut candidate swing clips from amateur rally footage for visual labeling.

Unlike extract_clips.py's process_job(), this does NOT run shot-type-specific
confidence scoring (score_forehand/score_backhand/score_serve) -- those
assume the shot type is already known and were tuned for isolated
single-shot compilation footage, not messy rallies. Here, shot type is
unknown until make_amateur_contact_sheets.py's visual labeling pass, which
does both classification and true/false-positive filtering in one step.

Rally footage triggers far more wrist-velocity peaks than a curated
compilation (running, adjusting, non-shot movement), so this evenly samples
a capped number of candidates per video rather than extracting every
detected peak.

Output clips are deliberately kept under data/04_clips/amateur/ -- NEVER
data/04_clips/<forehand|backhand|serve>/ -- so they can never be swept into
build_pro_database.py's pro reference set.
"""
import json
import os
import sys
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '04_clip_extraction'))
from extract_clips import extract_clip, build_pose_index, nearest_pose, get_lm, visible

SWINGS_DIR = r'C:\Users\jackp\tennis_app\data\03_swing_detection'
POSES_DIR = r'C:\Users\jackp\tennis_app\data\02_pose_extraction'
SRC_DIR = r'C:\Users\jackp\tennis_app\data\01_source_videos\amateur'
OUT_DIR = r'C:\Users\jackp\tennis_app\data\04_clips\amateur'

# The two wide/distant-camera videos (doubles court view, and a full-court
# static shot) proved unusable for visual shot-type classification in the
# first two rounds -- players too small to reliably tell forehand from
# backhand from a single frame. Excluded rather than wasting review time.
UNUSABLE_VIDEO_IDS = {'xDNUeZ6Svw0', '169mZbC_MIo'}

VIDEO_IDS = ['rNMc9tpWWZ0', 'hEJ9nPmMRGY', 'Hog_Fox6iiE', 'PnIwyWDY76k',
             '0genZFgM61E', 'AQvVlROWI2k', 'Q-87B8YmzGs']
PER_VIDEO_SAMPLE = 20  # additional candidates per video, beyond ones already extracted


def evenly_sample(items, n):
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest_path = os.path.join(OUT_DIR, 'manifest.json')
    manifest = []
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
        print(f'Loaded {len(manifest)} existing manifest entries — appending new candidates to it.')

    already_extracted = {(m['video_id'], m['swing_id']) for m in manifest}

    for vid in VIDEO_IDS:
        if vid in UNUSABLE_VIDEO_IDS:
            continue
        swings_path = os.path.join(SWINGS_DIR, f'amateur_{vid}_swings.json')
        poses_path = os.path.join(POSES_DIR, f'amateur_{vid}_poses.json')
        video_path = os.path.join(SRC_DIR, f'{vid}.mp4')

        with open(swings_path) as f:
            swing_data = json.load(f)
        with open(poses_path) as f:
            pose_data = json.load(f)

        fps = pose_data['fps']
        pose_index = build_pose_index(pose_data['frames'])
        remaining = [sw for sw in swing_data['swings'] if (vid, sw['swing_id']) not in already_extracted]
        candidates = evenly_sample(remaining, PER_VIDEO_SAMPLE)

        cap = cv2.VideoCapture(video_path)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')

        print(f'=== {vid}: {len(candidates)} new candidates (of {len(remaining)} remaining, '
              f'{len(swing_data["swings"])} total detected) ===')
        accepted = 0
        for sw in candidates:
            peak_lm = nearest_pose(pose_index, sw['peak_frame'])
            if peak_lm is None or not visible(get_lm(peak_lm, 'right_wrist'), threshold=0.3):
                continue

            fname = f'amateur_{vid}_swing_{sw["swing_id"]}.mp4'
            out_path = os.path.join(OUT_DIR, fname)
            extract_clip(cap, sw['start_frame'], sw['end_frame'], out_path, fps, fourcc)
            accepted += 1
            manifest.append({
                'video_id': vid,
                'swing_id': sw['swing_id'],
                'peak_frame': sw['peak_frame'],
                'peak_time_sec': sw['peak_time_sec'],
                'clip_path': out_path,
            })

        cap.release()
        print(f'  extracted {accepted} clips')

    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'\nTotal candidate clips (all videos): {len(manifest)}')
    print(f'Manifest saved to {manifest_path}')


if __name__ == '__main__':
    main()
