"""
Ball speed at the net crossing -- v1.

No pixel-to-real-world scale/homography exists anywhere in this codebase.
The net is the one object of known real-world size the pipeline already
detects reliably (infer_angle.py's trained net-keypoint model), so v1 uses
the net's own pixel span at the moment of contact as a local scale, and
reports ball speed AT THE NET CROSSING rather than off the racket at
contact -- least accurate exactly where contact usually happens, most
accurate near the net, a disclosed limitation rather than a hidden one. A
full ground-plane homography (court-line detection, not built) would let a
future version measure speed anywhere in frame.

Deliberately does NOT try to correct the net's pixel width for camera yaw.
infer_angle.py's own camera-angle estimate is derived FROM this same net
pixel-width (net_angle = acos(net_width / FULL_NET_FRACTION)), so "correcting"
net_width using that angle is circular -- algebraically it just recovers the
constant FULL_NET_FRACTION * frame_width, not an independent physical
correction. Instead, that angle estimate is used only as a reliability GATE:
below MIN_RELIABLE_ANGLE_DEG the net is too foreshortened for the raw pixel
width to be trusted at all, so the whole stat is skipped (returns None)
rather than reported wrong.

Every failure mode here returns None silently (by product decision) rather
than raising or surfacing a placeholder -- an unavailable speed reading is
common (close-up framing, net out of frame, ball tracking lost) and not
worth alarming a user over.
"""
import os
import sys

import numpy as np

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))

from infer_angle import extract_frame, detect_net_endpoints_keypoints  # noqa: E402
from racket_tracker import track_racket_and_ball, _interpolated_ball_track  # noqa: E402

# ITF net-post-to-net-post span: doubles court width (10.97m) + 0.914m
# overhang each side -- the real-world distance the trained net-keypoint
# model's 'net_top_left'/'net_top_right' points bracket, regardless of
# whether the match itself is singles or doubles (the net is always strung
# post to post).
NET_WIDTH_M = 12.8

# Below this estimated camera angle (0 = front-on, 90 = pure side-on) the
# net is foreshortened enough that its raw pixel width can't be trusted as
# a scale -- see module docstring for why this can't just be corrected for.
MIN_RELIABLE_ANGLE_DEG = 30.0

# A wildly implausible result is more likely a tracking/scale error than a
# real reading, given how many approximations are stacked here -- discard
# rather than mislead.
MIN_PLAUSIBLE_KMH = 20.0
MAX_PLAUSIBLE_KMH = 250.0

# How far past contact to keep looking for a net crossing before giving up.
MAX_SEARCH_SECONDS = 2.0

# Half-window (frames) used to fit the ball's velocity around the crossing
# frame -- mirrors verify_shot_contact.py's TRAJECTORY_HALF_WINDOW pattern.
VELOCITY_HALF_WINDOW = 4
VELOCITY_POLY_DEGREE = 2


def _net_scale_and_bounds(video_path, frame_number):
    """
    Returns (meters_per_pixel, net_y_px, left_x_px, right_x_px) at
    frame_number, or None if the net isn't confidently detected there.
    """
    frame = extract_frame(video_path, frame_number)
    net = detect_net_endpoints_keypoints(frame)
    if net is None:
        return None
    left_x, right_x, net_y = net  # normalised [0, 1]

    h, w = frame.shape[:2]
    net_width_px = (right_x - left_x) * w
    if net_width_px <= 0:
        return None

    scale = NET_WIDTH_M / net_width_px
    return scale, net_y * h, left_x * w, right_x * w


def _find_net_crossing(track, net_y_px, left_x_px, right_x_px):
    """
    track: [(frame, (x, y)), ...] in original-frame pixel space, e.g.
    racket_tracker._interpolated_ball_track()'s return shape. Returns the
    frame nearest a sign change in (y - net_y_px) while x sits within the
    net's own horizontal span (a y-crossing outside that span is the ball
    going wide/long, not through the net), or None if no such crossing
    exists in the track.
    """
    if left_x_px > right_x_px:
        left_x_px, right_x_px = right_x_px, left_x_px

    prev_frame, prev_pos = None, None
    for frame, (x, y) in track:
        if prev_pos is not None:
            prev_x, prev_y = prev_pos
            crossed = (prev_y - net_y_px) * (y - net_y_px) <= 0
            in_bounds = (left_x_px <= prev_x <= right_x_px) or (left_x_px <= x <= right_x_px)
            if crossed and in_bounds:
                return frame if abs(y - net_y_px) <= abs(prev_y - net_y_px) else prev_frame
        prev_frame, prev_pos = frame, (x, y)
    return None


def _ball_speed_px_per_frame_at(track, frame, half_window=VELOCITY_HALF_WINDOW,
                                 degree=VELOCITY_POLY_DEGREE):
    """
    Polynomial-fit-and-differentiate speed at `frame`, same pattern as
    verify_shot_contact.py's _racket_velocity_profile/_racket_speed_at, but
    over a plain (frame, (x, y)) track with no crop metadata to unwrap.
    Returns None if there isn't enough data in the window to fit reliably.
    """
    pts = [(f, x, y) for f, (x, y) in track if abs(f - frame) <= half_window]
    if len(pts) < 2:
        return None
    pts.sort(key=lambda p: p[0])

    degree = min(degree, len(pts) - 1)
    if degree < 1:
        return None

    frames = np.array([p[0] for p in pts], dtype=float)
    xs = np.array([p[1] for p in pts], dtype=float)
    ys = np.array([p[2] for p in pts], dtype=float)

    t0 = frames[0]
    t = frames - t0
    px = np.polyfit(t, xs, degree)
    py = np.polyfit(t, ys, degree)
    dpx = np.polyder(px)
    dpy = np.polyder(py)

    eval_t = frame - t0
    vx = np.polyval(dpx, eval_t)
    vy = np.polyval(dpy, eval_t)
    return float(np.hypot(vx, vy))


def estimate_net_crossing_ball_speed_kmh(video_path, contact_frame, fps, camera_angle_deg):
    """
    Best-effort ball speed (km/h) at the moment the ball crosses the net
    after `contact_frame`, or None whenever the estimate can't be trusted
    (see module docstring) -- never raises for an "unavailable" case, only
    for a genuinely broken video_path/model load, same as this pipeline's
    other non-fatal-on-failure stats.
    """
    if camera_angle_deg is None or camera_angle_deg < MIN_RELIABLE_ANGLE_DEG:
        return None

    bounds = _net_scale_and_bounds(video_path, contact_frame)
    if bounds is None:
        return None
    scale, net_y_px, left_x_px, right_x_px = bounds

    end_frame = contact_frame + int(MAX_SEARCH_SECONDS * fps)
    detections, _ = track_racket_and_ball(video_path, frame_range=(contact_frame, end_frame))
    track = _interpolated_ball_track(detections, contact_frame, end_frame)
    if not track:
        return None

    crossing_frame = _find_net_crossing(track, net_y_px, left_x_px, right_x_px)
    if crossing_frame is None:
        return None

    speed_px_per_frame = _ball_speed_px_per_frame_at(track, crossing_frame)
    if speed_px_per_frame is None:
        return None

    kmh = speed_px_per_frame * fps * scale * 3.6
    if not (MIN_PLAUSIBLE_KMH <= kmh <= MAX_PLAUSIBLE_KMH):
        return None
    return round(kmh, 1)
