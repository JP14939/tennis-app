"""
Infer camera angle from a tennis swing video.

Returns 0-90 degrees:
  0  = front view (camera faces player from net-side or behind baseline)
  90 = side view  (camera is along the net line)
  45 = ideal diagonal

Primary signal:   tennis net foreshortening via OpenCV Hough line detection.
Secondary signal: player x-position relative to net centre via MediaPipe.

Usage:
  python infer_angle.py <video_path> [frame_number]
"""

import cv2
import math
import sys
import os
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', 'pose_landmarker.task')

# MediaPipe landmark indices
IDX = {
    'left_shoulder':  11,
    'right_shoulder': 12,
}

# Expected net width as a fraction of frame width at a pure front view.
# Calibrated from broadcast tennis footage — net fills ~80% of frame when
# the camera is head-on. Adjust if results are consistently biased.
FULL_NET_FRACTION = 0.80


# ── MediaPipe helpers ─────────────────────────────────────────────────────────

def create_landmarker():
    """Create a reusable PoseLandmarker for batch processing (avoids reloading model per clip)."""
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        output_segmentation_masks=False,
        num_poses=1,
    )
    return vision.PoseLandmarker.create_from_options(options)


def _run_landmarker(frame, landmarker):
    """Run pose detection on a frame using an existing landmarker instance."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect(mp_image)
    if not result.pose_landmarks:
        return None
    return result.pose_landmarks[0]


def detect_pose(frame):
    """Detect pose from a single frame, creating a temporary landmarker."""
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        output_segmentation_masks=False,
        num_poses=1,
    )
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    with vision.PoseLandmarker.create_from_options(options) as lmk:
        result = lmk.detect(mp_image)
    if not result.pose_landmarks:
        return None
    return result.pose_landmarks[0]


# ── Frame extraction ──────────────────────────────────────────────────────────

def extract_frame(video_path, frame_number):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video_path}')
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_number = max(0, min(frame_number, total - 1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f'Could not read frame {frame_number} from {video_path}')
    return frame


# ── Net detection ─────────────────────────────────────────────────────────────

def detect_net_endpoints(frame):
    """
    Detect the tennis net as the dominant horizontal line in the middle of the frame.

    The net is the longest roughly-horizontal edge in the centre vertical band
    (between 25% and 75% of frame height).

    Returns (left_x, right_x, net_y) in normalised [0, 1] coordinates, or None.
    """
    h, w = frame.shape[:2]

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    # Restrict detection to the centre vertical band where the net lives
    roi_mask = np.zeros_like(edges)
    roi_mask[int(h * 0.25):int(h * 0.75), :] = 255
    edges = cv2.bitwise_and(edges, roi_mask)

    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=80,
        minLineLength=w // 8,
        maxLineGap=30,
    )

    if lines is None:
        return None

    # Keep only roughly horizontal lines (within ±20° of horizontal)
    horizontal = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        if x2 == x1:
            continue
        line_angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
        if line_angle <= 20 or line_angle >= 160:
            length = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            horizontal.append((length, x1, y1, x2, y2))

    if not horizontal:
        return None

    # Take the longest horizontal line that isn't a full-width banner/board.
    # Lines spanning >88% of frame are advertising boards, not the net.
    horizontal.sort(reverse=True)
    MAX_NET_FRACTION = 0.75
    chosen = None
    for length, x1, y1, x2, y2 in horizontal:
        apparent_width = abs(x2 - x1) / w
        if apparent_width <= MAX_NET_FRACTION:
            chosen = (x1, y1, x2, y2)
            break

    if chosen is None:
        return None

    x1, y1, x2, y2 = chosen
    left_x = min(x1, x2) / w
    right_x = max(x1, x2) / w
    net_y = (y1 + y2) / 2 / h

    return left_x, right_x, net_y


# ── Angle inference ───────────────────────────────────────────────────────────

def _angle_from_frame(frame, landmarker):
    """
    Compute camera angle from a single frame.
    Returns (net_width, net_center_x, net_y, player_x, player_vis) or None if net not found.
    """
    net = detect_net_endpoints(frame)
    if net is None:
        return None

    left_x, right_x, net_y = net
    net_width = right_x - left_x
    net_center_x = (left_x + right_x) / 2

    mp_landmarks = _run_landmarker(frame, landmarker) if landmarker is not None else detect_pose(frame)
    player_x = None
    player_vis = 0.0
    if mp_landmarks is not None:
        ls = mp_landmarks[IDX['left_shoulder']]
        rs = mp_landmarks[IDX['right_shoulder']]
        if ls.visibility > 0.3 and rs.visibility > 0.3:
            player_x = (ls.x + rs.x) / 2
            player_vis = (ls.visibility + rs.visibility) / 2

    return net_width, net_center_x, net_y, player_x, player_vis


def infer_camera_angle(video_path, frame_number=None, landmarker=None):
    """
    Returns (angle_deg, confidence, debug_info) or (None, 0, reason_str).

    angle_deg:  0° = front view, 90° = pure side view
    confidence: 0-1
    landmarker: optional pre-created PoseLandmarker for batch processing.
                If None, a temporary landmarker is created and destroyed per call.

    Samples 3 frames (at 25%, 50%, 75% of clip) and takes the median net_width.
    Consistent detections = the net; wildly varying ones = noise from banners/graphics.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None, 0.0, f'Cannot open video: {video_path}'
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    # Sample 3 candidate frames; use caller-specified frame as anchor if provided
    if frame_number is not None:
        offsets = [-int(total * 0.15), 0, int(total * 0.15)]
        candidate_frames = [max(0, min(frame_number + o, total - 1)) for o in offsets]
    else:
        candidate_frames = [int(total * q) for q in (0.25, 0.50, 0.75)]

    measurements = []
    for fn in candidate_frames:
        frame = extract_frame(video_path, fn)
        result = _angle_from_frame(frame, landmarker)
        if result is not None:
            measurements.append(result)

    if not measurements:
        return None, 0.0, 'Net not detected in any sampled frame'

    # Use median net_width for robustness against outlier frames
    net_widths = [m[0] for m in measurements]
    net_widths_sorted = sorted(net_widths)
    median_width = net_widths_sorted[len(net_widths_sorted) // 2]

    # Reject if all detections are suspiciously wide (banner false-positives)
    # and they are consistent (low spread = same banner detected in every frame)
    width_spread = max(net_widths) - min(net_widths)
    if median_width > 0.72 and width_spread < 0.05:
        return None, 0.0, f'Net detection unreliable: consistent wide line (w={median_width:.2f}) likely a banner'

    # Use the measurement closest to the median width
    best = min(measurements, key=lambda m: abs(m[0] - median_width))
    net_width, net_center_x, net_y, player_x, player_vis = best

    debug = {
        'frames_sampled':  candidate_frames,
        'net_widths':      [round(w, 3) for w in net_widths],
        'median_width':    round(median_width, 3),
        'width_spread':    round(width_spread, 3),
        'player_x':        round(player_x, 3) if player_x is not None else None,
        'player_vis':      round(player_vis, 3),
        'net': {
            'width':    round(net_width, 3),
            'center_x': round(net_center_x, 3),
            'y':        round(net_y, 3),
        },
    }

    # --- Primary: angle from net foreshortening ---
    apparent_ratio = min(net_width / FULL_NET_FRACTION, 1.0)
    net_angle = math.degrees(math.acos(max(apparent_ratio, 0.001)))
    net_angle = max(0.0, min(90.0, net_angle))

    debug['net_apparent_ratio'] = round(apparent_ratio, 3)
    debug['net_angle'] = round(net_angle, 1)

    # --- Secondary: player offset from net centre ---
    player_angle = None
    if player_x is not None:
        offset = abs(player_x - net_center_x)
        MAX_SIDE_OFFSET = 0.40
        offset_ratio = min(offset / MAX_SIDE_OFFSET, 1.0)
        player_angle = math.degrees(math.asin(offset_ratio))
        player_angle = max(0.0, min(90.0, player_angle))
        debug['player_net_offset'] = round(offset, 3)
        debug['player_angle'] = round(player_angle, 1)

    # --- Weighted average ---
    net_weight    = 2.0
    player_weight = player_vis if player_angle is not None else 0.0

    if player_angle is not None and player_weight > 0:
        angle_deg = (net_angle * net_weight + player_angle * player_weight) / (net_weight + player_weight)
    else:
        angle_deg = net_angle

    angle_deg = round(max(0.0, min(90.0, angle_deg)), 1)

    # Confidence: net detected consistently (base 0.7, penalty for high spread)
    spread_penalty = min(width_spread / 0.2, 0.3)
    confidence = round(min(0.7 - spread_penalty + player_vis * 0.3, 1.0), 3)

    debug['angle_final'] = angle_deg

    return angle_deg, confidence, debug


def infer_angle_from_source(source_video_path, peak_time_sec, landmarker=None):
    """
    Fallback angle inference using the full source compilation video.

    Samples frames outside the swing window (before the swing starts and after
    it ends), where the court is more likely to be unobstructed and the net visible.

    Returns same signature as infer_camera_angle: (angle_deg, confidence, debug) or (None, 0, reason).
    """
    cap = cv2.VideoCapture(source_video_path)
    if not cap.isOpened():
        return None, 0.0, f'Cannot open source video: {source_video_path}'
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    peak_frame = int(peak_time_sec * fps)

    # Sample before and after the swing — outside the 3s clip window
    offsets_sec = [-6, -4, -2, 3, 5]
    candidate_frames = [
        max(0, min(peak_frame + int(off * fps), total - 1))
        for off in offsets_sec
    ]
    # Deduplicate in case video is short
    candidate_frames = list(dict.fromkeys(candidate_frames))

    measurements = []
    for fn in candidate_frames:
        try:
            frame = extract_frame(source_video_path, fn)
            result = _angle_from_frame(frame, landmarker)
            if result is not None:
                measurements.append(result)
        except Exception:
            continue

    if not measurements:
        return None, 0.0, 'Net not detected in source video frames around swing'

    net_widths = [m[0] for m in measurements]
    net_widths_sorted = sorted(net_widths)
    median_width = net_widths_sorted[len(net_widths_sorted) // 2]
    width_spread = max(net_widths) - min(net_widths)

    if median_width > 0.72 and width_spread < 0.05:
        return None, 0.0, f'Source video detection unreliable: consistent wide line (w={median_width:.2f})'

    best = min(measurements, key=lambda m: abs(m[0] - median_width))
    net_width, net_center_x, _, player_x, player_vis = best

    apparent_ratio = min(net_width / FULL_NET_FRACTION, 1.0)
    net_angle = math.degrees(math.acos(max(apparent_ratio, 0.001)))
    net_angle = max(0.0, min(90.0, net_angle))

    player_angle = None
    if player_x is not None:
        offset = abs(player_x - net_center_x)
        offset_ratio = min(offset / 0.40, 1.0)
        player_angle = math.degrees(math.asin(offset_ratio))
        player_angle = max(0.0, min(90.0, player_angle))

    net_weight    = 2.0
    player_weight = player_vis if player_angle is not None else 0.0

    if player_angle is not None and player_weight > 0:
        angle_deg = (net_angle * net_weight + player_angle * player_weight) / (net_weight + player_weight)
    else:
        angle_deg = net_angle

    angle_deg = round(max(0.0, min(90.0, angle_deg)), 1)

    spread_penalty = min(width_spread / 0.2, 0.3)
    # Slightly lower confidence than clip-based detection (source frames are further from the swing)
    confidence = round(min(0.6 - spread_penalty + player_vis * 0.25, 1.0), 3)

    debug = {
        'source': source_video_path,
        'peak_time_sec': peak_time_sec,
        'frames_sampled': candidate_frames,
        'net_widths': [round(w, 3) for w in net_widths],
        'median_width': round(median_width, 3),
        'net_angle': round(net_angle, 1),
        'angle_final': angle_deg,
    }

    return angle_deg, confidence, debug


# ── Label helper ──────────────────────────────────────────────────────────────

def angle_label(angle):
    if angle is None:    return 'Unknown'
    if angle < 20:       return 'Front view'
    if angle < 40:       return 'Semi-front'
    if angle < 60:       return 'Diagonal (ideal)'
    if angle < 75:       return 'Semi-side'
    return 'Side view'


# ── CLI / test helpers ────────────────────────────────────────────────────────

def run_on_clips(shot_type, n=5):
    """Test angle inference on a sample of pro clips."""
    clips_dir = rf'C:\Users\jackp\tennis_app\data\04_clips\{shot_type}'
    if not os.path.exists(clips_dir):
        print(f'No clips found at {clips_dir}')
        return

    clips = [f for f in os.listdir(clips_dir) if f.endswith('.mp4')][:n]
    print(f'\nTesting on {len(clips)} {shot_type} clips:\n')
    print(f'{"Clip":<45} {"Angle":>6}  {"Label":<20} {"Conf":>5}')
    print('-' * 80)

    for clip in clips:
        path = os.path.join(clips_dir, clip)
        angle, conf, debug = infer_camera_angle(path)
        if angle is None:
            print(f'{clip:<45} {"N/A":>6}  {str(debug):<20}')
        else:
            print(f'{clip:<45} {angle:>5.1f}°  {angle_label(angle):<20} {conf:>5.3f}')


if __name__ == '__main__':
    if len(sys.argv) >= 2:
        video_path = sys.argv[1]
        frame_num  = int(sys.argv[2]) if len(sys.argv) >= 3 else None
        angle, conf, debug = infer_camera_angle(video_path, frame_num)
        if angle is None:
            print(f'Could not infer angle: {debug}')
        else:
            print(f'\nCamera angle: {angle}° — {angle_label(angle)}')
            print(f'Confidence:   {conf}')
            print(f'Debug:        {debug}')
    else:
        for shot in ['forehand', 'backhand', 'serve']:
            run_on_clips(shot, n=5)
