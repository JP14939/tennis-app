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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', 'pose_landmarker.task')

# MediaPipe landmark indices
IDX = {
    'left_shoulder':  11,
    'right_shoulder': 12,
    'left_hip':       23,
    'right_hip':      24,
    'left_ankle':     27,
    'right_ankle':    28,
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

NET_KEYPOINT_MODEL_PATH = os.path.join(DATA_DIR, '10_net_detection', 'yolo_pose_run_v4', 'weights', 'best.pt')
NET_KEYPOINT_CONF_MIN = 0.4
_net_kp_model = None


def _get_net_kp_model():
    global _net_kp_model
    if _net_kp_model is None:
        from ultralytics import YOLO
        _net_kp_model = YOLO(NET_KEYPOINT_MODEL_PATH)
    return _net_kp_model


NET_KEYPOINT_NAMES = ['net_top_left', 'net_top_right', 'left_post_base', 'right_post_base']


def run_net_keypoint_model(frame):
    """
    Raw inference from the trained YOLO-pose net-keypoint model (validated
    this session as accurate on both pro and real elevated footage). Single
    model call shared by both the horizontal-angle detector below and the
    vertical elevation signal (post-base points), so callers needing both
    don't pay for two inference passes.

    Returns a dict of whichever of NET_KEYPOINT_NAMES were detected with
    confidence >= NET_KEYPOINT_CONF_MIN, each a (x, y) normalised [0, 1]
    tuple. Missing points (occluded/not visible) are simply absent from the
    dict -- callers must check membership, not assume all 4 keys exist.
    """
    h, w = frame.shape[:2]
    model = _get_net_kp_model()
    results = model.predict(frame, verbose=False)
    if len(results[0].keypoints) == 0 or results[0].keypoints.xy.shape[1] == 0:
        return {}

    kpts = results[0].keypoints.xy[0].cpu().numpy()
    confs = results[0].keypoints.conf[0].cpu().numpy() if results[0].keypoints.conf is not None else None

    out = {}
    for i, name in enumerate(NET_KEYPOINT_NAMES):
        x, y = kpts[i]
        if x == 0 and y == 0:
            continue
        if confs is not None and confs[i] < NET_KEYPOINT_CONF_MIN:
            continue
        out[name] = (float(x) / w, float(y) / h)  # cast off numpy float32 -- not JSON-serializable downstream
    return out


def detect_net_endpoints_keypoints(frame):
    """
    Preferred net-edge detector: the trained YOLO-pose net-keypoint model,
    unlike detect_net_endpoints() below (which frequently locks onto backdrop
    boards/fences instead of the net -- see project memory
    project_vertical_angle_detection.md). Returns None (not a guess) when the
    net isn't confidently detected -- e.g. tight broadcast shots where it's
    simply out of frame -- so the caller can fall back to the older heuristic.

    Returns (left_x, right_x, net_y) in normalised [0, 1] coordinates, or None.
    """
    kp = run_net_keypoint_model(frame)
    if 'net_top_left' not in kp or 'net_top_right' not in kp:
        return None
    left_x, right_x = sorted([kp['net_top_left'][0], kp['net_top_right'][0]])
    net_y = (kp['net_top_left'][1] + kp['net_top_right'][1]) / 2
    return left_x, right_x, net_y


def height_ratio_from_keypoints(kp):
    """
    Vertical elevation signal: post-base-to-net-top vertical distance as a
    fraction of frame height, averaged over whichever post base(s) were
    detected. Validated this session (against real elevated footage) to run
    ~25-30% lower for elevated camera positions than level ones -- a real but
    noisy signal (only 2 known-elevated source videos to validate against),
    not a precise angle. Returns None if no post base was detected.
    """
    if 'net_top_left' not in kp or 'net_top_right' not in kp:
        return None
    net_top_y = (kp['net_top_left'][1] + kp['net_top_right'][1]) / 2
    ratios = [abs(kp[base][1] - net_top_y) for base in ('left_post_base', 'right_post_base') if base in kp]
    if not ratios:
        return None
    return sum(ratios) / len(ratios)


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


def detect_court_sidelines(frame):
    """
    Detect the two court sidelines as the longest diagonal line on each side
    of frame-center in the lower portion of the frame, converging toward a
    vanishing point above -- visible from ANY on-court camera position,
    unlike the net (only usably foreshortened from certain positions, and
    essentially unusable from a net-position/'front' recording where the
    camera is right at/behind it). Same cv2.HoughLinesP toolkit as
    detect_net_endpoints(), a different region and line orientation.

    Returns (left_angle_deg, right_angle_deg): each sideline's deviation
    from vertical, in degrees, signed positive when the line leans toward
    frame-center as it goes up (the expected perspective-convergence
    direction) -- or None if a confident pair of candidate lines wasn't
    found on both sides.
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    # Sidelines live in the lower portion of the frame (the court surface),
    # below where the net/horizon typically sits -- same ROI-restriction
    # principle as detect_net_endpoints(), a different band.
    roi_mask = np.zeros_like(edges)
    roi_mask[int(h * 0.35):h, :] = 255
    edges = cv2.bitwise_and(edges, roi_mask)

    lines = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=60,
        minLineLength=int(h * 0.15), maxLineGap=25,
    )
    if lines is None:
        return None

    # Sidelines are diagonal -- not horizontal (net/baseline) or purely
    # vertical (a net post) -- keep lines between 15deg and 75deg off
    # horizontal (equivalently, 15deg-75deg off vertical too).
    candidates = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        if x1 == x2 and y1 == y2:
            continue
        # Normalize so (x1, y1) is the LOWER point (larger y = lower in
        # image coords) -- makes "leans toward center going up" well-defined
        # regardless of Hough's arbitrary endpoint order.
        if y1 < y2:
            x1, y1, x2, y2 = x2, y2, x1, y1
        dx, dy = x2 - x1, y2 - y1
        if dy >= 0:
            continue  # not going upward -- not a sideline candidate
        # atan2(dy, dx) directly would land outside [0, 90] whenever dx is
        # negative (a line going up-and-to-the-left) since it doesn't fold
        # quadrants back into an acute angle -- use abs() on both
        # components first so this is always the line's acute angle from
        # horizontal, regardless of which way it leans.
        line_angle_from_horizontal = math.degrees(math.atan2(abs(dy), abs(dx)))
        if not (15 <= line_angle_from_horizontal <= 75):
            continue
        length = math.sqrt(dx ** 2 + dy ** 2)
        bottom_x_norm = x1 / w
        candidates.append((length, bottom_x_norm, x1, y1, x2, y2))

    if not candidates:
        return None

    left_candidates = [c for c in candidates if c[1] < 0.5]
    right_candidates = [c for c in candidates if c[1] >= 0.5]
    if not left_candidates or not right_candidates:
        return None

    # Longest candidate on each side -- same "longest wins" heuristic
    # detect_net_endpoints() uses for picking the real net line over noise.
    left_candidates.sort(reverse=True)
    right_candidates.sort(reverse=True)
    _, _, lx1, ly1, lx2, ly2 = left_candidates[0]
    _, _, rx1, ry1, rx2, ry2 = right_candidates[0]

    def angle_from_vertical(x1, y1, x2, y2):
        # (x1, y1) is the lower point, (x2, y2) the upper one (see
        # normalization above). Positive = converging toward center as it
        # goes up (expected); negative = diverging (a noisy/wrong match).
        dx, dy = x2 - x1, y1 - y2  # dy > 0 (upward)
        angle = math.degrees(math.atan2(abs(dx), dy))
        converging = abs(x2 - w * 0.5) < abs(x1 - w * 0.5)
        return angle if converging else -angle

    left_angle_deg = round(angle_from_vertical(lx1, ly1, lx2, ly2), 1)
    right_angle_deg = round(angle_from_vertical(rx1, ry1, rx2, ry2), 1)
    return left_angle_deg, right_angle_deg


def angle_from_sideline_symmetry(left_angle_deg, right_angle_deg):
    """
    Converts court-sideline convergence asymmetry into a rough 0-90 camera
    angle estimate, in the same direction infer_camera_angle()'s net-based
    reading uses (0 = front/centered, 90 = side-on/off to one side). A
    centered, front-on camera produces two sidelines converging
    symmetrically (left_angle_deg ~= right_angle_deg); an off-center or
    angled camera makes one side's convergence noticeably steeper than the
    other's. Deliberately the simpler, more robust signal (slope asymmetry)
    rather than full vanishing-point triangulation -- matches this file's
    established style of simple, wide-banded geometric proxies over precise
    photogrammetry (see elevation_label()/framing_label()'s own thresholds).

    Callers must only pass two POSITIVE (converging) angles -- a negative
    (diverging) reading from detect_court_sidelines() means that side's
    detected line isn't a sane sideline match and the pair shouldn't be
    trusted at all; filtering that is the caller's job, not this function's.

    Returns None only for the degenerate both-angles-zero case.
    """
    total = left_angle_deg + right_angle_deg
    if total <= 1e-6:
        return None
    asymmetry = abs(left_angle_deg - right_angle_deg) / total  # 0 (symmetric) .. 1 (maximally asymmetric)
    return round(min(90.0, asymmetry * 90.0), 1)


def detect_post_height(frame, left_x, right_x, net_y):
    """
    Estimate a net post's visible vertical pixel extent, searching narrow
    vertical strips at the net's already-detected left/right edges for
    near-vertical Hough lines. Primary signal for vertical camera elevation —
    a post that appears compressed relative to a level-camera baseline implies
    the camera is angled down from above (looking along the post's length
    foreshortens it). This is a raw pixel measurement, not yet calibrated into
    an elevation estimate — see calibrate step in enrich_pro_elevation.py.

    Returns the longest detected near-vertical line's length as a fraction of
    frame height, or None if neither post yields a clean line.
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    STRIP_FRAC = 0.03  # +/- 3% of frame width around each post x-position
    best_length_px = None

    for post_x_norm in (left_x, right_x):
        post_x = int(post_x_norm * w)
        x_lo = max(0, post_x - int(w * STRIP_FRAC))
        x_hi = min(w, post_x + int(w * STRIP_FRAC))
        y_lo = max(0, int((net_y - 0.05) * h))

        roi_mask = np.zeros_like(edges)
        roi_mask[y_lo:h, x_lo:x_hi] = 255
        strip_edges = cv2.bitwise_and(edges, roi_mask)

        lines = cv2.HoughLinesP(
            strip_edges, rho=1, theta=np.pi / 180, threshold=25,
            minLineLength=int(h * 0.05), maxLineGap=15,
        )
        if lines is None:
            continue

        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            if y2 == y1:
                continue
            line_angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
            if 70 <= line_angle <= 110:  # near-vertical
                length = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                if best_length_px is None or length > best_length_px:
                    best_length_px = length

    if best_length_px is None:
        return None
    return best_length_px / h


def detect_net_mesh_height(frame, left_x, right_x, net_y):
    """
    Estimate the net's vertical extent (top cord to ground) via texture
    (edge-density) segmentation rather than a single Hough edge line -- the
    net's crosshatch mesh produces much higher local edge density than the
    court surface below it. This is a different technique than the
    post-height Hough-line detector tried earlier (which showed no real
    separation between known-good and known-bad footage when calibrated
    against the full pro database -- see project memory
    project_vertical_angle_detection.md -- likely because thin posts at
    typical video resolution get confused with background clutter).

    NOT YET INTEGRATED into infer_camera_angle() -- must be visually
    verified against sample frames first (see visualize_net_height.py)
    before trusting it numerically, same lesson learned from the post-height
    attempt not being checked until after a full expensive calibration run.

    Returns net_height_frac (vertical extent below net_y, as a fraction of
    frame height) or None if no clear mesh-to-court transition is found.
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    net_y_px = int(net_y * h)
    PATCH_H = max(4, int(h * 0.01))
    MAX_DEPTH = int(h * 0.25)  # net won't visually span more than ~25% of frame height
    SAMPLE_FRACS = (0.25, 0.5, 0.75)

    bottoms = []
    for frac in SAMPLE_FRACS:
        x = int((left_x + (right_x - left_x) * frac) * w)
        x_lo = max(0, x - int(w * 0.02))
        x_hi = min(w, x + int(w * 0.02))

        densities = []
        for y in range(net_y_px, min(h, net_y_px + MAX_DEPTH), PATCH_H):
            patch = edges[y:y + PATCH_H, x_lo:x_hi]
            densities.append(patch.mean() / 255.0 if patch.size else 0.0)

        if not densities:
            continue

        baseline = max(densities[:max(1, len(densities) // 4)], default=0)
        if baseline < 0.02:  # no real texture near the top -- not a usable detection
            continue

        threshold = baseline * 0.4
        bottom_step = next((i for i, d in enumerate(densities) if d < threshold), None)
        if bottom_step is None:
            continue  # density never dropped off within MAX_DEPTH

        bottoms.append(net_y_px + bottom_step * PATCH_H)

    if not bottoms:
        return None

    bottoms.sort()
    median_bottom = bottoms[len(bottoms) // 2]
    return (median_bottom - net_y_px) / h


# ── Angle inference ───────────────────────────────────────────────────────────

def _angle_from_frame(frame, landmarker):
    """
    Compute camera angle from a single frame.
    Returns (net_width, net_center_x, net_y, player_x, player_vis, post_height_frac,
    ankle_y, used_keypoints, height_ratio, stance_width_ratio, shoulder_tilt_deg)
    or None if net not found.
    post_height_frac/ankle_y are the older, raw/uncalibrated Hough-based vertical
    signal; height_ratio is the newer, validated keypoint-model-based one (only
    available when used_keypoints is True and a post base was detected).
    used_keypoints is True when the trained net-keypoint model found the net
    (preferred, more reliable); False means it fell back to the older
    Hough-line heuristic for this frame.

    stance_width_ratio/shoulder_tilt_deg (both None if hips/shoulders aren't
    both visible) are a supplementary pose-geometry signal for camera
    perpendicularity/tilt -- see check_camera_setup_frame()'s framing_status
    for how they're used. Appended at the end rather than inserted so
    existing positional unpacking of the first 9 values elsewhere in this
    file doesn't need to change field order.
    """
    kp = run_net_keypoint_model(frame)
    used_keypoints = 'net_top_left' in kp and 'net_top_right' in kp
    if used_keypoints:
        left_x, right_x = sorted([kp['net_top_left'][0], kp['net_top_right'][0]])
        net_y = (kp['net_top_left'][1] + kp['net_top_right'][1]) / 2
    else:
        net = detect_net_endpoints(frame)
        if net is None:
            return None
        left_x, right_x, net_y = net

    net_width = right_x - left_x
    net_center_x = (left_x + right_x) / 2
    post_height_frac = detect_post_height(frame, left_x, right_x, net_y)
    height_ratio = height_ratio_from_keypoints(kp) if used_keypoints else None

    mp_landmarks = _run_landmarker(frame, landmarker) if landmarker is not None else detect_pose(frame)
    player_x = None
    player_vis = 0.0
    ankle_y = None
    if mp_landmarks is not None:
        ls = mp_landmarks[IDX['left_shoulder']]
        rs = mp_landmarks[IDX['right_shoulder']]
        if ls.visibility > 0.3 and rs.visibility > 0.3:
            player_x = (ls.x + rs.x) / 2
            player_vis = (ls.visibility + rs.visibility) / 2

        la = mp_landmarks[IDX['left_ankle']]
        ra = mp_landmarks[IDX['right_ankle']]
        ankle_ys = [a.y for a in (la, ra) if a.visibility > 0.3]
        if ankle_ys:
            ankle_y = sum(ankle_ys) / len(ankle_ys)

    stance_width_ratio = None
    shoulder_tilt_deg = None
    if mp_landmarks is not None:
        lh = mp_landmarks[IDX['left_hip']]
        rh = mp_landmarks[IDX['right_hip']]
        if ls.visibility > 0.3 and rs.visibility > 0.3 and lh.visibility > 0.3 and rh.visibility > 0.3:
            dx = rs.x - ls.x
            dy = rs.y - ls.y
            shoulder_width = abs(dx)
            hip_width = abs(rh.x - lh.x)
            if shoulder_width > 1e-4:
                stance_width_ratio = round(hip_width / shoulder_width, 3)
            # A line's orientation only means something mod 180 deg, so wrap
            # into [0, 90] (0 = horizontal, 90 = vertical) rather than
            # leaving atan2's raw [-180, 180] output as-is. Confirmed
            # empirically necessary: real swing-clip frames sampled
            # mid-rotation, or back-view frames where MediaPipe's anatomical
            # left/right flips which shoulder appears on-screen-left,
            # otherwise produced nonsense >90 deg "tilt" values on footage
            # that was never actually tilted (see this session's spot-check).
            raw = abs(math.degrees(math.atan2(dy, dx))) % 180
            wrapped = min(raw, 180 - raw)
            # Only trust this as a CAMERA-tilt reading when the shoulder
            # line is still closer to horizontal than vertical -- once the
            # player's body is rotated enough that dy dominates dx, a large
            # "tilt" reflects body rotation (mid-swing, or just turned to
            # the side), not the camera being canted, and reporting it as
            # camera advice would be actively wrong.
            shoulder_tilt_deg = round(wrapped, 1) if abs(dx) >= abs(dy) else None

    return (net_width, net_center_x, net_y, player_x, player_vis, post_height_frac, ankle_y,
            used_keypoints, height_ratio, stance_width_ratio, shoulder_tilt_deg)


# View-direction margin: fraction of the player's own on-screen height
# (shoulder_y to ankle_y) used as tolerance around that span when deciding
# whether the net's y-position falls "within" it -- scales with how big the
# player appears in frame instead of a fixed pixel-space value.
VIEW_DIRECTION_MARGIN_FRAC = 0.15


def detect_view_direction(frame, landmarker=None):
    """
    Distinguish a genuine FRONT view (camera at/near the net, facing the far
    player -- you see their face) from a BACK view (camera behind a
    baseline, facing the near player -- you see their back). Both can
    produce a similarly narrow apparent net width and land in the same
    low camera_angle bucket from _angle_from_frame()/infer_camera_angle(),
    even though the pose landmarks are essentially mirrored between them --
    this is a separate signal, not a replacement for that angle.

    Key visual distinction: in a back view the net sits BEHIND the player
    in the frame (between their own body and the far side), so its y
    falls within the player's own on-screen vertical span (shoulders to
    ankles). In a front view the net is close to the camera -- low in
    frame, at/below the player's feet -- and what's behind the player
    instead is the far fence/billboards, not the net.

    Returns 'front', 'back', or 'unknown' (net or pose not confidently
    detected, or the net falls outside both bands -- e.g. an elevated
    camera -- where this heuristic isn't calibrated to guess).
    """
    kp = run_net_keypoint_model(frame)
    if 'net_top_left' in kp and 'net_top_right' in kp:
        net_y = (kp['net_top_left'][1] + kp['net_top_right'][1]) / 2
    else:
        net = detect_net_endpoints(frame)
        if net is None:
            return 'unknown'
        _, _, net_y = net

    mp_landmarks = _run_landmarker(frame, landmarker) if landmarker is not None else detect_pose(frame)
    if mp_landmarks is None:
        return 'unknown'

    ls = mp_landmarks[IDX['left_shoulder']]
    rs = mp_landmarks[IDX['right_shoulder']]
    la = mp_landmarks[IDX['left_ankle']]
    ra = mp_landmarks[IDX['right_ankle']]

    shoulder_ys = [s.y for s in (ls, rs) if s.visibility > 0.3]
    ankle_ys = [a.y for a in (la, ra) if a.visibility > 0.3]
    if not shoulder_ys or not ankle_ys:
        return 'unknown'

    shoulder_y = sum(shoulder_ys) / len(shoulder_ys)
    ankle_y = sum(ankle_ys) / len(ankle_ys)
    span = ankle_y - shoulder_y
    if span <= 0.01:
        return 'unknown'

    margin = span * VIEW_DIRECTION_MARGIN_FRAC
    if shoulder_y - margin <= net_y <= ankle_y + margin:
        return 'back'
    if net_y > ankle_y + margin:
        return 'front'
    return 'unknown'


# Mirrors check_camera_setup.py's ELEVATION_MESSAGES, but shorter -- meant for
# a small live overlay badge during camera positioning, not a full results
# banner. Kept separate/duplicated deliberately: same signal, different
# framing for a tighter UI space.
LIVE_FRAMING_MESSAGES = {
    'ok':                 '',
    'tilted':             ' Camera looks tilted — try leveling it.',
    'compressed_stance':  ' Stance looks compressed — try moving more front-on.',
    'unknown':            '',
}

LIVE_ELEVATION_MESSAGES = {
    'level':              'Camera height looks good.',
    'uncertain':          'Height roughly OK — not fully confident.',
    'possibly_elevated':  'Camera may be too high — lower it.',
    'unknown':            'Camera height unclear.',
}
LIVE_MIN_CONFIDENCE = 0.5


def check_camera_setup_frame(frame, landmarker=None):
    """
    Single-frame version of check_camera_setup.py's check_camera_setup() --
    same ok/message/elevation_status decision logic, but on one
    already-decoded live-camera snapshot instead of 3 frames sampled from a
    finished video. Meant to be called repeatedly (every ~1.5s) against a
    persistent model instance (see calibration_server.py) while a player
    positions their camera, trading infer_camera_angle()'s median-of-3
    robustness for speed -- acceptable since the live loop naturally
    resamples on its own cadence anyway.

    Returns the same shape check_camera_setup.py returns: {ok, angle,
    confidence, height_ratio, elevation_status, framing_status, message}.
    """
    result = _angle_from_frame(frame, landmarker)
    if result is None:
        return {
            'ok': False, 'angle': None, 'confidence': 0.0,
            'height_ratio': None, 'elevation_status': 'unknown', 'framing_status': 'unknown',
            'message': "Can't find the net — try stepping back or check the fence-mount guide.",
        }

    (net_width, net_center_x, net_y, player_x, player_vis, post_height_frac, ankle_y,
     used_keypoints, height_ratio, stance_width_ratio, shoulder_tilt_deg) = result

    apparent_ratio = min(net_width / FULL_NET_FRACTION, 1.0)
    angle = math.degrees(math.acos(max(apparent_ratio, 0.001)))
    angle = round(max(0.0, min(90.0, angle)), 1)

    # Hough-fallback base lowered from 0.7 -- this session proved the v4
    # keypoint model (trained on real negatives for the first time) reliably
    # abstains on non-tennis scenes, so a low/no fallback confidence without
    # player-pose corroboration is no longer "no signal," it's a real
    # not-a-net signal on its own. 0.35 alone can't clear LIVE_MIN_CONFIDENCE
    # (0.5); needs player_vis >= ~0.5 (a real player, clearly visible, is in
    # frame) to cross it -- real swing footage always has this, an empty
    # street photo never does. used_keypoints stays at 0.85, untouched.
    base_confidence = 0.85 if used_keypoints else 0.35
    confidence = round(min(base_confidence + player_vis * 0.3, 1.0), 3)

    elevation_status = elevation_label(height_ratio)
    framing_status = framing_label(stance_width_ratio, shoulder_tilt_deg)

    if confidence < LIVE_MIN_CONFIDENCE:
        return {
            'ok': False, 'angle': angle, 'confidence': confidence,
            'height_ratio': height_ratio, 'elevation_status': elevation_status,
            'framing_status': framing_status,
            'message': f'Uncertain ({angle_label(angle)}, low confidence).',
        }

    return {
        'ok': True, 'angle': angle, 'confidence': confidence,
        'height_ratio': height_ratio, 'elevation_status': elevation_status,
        'framing_status': framing_status,
        'message': (
            f'{angle_label(angle)}. {LIVE_ELEVATION_MESSAGES.get(elevation_status, LIVE_ELEVATION_MESSAGES["unknown"])}'
            f'{LIVE_FRAMING_MESSAGES.get(framing_status, "")}'
        ),
    }


def _court_line_fallback_angle(video_path, candidate_frames, view_direction_hint):
    """
    Court-sideline-based angle estimate, used when net detection is either
    known in advance to be useless (view_direction_hint == 'front' -- a
    net-position recording, camera right at/behind the net itself) or
    organically failed on every sampled frame (net absence itself a soft
    "might be a net-position recording" signal, tried even without a hint).

    Kept deliberately low-confidence and separate from the net-based path
    above -- there is no known "recorded from the net" sample footage to
    validate this formula against yet, and this file has repeatedly learned
    the lesson that a reasonable-looking geometric threshold can fail on
    real data (see project_vertical_angle_detection memory). Confidence is
    capped well below check_camera_setup.py's MIN_CONFIDENCE (0.5) so a
    court-line reading always surfaces as "uncertain" advisory, never a
    false confident "ok."

    Returns (angle_deg, confidence, debug) or (None, 0.0, reason_str).
    """
    court_angles = []
    for fn in candidate_frames:
        try:
            frame = extract_frame(video_path, fn)
        except RuntimeError:
            # cap.get(CAP_PROP_FRAME_COUNT) can overstate a real-world
            # phone-recorded/VFR video's actual decodable frame count, so a
            # candidate frame index clamped against it can still fail to
            # read. Treated the same as "no sidelines found on this frame"
            # rather than aborting the whole fallback for one bad sample.
            continue
        sidelines = detect_court_sidelines(frame)
        if sidelines is None:
            continue
        left_angle_deg, right_angle_deg = sidelines
        if left_angle_deg <= 0 or right_angle_deg <= 0:
            continue  # not a sane converging pair -- skip rather than trust noise
        angle_est = angle_from_sideline_symmetry(left_angle_deg, right_angle_deg)
        if angle_est is not None:
            court_angles.append(angle_est)

    if not court_angles:
        reason = ('Net not expected (front-position hint) and court sidelines not detected'
                   if view_direction_hint == 'front' else
                   'Net not detected in any sampled frame, and court-sidelines fallback also failed')
        return None, 0.0, reason

    court_angles.sort()
    median_angle = court_angles[len(court_angles) // 2]
    confidence = round(min(0.3, 0.15 + 0.05 * len(court_angles)), 3)
    debug = {
        'net_detection_method': 'court_lines',
        'view_direction_hint': view_direction_hint,
        'court_line_angle_samples': court_angles,
    }
    return median_angle, confidence, debug


def infer_camera_angle(video_path, frame_number=None, landmarker=None, view_direction_hint=None):
    """
    Returns (angle_deg, confidence, debug_info) or (None, 0, reason_str).

    angle_deg:  0° = front view, 90° = pure side view
    confidence: 0-1
    landmarker: optional pre-created PoseLandmarker for batch processing.
                If None, a temporary landmarker is created and destroyed per call.
    view_direction_hint: 'front'|'back'|None, the record-time filming-
                position picker's answer (see ContactMarkingScreen.js). When
                'front' (camera at the net), net-based detection is skipped
                entirely -- the net is right at/behind the camera, not a
                usable foreshortened line -- in favor of _court_line_
                fallback_angle() below. Otherwise unused unless net
                detection organically fails (see below).

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
    if view_direction_hint != 'front':
        for fn in candidate_frames:
            try:
                frame = extract_frame(video_path, fn)
            except RuntimeError:
                # Same as the court-line fallback below: cap.get() reports a
                # frame count the decoder can't always honour, so one
                # candidate frame failing to read shouldn't crash the whole
                # comparison (previously did -- see compare_swing.py's call
                # site, which otherwise treats "no measurements" as a normal,
                # gracefully-handled outcome).
                continue
            result = _angle_from_frame(frame, landmarker)
            if result is not None:
                measurements.append(result)

    if not measurements:
        # Either the net attempt was skipped entirely (front-position hint)
        # or it ran and found nothing on every sampled frame -- either way,
        # try the court-sideline fallback before giving up.
        return _court_line_fallback_angle(video_path, candidate_frames, view_direction_hint)

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
    (net_width, net_center_x, net_y, player_x, player_vis, post_height_frac, ankle_y,
     used_keypoints, _, stance_width_ratio, shoulder_tilt_deg) = best
    n_keypoint_frames = sum(1 for m in measurements if m[7])

    # Vertical elevation: median height_ratio across whichever sampled frames
    # got one (keypoint-model frames with a detected post base), not just the
    # `best` frame -- more robust than relying on a single sample.
    height_ratios = sorted(m[8] for m in measurements if m[8] is not None)
    median_height_ratio = height_ratios[len(height_ratios) // 2] if height_ratios else None

    # Stance/tilt: same "closest-to-median-net-width" frame's values as the
    # rest of `best` -- these two are read straight from the player's own
    # pose in that one frame, not medianed across samples like height_ratio.

    debug = {
        'frames_sampled':  candidate_frames,
        'net_widths':      [round(w, 3) for w in net_widths],
        'median_width':    round(median_width, 3),
        'width_spread':    round(width_spread, 3),
        'player_x':        round(player_x, 3) if player_x is not None else None,
        'player_vis':      round(player_vis, 3),
        'net_detection_method': 'keypoint_model' if used_keypoints else 'hough_heuristic',
        'net_keypoint_frames':  f'{n_keypoint_frames}/{len(measurements)}',
        'net': {
            'width':    round(net_width, 3),
            'center_x': round(net_center_x, 3),
            'y':        round(net_y, 3),
        },
        # height_ratio/elevation_status: the validated keypoint-model-based
        # vertical signal (see height_ratio_from_keypoints docstring for
        # calibration caveats -- only 2 known-elevated reference videos).
        # post_height_frac/ankle_y below are the older raw Hough-based signal,
        # kept for continuity/debugging, not used for elevation_status.
        'height_ratio':      round(median_height_ratio, 4) if median_height_ratio is not None else None,
        'elevation_status':  elevation_label(median_height_ratio),
        'post_height_frac': round(post_height_frac, 4) if post_height_frac is not None else None,
        'ankle_y':           round(ankle_y, 4) if ankle_y is not None else None,
        'elevation_gap':     round(ankle_y - net_y, 4) if ankle_y is not None else None,
        'stance_width_ratio': stance_width_ratio,
        'shoulder_tilt_deg':  shoulder_tilt_deg,
        'framing_status':     framing_label(stance_width_ratio, shoulder_tilt_deg),
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

    # Confidence: net detected consistently (penalty for high spread).
    # Higher base when the keypoint model found the net directly -- validated
    # this session as much more reliable than the Hough-line fallback, which
    # frequently locks onto backdrop boards (or, proven this session, street
    # furniture/rooflines on non-tennis footage) instead of the net.
    #
    # Fallback base lowered 0.7 -> 0.35 this session: the v4 keypoint model
    # (first ever trained on real negative/no-net examples) was validated to
    # reliably abstain on non-tennis scenes rather than guess, so when it's
    # the Hough fallback firing instead, that's a weaker signal than it used
    # to be treated as. 0.35 alone can't clear MIN_CONFIDENCE (0.5) in
    # check_camera_setup.py; needs real player-pose corroboration
    # (player_vis >= ~0.5) to cross it -- present in any genuine swing video,
    # absent in a street photo with no player in frame.
    base_confidence = 0.85 if used_keypoints else 0.35
    spread_penalty = min(width_spread / 0.2, 0.3)
    confidence = round(min(base_confidence - spread_penalty + player_vis * 0.3, 1.0), 3)

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
    (net_width, net_center_x, net_y, player_x, player_vis, post_height_frac, ankle_y,
     used_keypoints, _, _stance_width_ratio, _shoulder_tilt_deg) = best
    height_ratios = sorted(m[8] for m in measurements if m[8] is not None)
    median_height_ratio = height_ratios[len(height_ratios) // 2] if height_ratios else None

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
    base_confidence = 0.75 if used_keypoints else 0.6
    confidence = round(min(base_confidence - spread_penalty + player_vis * 0.25, 1.0), 3)

    debug = {
        'source': source_video_path,
        'peak_time_sec': peak_time_sec,
        'frames_sampled': candidate_frames,
        'net_widths': [round(w, 3) for w in net_widths],
        'median_width': round(median_width, 3),
        'net_angle': round(net_angle, 1),
        'net_detection_method': 'keypoint_model' if used_keypoints else 'hough_heuristic',
        'angle_final': angle_deg,
        'height_ratio':      round(median_height_ratio, 4) if median_height_ratio is not None else None,
        'elevation_status':  elevation_label(median_height_ratio),
        'post_height_frac': round(post_height_frac, 4) if post_height_frac is not None else None,
        'ankle_y':           round(ankle_y, 4) if ankle_y is not None else None,
        'elevation_gap':     round(ankle_y - net_y, 4) if ankle_y is not None else None,
    }

    return angle_deg, confidence, debug


# ── Label helpers ─────────────────────────────────────────────────────────────

def angle_label(angle):
    if angle is None:    return 'Unknown'
    if angle < 20:       return 'Front view'
    if angle < 40:       return 'Semi-front'
    if angle < 60:       return 'Diagonal (ideal)'
    if angle < 75:       return 'Semi-side'
    return 'Side view'


# Thresholds from this session's live-model validation: pro-clip height_ratio
# mean ~0.074, known-elevated mean ~0.051 (~32% gap). Bands are intentionally
# conservative/wide given the elevated group is only 2 real source videos --
# 'uncertain' covers the overlap zone rather than forcing a confident call.
ELEVATION_LEVEL_MIN = 0.065
ELEVATION_LOW_MAX = 0.050


# Provisional thresholds for the new pose-geometry framing check -- see
# this module's spot-check script/comment for what real footage was
# actually measured before these were set (same discipline as
# ELEVATION_LEVEL_MIN/ELEVATION_LOW_MAX above: don't trust an ungrounded
# geometric threshold, this session already found three that looked
# reasonable and failed on real data). Deliberately wide/conservative --
# only flags a clearly-off frame, not a borderline one.
STANCE_WIDTH_RATIO_LOW = 0.30   # hip-width / shoulder-width below this -- stance reads unusually compressed
SHOULDER_TILT_MAX_DEG = 15.0    # shoulder line more than this many degrees off horizontal


def framing_label(stance_width_ratio, shoulder_tilt_deg):
    """
    Supplementary signal to elevation_label() -- flags likely camera
    perpendicularity/tilt issues from the player's own pose geometry
    (shoulders/hips), independent of the net-based angle/elevation checks.
    Returns 'unknown' | 'ok' | 'tilted' | 'compressed_stance'. Checks tilt
    first since a canted camera is the more actionable, unambiguous fix.
    """
    if stance_width_ratio is None and shoulder_tilt_deg is None:
        return 'unknown'
    if shoulder_tilt_deg is not None and shoulder_tilt_deg > SHOULDER_TILT_MAX_DEG:
        return 'tilted'
    if stance_width_ratio is not None and stance_width_ratio < STANCE_WIDTH_RATIO_LOW:
        return 'compressed_stance'
    return 'ok'


def elevation_label(height_ratio):
    if height_ratio is None:
        return 'unknown'
    if height_ratio >= ELEVATION_LEVEL_MIN:
        return 'level'
    if height_ratio < ELEVATION_LOW_MAX:
        return 'possibly_elevated'
    return 'uncertain'


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
