import json
import os
import math
import argparse

# Default window around peak wrist velocity
PRE_SWING_SEC  = 1.0
POST_SWING_SEC = 2.0

# Shot-specific overrides — serves need more pre-swing to capture toss + trophy position
SHOT_WINDOWS = {
    'forehand': (1.0, 2.0),
    'backhand': (1.0, 2.0),
    'serve':    (1.8, 2.0),
}

# Minimum seconds between two separate swings (prevents one swing being counted twice)
MIN_SWING_GAP_SEC = 1.5

# Smoothing window for velocity curve (frames)
SMOOTH_WINDOW = 5

# Velocity threshold percentile — only peaks above this are considered swings
THRESHOLD_PERCENTILE = 85


def get_landmark(frame, name):
    if not frame['landmarks']:
        return None
    for lm in frame['landmarks']:
        if lm['name'] == name:
            return lm
    return None


def distance(a, b):
    return math.sqrt((a['x'] - b['x']) ** 2 + (a['y'] - b['y']) ** 2)


def smooth(values, window):
    result = []
    half = window // 2
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        result.append(sum(values[lo:hi]) / (hi - lo))
    return result


def compute_wrist_velocity(frames):
    """Return per-frame wrist speed (max of left/right wrist movement)."""
    velocities = []
    prev_lw = prev_rw = None

    for frame in frames:
        lw = get_landmark(frame, 'left_wrist')
        rw = get_landmark(frame, 'right_wrist')

        speed = 0.0
        if lw and prev_lw and lw['visibility'] > 0.5:
            speed = max(speed, distance(lw, prev_lw))
        if rw and prev_rw and rw['visibility'] > 0.5:
            speed = max(speed, distance(rw, prev_rw))

        velocities.append(speed)
        prev_lw = lw
        prev_rw = rw

    return velocities


def find_swing_peaks(velocities, frames, fps, threshold_percentile, min_gap_sec):
    """Find frames where wrist speed peaks above threshold."""
    smoothed = smooth(velocities, SMOOTH_WINDOW)

    nonzero = [v for v in smoothed if v > 0]
    if not nonzero:
        return []

    nonzero_sorted = sorted(nonzero)
    idx = int(len(nonzero_sorted) * threshold_percentile / 100)
    threshold = nonzero_sorted[min(idx, len(nonzero_sorted) - 1)]

    min_gap_frames = int(min_gap_sec * fps)
    swings = []
    last_peak_frame = -min_gap_frames

    i = 1
    while i < len(smoothed) - 1:
        if (smoothed[i] >= threshold and
                smoothed[i] >= smoothed[i - 1] and
                smoothed[i] >= smoothed[i + 1]):

            sample_frame = frames[i]['frame']
            if sample_frame - last_peak_frame >= min_gap_frames:
                swings.append({
                    'peak_sample_idx': i,
                    'peak_frame': sample_frame,
                    'peak_time': frames[i]['timestamp'],
                    'peak_velocity': smoothed[i],
                })
                last_peak_frame = sample_frame
        i += 1

    return swings


def build_swing_clips(swings, total_frames, fps, pre_sec, post_sec, swing_id_offset=0):
    clips = []
    for i, sw in enumerate(swings):
        start_frame = max(0, int(sw['peak_frame'] - pre_sec * fps))
        end_frame = min(total_frames - 1, int(sw['peak_frame'] + post_sec * fps))
        clips.append({
            'swing_id': swing_id_offset + i + 1,
            'peak_frame': sw['peak_frame'],
            'peak_time_sec': sw['peak_time'],
            'start_frame': start_frame,
            'end_frame': end_frame,
            'start_time_sec': round(start_frame / fps, 3),
            'end_time_sec': round(end_frame / fps, 3),
            'duration_sec': round((end_frame - start_frame) / fps, 3),
            'peak_velocity': round(sw['peak_velocity'], 5),
        })
    return clips


def detect_swings(json_path, output_path, pre_sec=PRE_SWING_SEC, post_sec=POST_SWING_SEC, swing_id_offset=0):
    print(f"\nLoading {os.path.basename(json_path)}...")
    with open(json_path) as f:
        data = json.load(f)

    fps = data['fps']
    total_frames = data['total_frames']
    frames = data['frames']
    detected_frames = [f for f in frames if f['landmarks']]
    print(f"  {len(frames)} sampled frames, {len(detected_frames)} with pose detected")

    print("  Computing wrist velocity...")
    velocities = compute_wrist_velocity(frames)

    print("  Finding swing peaks...")
    swings = find_swing_peaks(velocities, frames, fps, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC)
    print(f"  Found {len(swings)} potential swings")

    clips = build_swing_clips(swings, total_frames, fps, pre_sec, post_sec, swing_id_offset)

    result = {
        'video': data['video'],
        'fps': fps,
        'total_frames': total_frames,
        'total_duration_sec': round(total_frames / fps, 1),
        'swings_detected': len(clips),
        'swings': clips,
    }

    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"  Saved {len(clips)} swings to {output_path}")
    print("\n  Sample swings:")
    for sw in clips[:5]:
        print(f"    Swing {sw['swing_id']}: {sw['start_time_sec']}s -> {sw['end_time_sec']}s  (peak at {sw['peak_time_sec']}s, vel={sw['peak_velocity']:.4f})")
    if len(clips) > 5:
        print(f"    ... and {len(clips) - 5} more")

    return clips


if __name__ == '__main__':
    poses_base = r'C:\Users\jackp\tennis_app\data\02_pose_extraction'
    swings_base = r'C:\Users\jackp\tennis_app\data\03_swing_detection'

    videos = [
        ('forehand_poses.json', 'forehand_swings.json', 'forehand'),
        ('backhand_poses.json', 'backhand_swings.json', 'backhand'),
        ('serve_poses.json',    'serve_swings.json',    'serve'),
    ]

    total = 0
    for poses_file, swings_file, shot_type in videos:
        poses_path = os.path.join(poses_base, poses_file)
        swings_path = os.path.join(swings_base, swings_file)
        if not os.path.exists(poses_path):
            print(f"Skipping {poses_file} (not found)")
            continue
        pre, post = SHOT_WINDOWS[shot_type]
        print(f"\n{shot_type.upper()}: window = -{pre}s / +{post}s")
        clips = detect_swings(poses_path, swings_path, pre_sec=pre, post_sec=post)
        total += len(clips)

    print(f"\nDone. {total} total swings detected across all videos.")
