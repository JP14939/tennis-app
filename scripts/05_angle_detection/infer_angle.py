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
# Hand-set from broadcast tennis footage (~80% head-on) -- NEVER data-tuned.
# There is no data-free way to improve it; scripts/10_net_detection/
# calibrate_full_net_fraction.py fits it once 0c fence footage with coarse
# known angles exists (Section 8 item 5). If it changes, that is one atomic
# commit: VIEW_GATE_SIDE_ON_ANGLE_DEG, ball_speed.MIN_RELIABLE_ANGLE_DEG,
# angle_label buckets, and a full pro-DB re-enrich all move with it.
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

# v10 (2026-09-08): 2-keypoint (net_top_left/right only, no post bases),
# retrained with amateur data. 87% test recall / 59% held-out amateur vs v4's
# 21% on amateur. A/B revert to v4 is this one path + NET_KEYPOINT_NAMES below.
NET_KEYPOINT_MODEL_PATH = os.path.join(DATA_DIR, '10_net_detection', 'yolo_pose_run_v10', 'weights', 'best.pt')
NET_KEYPOINT_IMGSZ = 640  # matches yolo_pose_run_v10/args.yaml -- passed explicitly so predict() doesn't guess
# 0.5 (was 0.4 for v4): v10 is ~8% FP on non-tennis footage vs v4's 0%. The
# lone-keypoint FP is further gated downstream by MIN_CONFIDENCE requiring a
# corroborating player pose; residual FP is noted for a v11 retrain.
NET_KEYPOINT_CONF_MIN = 0.5
_net_kp_model = None


def _get_net_kp_model():
    global _net_kp_model
    if _net_kp_model is None:
        from ultralytics import YOLO
        _net_kp_model = YOLO(NET_KEYPOINT_MODEL_PATH)
    return _net_kp_model


# v10 is 2-keypoint. The two post-base names are kept in the list (commented)
# so an A/B revert to the 4-kpt v4 checkpoint is a one-line change; the loop in
# run_net_keypoint_model slices to whatever the loaded checkpoint actually emits.
NET_KEYPOINT_NAMES = ['net_top_left', 'net_top_right']  # + 'left_post_base', 'right_post_base' for v4


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
    dict -- callers must check membership, not assume every key exists. The
    loop slices NET_KEYPOINT_NAMES to the checkpoint's actual keypoint count,
    so a 2-kpt (v10) or 4-kpt (v4) model both work unchanged.
    """
    h, w = frame.shape[:2]
    model = _get_net_kp_model()
    results = model.predict(frame, verbose=False, imgsz=NET_KEYPOINT_IMGSZ)
    if len(results[0].keypoints) == 0 or results[0].keypoints.xy.shape[1] == 0:
        return {}

    kpts = results[0].keypoints.xy[0].cpu().numpy()
    confs = results[0].keypoints.conf[0].cpu().numpy() if results[0].keypoints.conf is not None else None

    out = {}
    for i, name in enumerate(NET_KEYPOINT_NAMES[:kpts.shape[0]]):
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


def net_roll_deg(kp):
    """
    In-plane camera roll (tilt about the optical axis), in degrees, from the
    slope of the net's top cord -- a physically horizontal line, so any
    apparent slope in the image is the camera being canted. Positive follows
    image coords (y down): the net's right end sitting lower than its left
    reads as a positive angle.

    `kp` is run_net_keypoint_model()'s dict. Returns None unless BOTH
    net_top_left and net_top_right were detected -- this is a pure
    left-to-right slope measurement, a single post base can't provide it.
    """
    if 'net_top_left' not in kp or 'net_top_right' not in kp:
        return None
    (lx, ly), (rx, ry) = kp['net_top_left'], kp['net_top_right']
    if rx == lx and ry == ly:
        return None
    # Order by x so "right end lower -> positive" holds regardless of which
    # keypoint the model labelled left/right on a heavily canted frame.
    if lx > rx:
        (lx, ly), (rx, ry) = (rx, ry), (lx, ly)
    return math.degrees(math.atan2(ry - ly, rx - lx))


# Roll-correction band, shared by compare_swing.py (user side) and
# enrich_pro_camera_roll.py (pro database). Below MIN it's within
# net-keypoint noise and not worth rotating; above MAX it's more likely a
# bad detection or a genuine phone-orientation problem than a slightly
# tilted mount, and silently rotating it away would hide that.
ROLL_CORRECTION_MIN_DEG = 3.0
ROLL_CORRECTION_MAX_DEG = 25.0


def usable_roll(roll_deg):
    """Return roll_deg when it's in the correctable band, else None."""
    if roll_deg is None:
        return None
    if ROLL_CORRECTION_MIN_DEG <= abs(roll_deg) <= ROLL_CORRECTION_MAX_DEG:
        return roll_deg
    return None


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
    ankle_y, used_keypoints, height_ratio, stance_width_ratio, shoulder_tilt_deg,
    net_roll) or None if net not found.

    net_roll is the in-plane camera-roll angle from the net-cord slope (deg,
    see net_roll_deg()), only available when used_keypoints is True; None
    otherwise. Appended at the end for the same positional-unpacking reason
    stance_width_ratio/shoulder_tilt_deg were.
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
    # Elevation retired (Section 8 item 2): v10 has no post-base keypoints, so
    # height_ratio_from_keypoints() would always be None anyway. The signal was
    # only ever validated on 2 videos with synthetic labels -- dropped, not
    # resurrected via Hough (project_vertical_angle_detection scar tissue).
    # Tuple slot kept so positional unpacking elsewhere doesn't shift.
    height_ratio = None
    net_roll = net_roll_deg(kp) if used_keypoints else None

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
            used_keypoints, height_ratio, stance_width_ratio, shoulder_tilt_deg, net_roll)


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


# --- Behind-the-baseline view gate (roadmap 1a) --------------------------------
# A single "is this a usable behind-baseline setup?" verdict, computed the same
# way for a finished upload (compare_swing.py) and a live snapshot
# (check_camera_setup_frame). v1 only supports the behind-baseline view; today
# an unsupported view is silently scored against the whole pro pool. Advisory
# for now (compare_swing keeps matching) -- promoted to a hard reject via
# RALLYMAX_ENFORCE_VIEW_GATE once VIEW_GATE_* is tuned on labelled footage
# (1a-val). 'unknown' view alone does NOT fail: detect_view_direction() is
# unreliable and the record-time picker hint is the tie-breaker.
VIEW_GATE_SIDE_ON_ANGLE_DEG = 78.0   # >= this ~= angle_label "Side view" -- no usable court depth
# 0.45 (was 0.25): re-tuned on the Section 8 item 3 confidence distribution
# (scripts/10_net_detection/eval_view_gate_conf.py). On net_keypoint_testset_v1
# via the single-frame path, no-net frames cluster at 0.35 (Hough base, no
# player) and has-net frames at >=0.85 -- 0.45 rejects ~88% of no-net while
# keeping ~92% of has-net, and lines up with
# compare_swing.ANGLE_FILTER_MIN_CONF (D12: keep them unified). Front / side-on
# behind-baseline buckets are handled by the view_direction / SIDE_ON rules,
# not this one; the 0c-footage 1a-val pass revisits the absolute number.
VIEW_GATE_MIN_ANGLE_CONF    = 0.45

# Launch input-domain restriction (2026-09-09): the app only accepts footage shot
# from behind the baseline with the WHOLE net in frame. A post within this
# fraction of a frame edge counts as truncated (net running out of shot = camera
# too close to one tramline / too angled); at least this fraction of the trained
# keypoint frames must show both posts inside the margins.
NET_POST_EDGE_MARGIN   = 0.03
POSTS_INFRAME_MIN_FRAC  = 0.5

# reasons that hard-reject an upload (severity 'block') vs. only warn ('warn').
# angle_unreliable warns rather than blocks: it fires on "player not clearly
# visible in the sampled frames", which would false-reject otherwise-fine
# behind-baseline footage (~12% on the Section 8 item 8 distribution).
VIEW_GATE_BLOCK_REASONS = {'front_view', 'side_on', 'net_not_found', 'net_truncated'}

# Full-length copy for the results banner / post-pick check.
VIEW_GATE_MESSAGES = {
    'front_view':       'This looks filmed from the net. Stand behind the baseline fence so the camera sees your back.',
    'side_on':          'This looks filmed side-on. Move around behind the baseline so the camera looks down the court.',
    'angle_unreliable': "We couldn't read the court angle clearly -- check the fence-mount guide and try again.",
    'net_not_found':    "We couldn't find the net. Film from behind the baseline with the whole net in view.",
    'net_truncated':    'The net runs out of the frame -- move back behind the baseline so both net posts are visible.',
}
# Shorter copy for the live positioning badge (tight UI), same signal.
VIEW_GATE_LIVE_MESSAGES = {
    'front_view':       'Filmed from the net -- move behind the baseline fence.',
    'side_on':          'Too side-on -- move behind the baseline.',
    'angle_unreliable': "Can't read the court angle -- see the fence-mount guide.",
    'net_not_found':    "Can't find the net -- get the whole net in shot from behind the baseline.",
    'net_truncated':    'Net is cut off -- step back so both posts are visible.',
}


def evaluate_view_usable(view_direction, angle_deg, angle_conf, *, net_debug=None):
    """
    Decide whether a camera setup is a usable behind-the-baseline view.

    Returns {'usable': bool, 'reason': str|None, 'severity': 'ok'|'warn'|'block',
             'message': str|None} where reason is one of None, 'front_view',
             'side_on', 'angle_unreliable', 'net_not_found', 'net_truncated'.
    First failing rule wins.

    net_debug: the infer_camera_angle() debug dict (or a 2-key dict on the live
    single-frame path -- 'net_detection_method' + 'posts_inframe_frac'). When
    None the net-geometry rules are skipped, so callers that can't supply it
    (and the 3-arg unit tests) keep the pre-2026-09-09 behaviour.

    severity 'block' reasons hard-reject an upload (VIEW_GATE_BLOCK_REASONS);
    'warn' rides along in the result for a frontend banner but still scores.
    """
    reason = None
    if view_direction == 'front':
        reason = 'front_view'
    elif net_debug is not None and net_debug.get('net_detection_method') != 'keypoint_model':
        reason = 'net_not_found'
    elif net_debug is not None and net_debug.get('posts_inframe_frac', 1.0) < POSTS_INFRAME_MIN_FRAC:
        reason = 'net_truncated'
    elif angle_deg is not None and angle_deg >= VIEW_GATE_SIDE_ON_ANGLE_DEG:
        reason = 'side_on'
    elif (angle_deg is not None and angle_conf is not None
          and angle_conf < VIEW_GATE_MIN_ANGLE_CONF):
        reason = 'angle_unreliable'

    if reason is None:
        return {'usable': True, 'reason': None, 'severity': 'ok', 'message': None}
    severity = 'block' if reason in VIEW_GATE_BLOCK_REASONS else 'warn'
    return {'usable': False, 'reason': reason, 'severity': severity,
            'message': VIEW_GATE_MESSAGES[reason]}


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

# Elevation retired (Section 8 item 2): the live badge no longer shows a
# camera-height clause (elevation_status is always 'unknown' now). Dict kept
# only so nothing importing it breaks.
LIVE_ELEVATION_MESSAGES = {
    'level':              '',
    'uncertain':          '',
    'possibly_elevated':  '',
    'unknown':            '',
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
            'view_direction': 'unknown', 'view_reason': 'net_not_found', 'view_severity': 'block',
            'message': "Can't find the net — try stepping back or check the fence-mount guide.",
        }

    (net_width, net_center_x, net_y, player_x, player_vis, post_height_frac, ankle_y,
     used_keypoints, _height_ratio, stance_width_ratio, shoulder_tilt_deg, _net_roll) = result

    # Single-frame equivalent of _aggregate_frame_angles' posts_inframe_frac:
    # is the whole net in shot, or is a post at the frame edge?
    left_x, right_x = net_center_x - net_width / 2, net_center_x + net_width / 2
    posts_inframe = (left_x > NET_POST_EDGE_MARGIN and right_x < 1 - NET_POST_EDGE_MARGIN)
    frame_net_debug = {
        'net_detection_method': 'keypoint_model' if used_keypoints else 'hough_heuristic',
        'posts_inframe_frac': 1.0 if posts_inframe else 0.0,
    }

    # Same acos + player-offset formula as the finished-video path -- via the
    # shared helper (Section 8 item 3), so this is no longer a divergent copy.
    angle = _angle_from_measurement(result)[0]

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

    # Elevation retired (Section 8 item 2) -- always None / 'unknown'.
    height_ratio = None
    elevation_status = 'unknown'
    framing_status = framing_label(stance_width_ratio, shoulder_tilt_deg)

    # Behind-the-baseline view gate -- same verdict compare_swing.py applies to
    # a finished upload, so the live badge warns about a wrong-side setup
    # before the user records rather than after they get their result.
    try:
        view_direction = detect_view_direction(frame, landmarker=landmarker)
    except Exception:
        view_direction = 'unknown'
    view_gate = evaluate_view_usable(view_direction, angle, confidence, net_debug=frame_net_debug)

    if confidence < LIVE_MIN_CONFIDENCE:
        return {
            'ok': False, 'angle': angle, 'confidence': confidence,
            'height_ratio': height_ratio, 'elevation_status': elevation_status,
            'framing_status': framing_status,
            'view_direction': view_direction, 'view_reason': view_gate['reason'],
            'view_severity': view_gate['severity'] if not view_gate['usable'] else 'warn',
            'message': f'Uncertain ({angle_label(angle)}, low confidence).',
        }

    if not view_gate['usable']:
        return {
            'ok': False, 'angle': angle, 'confidence': confidence,
            'height_ratio': height_ratio, 'elevation_status': elevation_status,
            'framing_status': framing_status,
            'view_direction': view_direction, 'view_reason': view_gate['reason'],
            'view_severity': view_gate['severity'],
            'message': VIEW_GATE_LIVE_MESSAGES[view_gate['reason']],
        }

    return {
        'ok': True, 'angle': angle, 'confidence': confidence,
        'height_ratio': height_ratio, 'elevation_status': elevation_status,
        'framing_status': framing_status,
        'view_direction': view_direction, 'view_reason': None, 'view_severity': 'ok',
        'message': (
            f'{angle_label(angle)}.'
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
        # Same undecodable-frame guard as infer_camera_angle()'s net-detection
        # loop above -- one bad frame shouldn't abort the whole fallback,
        # especially since this path runs on every 'front' (net-position)
        # recording, not just as a rare failure mode.
        try:
            frame = extract_frame(video_path, fn)
        except RuntimeError:
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


def _angle_from_measurement(m):
    """
    Camera angle (deg, 0 = front, 90 = pure side) from ONE frame's
    _angle_from_frame() tuple. This is the exact legacy formula -- net
    foreshortening via acos(net_width / FULL_NET_FRACTION), an optional player-
    offset secondary via asin(offset / 0.40), weighted average (net 2.0 /
    player player_vis). Extracted verbatim (Section 8 item 3) so
    check_camera_setup_frame() consumes the same helper instead of keeping a
    divergent inline copy of it.

    Returns (angle_deg, net_angle, player_angle | None).
    """
    net_width, net_center_x = m[0], m[1]
    player_x, player_vis = m[3], m[4]

    apparent_ratio = min(net_width / FULL_NET_FRACTION, 1.0)
    net_angle = max(0.0, min(90.0, math.degrees(math.acos(max(apparent_ratio, 0.001)))))

    player_angle = None
    if player_x is not None:
        offset_ratio = min(abs(player_x - net_center_x) / 0.40, 1.0)
        player_angle = max(0.0, min(90.0, math.degrees(math.asin(offset_ratio))))

    net_weight = 2.0
    player_weight = player_vis if player_angle is not None else 0.0
    if player_angle is not None and player_weight > 0:
        angle = (net_angle * net_weight + player_angle * player_weight) / (net_weight + player_weight)
    else:
        angle = net_angle
    return round(max(0.0, min(90.0, angle)), 1), round(net_angle, 1), (
        round(player_angle, 1) if player_angle is not None else None)


def _aggregate_frame_angles(measurements, *, kp_base=0.85, hough_base=0.35,
                            player_vis_weight=0.3):
    """
    Shared 5-frame aggregation for infer_camera_angle / infer_angle_from_source
    (Section 8 item 3). Was: median of net_widths -> angle from the single frame
    closest to that median. Now: an angle per frame, then the median of the
    per-frame angles, with a confidence that reflects how much of the answer
    came from the trusted keypoint model vs the Hough fallback.

    Returns a dict:
      {'ok', 'reason', 'angle', 'confidence', 'n_keypoint_frames', 'debug'}
    ok=False means the net path did not produce a usable answer -- 'reason' is
    a banner-false-positive message or 'net_path_insufficient' (< 2 keypoint
    frames); the caller picks the fallback (court sidelines / give up). 'angle'
    is still filled on 'net_path_insufficient' for debug logging.
    """
    net_widths = [m[0] for m in measurements]
    median_width = sorted(net_widths)[len(net_widths) // 2]
    width_spread = max(net_widths) - min(net_widths)

    agg_debug = {
        'net_widths':   [round(w, 3) for w in net_widths],
        'median_width': round(median_width, 3),
        'width_spread': round(width_spread, 3),
    }

    # Banner false-positive: every frame found a suspiciously wide, suspiciously
    # consistent line (the same backdrop banner in each sample).
    if median_width > 0.72 and width_spread < 0.05:
        return {'ok': False,
                'reason': f'Net detection unreliable: consistent wide line (w={median_width:.2f}) likely a banner',
                'angle': None, 'confidence': 0.0, 'n_keypoint_frames': 0, 'debug': agg_debug}

    n_keypoint_frames = sum(1 for m in measurements if m[7])
    kp_frac = n_keypoint_frames / len(measurements)

    per_frame = [(_angle_from_measurement(m)[0], m) for m in measurements]
    # A Hough banner-line angle mixed into the median is pure noise -- once we
    # have >= 3 real keypoint frames, drop the Hough ones from the vote.
    if n_keypoint_frames >= 3:
        chosen = [a for a, m in per_frame if m[7]]
    else:
        chosen = [a for a, _ in per_frame]
    chosen_sorted = sorted(chosen)
    median_angle = chosen_sorted[len(chosen_sorted) // 2]
    angle_spread = max(chosen) - min(chosen)

    # Secondary signals read from the frame closest to the median net width
    # (the legacy "best" frame): player visibility feeds both the confidence
    # bump and -- historically -- the offset term already folded into per-frame.
    best = min(measurements, key=lambda m: abs(m[0] - median_width))
    player_vis = best[4]

    # Launch view gate: on the trained-keypoint frames, is the whole net (both
    # posts) inside the frame, or is a post running off the edge? left/right post
    # x reconstructed from center +/- width/2 (both already normalised [0,1]).
    kp_meas = [m for m in measurements if m[7]]
    posts_inframe = sum(
        1 for m in kp_meas
        if (m[1] - m[0] / 2) > NET_POST_EDGE_MARGIN
        and (m[1] + m[0] / 2) < 1 - NET_POST_EDGE_MARGIN)
    posts_inframe_frac = round(posts_inframe / len(kp_meas), 2) if kp_meas else 0.0

    agg_debug.update({
        'net_keypoint_frames': f'{n_keypoint_frames}/{len(measurements)}',
        'posts_inframe_frac':  posts_inframe_frac,
        'kp_frac':             round(kp_frac, 2),
        'per_frame_angles':    [round(a, 1) for a, _ in per_frame],
        'angle_spread':        round(angle_spread, 1),
        'angle_median':        round(median_angle, 1),
        'player_vis':          round(player_vis, 3),
    })

    # The net path only counts as "produced a usable answer" with >= 2 real
    # keypoint frames. Below that the caller falls back to court sidelines.
    if n_keypoint_frames < 2:
        return {'ok': False, 'reason': 'net_path_insufficient',
                'angle': round(median_angle, 1), 'confidence': 0.0,
                'n_keypoint_frames': n_keypoint_frames, 'debug': agg_debug}

    base = kp_base * kp_frac + hough_base * (1 - kp_frac)
    confidence = base - min(angle_spread / 20.0, 0.3) + player_vis * player_vis_weight
    confidence = round(max(0.0, min(1.0, confidence)), 3)

    return {'ok': True, 'reason': None,
            'angle': round(max(0.0, min(90.0, median_angle)), 1),
            'confidence': confidence,
            'n_keypoint_frames': n_keypoint_frames, 'debug': agg_debug}


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

    # Sample 5 candidate frames (Section 8 item 3): anchored around the
    # caller's frame if given, else spread across the clip.
    if frame_number is not None:
        candidate_frames = [max(0, min(frame_number + int(total * f), total - 1))
                            for f in (-0.15, -0.075, 0.0, 0.075, 0.15)]
    else:
        candidate_frames = [int(total * q) for q in (0.2, 0.35, 0.5, 0.65, 0.8)]

    measurements = []
    if view_direction_hint != 'front':
        for fn in candidate_frames:
            # extract_frame() raises when cap.read() fails on a clamped-but-
            # undecodable frame (common on phone/VFR video). Skip it rather
            # than abort the whole detection, same as a no-net frame below.
            try:
                frame = extract_frame(video_path, fn)
            except RuntimeError:
                continue
            result = _angle_from_frame(frame, landmarker)
            if result is not None:
                measurements.append(result)

    if not measurements:
        # Either the net attempt was skipped entirely (front-position hint)
        # or it ran and found nothing on every sampled frame -- either way,
        # try the court-sideline fallback before giving up.
        return _court_line_fallback_angle(video_path, candidate_frames, view_direction_hint)

    agg = _aggregate_frame_angles(measurements)

    # Banner false-positive -- give up (unchanged behaviour).
    if not agg['ok'] and agg['reason'] != 'net_path_insufficient':
        return None, 0.0, agg['reason']

    # < 2 keypoint frames: the net path isn't trustworthy on its own. Try the
    # court-sideline fallback (unless the front hint already ruled the net out).
    if not agg['ok']:
        fb_angle, fb_conf, fb_debug = _court_line_fallback_angle(
            video_path, candidate_frames, view_direction_hint)
        if fb_angle is not None:
            if isinstance(fb_debug, dict):
                fb_debug['net_path'] = agg['debug']
            return fb_angle, fb_conf, fb_debug
        # Court lines failed too -- fall through to the low-confidence net-path
        # median (confidence 0.0 from the aggregation flags it as a guess).

    # Assemble the full debug dict. Roll / framing / net geometry are read from
    # the measurements; the angle + confidence come from the aggregation.
    median_width = agg['debug']['median_width']
    best = min(measurements, key=lambda m: abs(m[0] - median_width))
    (net_width, net_center_x, net_y, player_x, player_vis, _post_height_frac, _ankle_y,
     used_keypoints, _, stance_width_ratio, shoulder_tilt_deg, _net_roll) = best
    roll_samples = sorted(m[11] for m in measurements if m[11] is not None)
    median_roll = roll_samples[len(roll_samples) // 2] if roll_samples else None

    angle_deg = agg['angle']
    confidence = agg['confidence']

    debug = {
        'frames_sampled':  candidate_frames,
        'player_x':        round(player_x, 3) if player_x is not None else None,
        'net_detection_method': 'keypoint_model' if used_keypoints else 'hough_heuristic',
        'net': {
            'width':    round(net_width, 3),
            'center_x': round(net_center_x, 3),
            'y':        round(net_y, 3),
        },
        # Elevation retired (Section 8 item 2): the v10 net model has no
        # post-base keypoints, so this signal is permanently None / 'unknown'.
        # Keys kept so downstream readers and the pro-DB schema don't need a
        # coordinated change. NOT resurrected via a Hough post-height fallback
        # (project_vertical_angle_detection: every such attempt failed on real data).
        'height_ratio':      None,
        'elevation_status':  'unknown',
        'stance_width_ratio': stance_width_ratio,
        'shoulder_tilt_deg':  shoulder_tilt_deg,
        'framing_status':     framing_label(stance_width_ratio, shoulder_tilt_deg),
        # In-plane camera roll from the net-cord slope (deg). None when no
        # keypoint-model frame yielded both net-top points. Consumed by
        # compare_swing.py (user side) and enrich_pro_camera_roll.py to
        # rotate trajectories level before DTW -- see usable_roll().
        'camera_roll_deg':    round(median_roll, 1) if median_roll is not None else None,
        'camera_roll_source': 'net_keypoints' if median_roll is not None else None,
        'angle_final':        angle_deg,
    }
    debug.update(agg['debug'])

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

    # Same 5-frame aggregation as infer_camera_angle (Section 8 item 3), but
    # keeping this path's lower confidence bases -- source frames sit further
    # from the swing than the clip's own frames do.
    agg = _aggregate_frame_angles(measurements, kp_base=0.75, hough_base=0.6,
                                  player_vis_weight=0.25)
    if not agg['ok'] and agg['reason'] != 'net_path_insufficient':
        return None, 0.0, agg['reason'].replace('Net detection unreliable',
                                                'Source video detection unreliable')
    if not agg['ok']:
        # No court-sideline fallback on the source path -- give up.
        return None, 0.0, 'Net not reliably detected in source video frames around swing'

    median_width = agg['debug']['median_width']
    best = min(measurements, key=lambda m: abs(m[0] - median_width))
    (net_width, net_center_x, net_y, player_x, player_vis, _post_height_frac, _ankle_y,
     used_keypoints, _, _stance_width_ratio, _shoulder_tilt_deg, _net_roll) = best
    roll_samples = sorted(m[11] for m in measurements if m[11] is not None)
    median_roll = roll_samples[len(roll_samples) // 2] if roll_samples else None

    angle_deg = agg['angle']
    confidence = agg['confidence']

    debug = {
        'source': source_video_path,
        'peak_time_sec': peak_time_sec,
        'frames_sampled': candidate_frames,
        'net_detection_method': 'keypoint_model' if used_keypoints else 'hough_heuristic',
        'angle_final': angle_deg,
        # Elevation retired (Section 8 item 2) -- see infer_camera_angle.
        'height_ratio':      None,
        'elevation_status':  'unknown',
        'net': {
            'width':    round(net_width, 3),
            'center_x': round(net_center_x, 3),
            'y':        round(net_y, 3),
        },
        'camera_roll_deg':    round(median_roll, 1) if median_roll is not None else None,
        'camera_roll_source': 'net_keypoints' if median_roll is not None else None,
    }
    debug.update(agg['debug'])

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
