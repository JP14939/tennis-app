"""
Ball speed at the net crossing -- v2 (lateral + radial).

No pixel-to-real-world scale/homography exists anywhere in this codebase.
The net is the one object of known real-world size the pipeline already
detects reliably (infer_angle.py's trained net-keypoint model), so this
uses the net's own pixel span at the moment of contact as a local scale, and
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
correction.

v1 rejected the whole estimate below MIN_RELIABLE_ANGLE_DEG (30deg),
reasoning that low camera angle meant a foreshortened, untrustworthy net
scale. That reasoning had it backwards: low angle_deg means MORE of the
net's true width is visible (less foreshortened, per _angle_from_measurement
in infer_angle.py), so the scale itself is fine there. The real problem is
that at low angle (the encouraged, view-gate-approved dead-centre
behind-the-baseline framing -- see evaluate_view_usable, which passes
view_direction=='back' at any angle below the separate 78deg side_on cutoff)
the ball's real flight toward/away from the far net is mostly RADIAL --
along the camera's optical axis -- and barely moves the ball's (x, y) pixel
position frame to frame. A lateral pixel-velocity estimate alone reads close
to zero real signal there, which is what v1 was actually (rightly)
distrusting, just for the wrong stated reason.

v2 adds a second, independent signal for exactly that missing radial
component: the ball's apparent size (bounding-box diameter) shrinks/grows
in inverse proportion to its distance from the camera as it approaches/
recedes, which is strongest exactly where the lateral signal is weakest.
A focal length turns that size-derivative into a radial speed the same way
the net's known width turns lateral pixel motion into a lateral speed, and
the two are combined as the (roughly orthogonal) transverse and depth
components of one 3D velocity. Neither component is individually gated on
camera_angle_deg any more -- each is naturally small where its underlying
real motion is small, so the Pythagorean combination self-weights across
the whole accepted framing range without needing an explicit angle-based
cutoff.

v2.1 (2026-09-11, same session) fixes the radial term's weakest assumption.
Focal length can't be measured from a single video the way the net-width
scale can (no known-size object at a known distance is visible), so v2
approximated it from an ASSUMED camera-to-NET distance -- but that's a
*setup* property (how far back this particular user stood) that varies
hugely between users, unlike focal length itself, which is a *camera/lens*
property that's the same for every user on the same phone model regardless
of where they stand. Ratio/percentage framing of the shrink rate (e.g.
"50%->25%" vs a calibration clip's "80%->25%") doesn't sidestep this: focal
length and distance only ever appear as a product in the size equation
(diameter_px = focal_px * BALL_DIAMETER_M / distance), so no amount of
looking at relative shrinkage recovers one from the other without an
external anchor -- there is no way around needing one per video, only a
choice of what to anchor on. v2.1 anchors on the device instead of the
setup: DEVICE_FOCAL_PX_PER_WIDTH keys a resolution-independent
focal-px-per-frame-width ratio by the video's `com.apple.quicktime.model`
container-metadata tag (present on real iPhone videos -- confirmed via
ffmpeg on a real user recording -- even though no explicit focal-length/FOV
tag exists). A device model's entry, once measured from ONE reference clip
(see _device_model_from_video below and TODO_MANUAL.md for the filming
recipe), applies correctly to every user on that same phone model at any
distance -- which ASSUMED_CAMERA_TO_NET_M does not. The table starts empty:
no real calibration data exists yet, and guessing numbers from public spec
sheets would just be a different unverified assumption wearing a more
precise-looking hat (video-mode sensor crop/stabilization can differ from
quoted photo-mode specs). Until a device has a table entry, focal_px falls
back to the v2 assumed-distance approximation, unchanged.

v3 (2026-09-11, same session) adds a THIRD, higher-priority tier that needs no
assumption at all: a court-geometry self-calibration. Jack pushed back that a
per-device table doesn't scale (needs a filmed reference clip per phone
model). A first attempt at self-calibrating from the sideline vanishing point
alone (see infer_angle.sideline_vanishing_point_y) turned out to be
mathematically degenerate on closer derivation -- the net is one object at
one distance, and no combination of measurements taken from it alone (width,
row position) supplies a second independent equation; the focal-length terms
algebraically cancel out however they're combined. Fixing this needed one
more real-world reference at a genuinely different, known distance:
infer_angle.detect_near_baseline gives the near baseline's row, and the
baseline-to-net distance (11.89m) is a fixed court dimension true for every
setup, not a per-user assumption. Combined with the sideline vanishing
point's row and the already-detected net (row + pixel width), this is a
well-posed system (4 equations, 4 unknowns: focal length, camera height,
pitch, camera-to-baseline distance) solved numerically in
_focal_px_from_court_geometry -- see that function for the exact pinhole
geometry and _solve_camera_geometry's derivation notes. Verified against 320
synthetic (focal length, height, pitch, distance) combinations spanning
realistic phone-holding setups: recovers all four exactly (see
test_court_geometry_calibration_pytest.py). Real footage (Jack's own
IMG_5755.MOV) shows the underlying vanishing-point and baseline detections
are stable and plausible across a whole fixed-camera match, but baseline
detection recall is well under half (lighting/shadow dependent) -- so this
tier fires often enough to be worth having as the best available source when
it does, but is not expected to fire on every video; it falls through
cleanly to the device table, then the assumed-distance approximation, when
any of its inputs are missing.

Every failure mode here returns None silently (by product decision) rather
than raising or surfacing a placeholder -- an unavailable speed reading is
common (close-up framing, net out of frame, ball tracking lost) and not
worth alarming a user over. The radial estimator in particular is additive:
if diameter data is missing or unreliable it drops out and the result falls
back to the lateral-only estimate, same as v1 produced when it succeeded.
"""
import os
import subprocess
import sys

import cv2
import imageio_ffmpeg
import numpy as np
from scipy.optimize import brentq

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))

from infer_angle import (  # noqa: E402
    extract_frame, detect_net_endpoints_keypoints, detect_near_baseline,
    sideline_vanishing_point_y,
)
from racket_tracker import track_racket_and_ball, _interpolated_ball_track  # noqa: E402
from ball_roi_tracker import refine_ball_track  # noqa: E402

# ITF net-post-to-net-post span: doubles court width (10.97m) + 0.914m
# overhang each side -- the real-world distance the trained net-keypoint
# model's 'net_top_left'/'net_top_right' points bracket, regardless of
# whether the match itself is singles or doubles (the net is always strung
# post to post).
NET_WIDTH_M = 12.8

# ITF baseline-to-net distance -- fixed on every standard court, unlike
# ASSUMED_CAMERA_TO_NET_M below (which guesses where the CAMERA stands, a
# setup property that varies per user). This is a court dimension, true
# regardless of setup, so it costs nothing to use as a calibration anchor.
BASELINE_TO_NET_M = 11.89

# Sanity bounds on the court-geometry solver's recovered camera height and
# pitch -- a solution outside a plausible phone-holding range is more likely
# a bad line detection than a real reading (same "discard rather than
# mislead" philosophy as MIN/MAX_PLAUSIBLE_KMH). Generous on purpose: this
# gates obviously-wrong solves, not borderline ones.
PLAUSIBLE_CAMERA_HEIGHT_M = (0.5, 2.2)
PLAUSIBLE_PITCH_DEG = (0.1, 45.0)
PLAUSIBLE_BASELINE_DISTANCE_M = (0.05, 8.0)

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

# Real tennis ball diameter (ITF spec, 6.54-6.86cm) -- used with the same
# apparent-size-implies-distance logic as NET_WIDTH_M, just for the ball
# instead of the net.
BALL_DIAMETER_M = 0.067

# Fallback focal-length approximation for a device with no
# DEVICE_FOCAL_PX_PER_WIDTH entry (see below): treat the net-width detection
# ball_speed already uses for scale as if it were seen from an assumed
# camera-to-net distance for a correctly-positioned behind-the-baseline shot
# -- baseline-to-net is a fixed 11.89m on any standard court, plus a nominal
# ~1m setback for the fence/tripod mount itself. This is a genuine
# approximation (real user setups vary a lot in how far back they stand) in
# the same spirit as NET_WIDTH_M's scale -- disclosed, not hidden -- and only
# used for the radial (depth) term below, never the lateral term's existing
# net-width scale. Superseded per-device by DEVICE_FOCAL_PX_PER_WIDTH once a
# real calibration entry exists for that device model (see module docstring).
ASSUMED_CAMERA_TO_NET_M = 13.0

# Per-device-model calibration: focal length in pixels PER PIXEL OF FRAME
# WIDTH (i.e. focal_px = ratio * frame_width_px), so one entry applies at any
# recording resolution for that device model. Keyed by the exact string a
# real video's `com.apple.quicktime.model` container-metadata tag carries
# (see _device_model_from_video) -- e.g. 'iPhone 13'. Starts empty: no real
# calibration data exists yet (see module docstring for why guessed public
# spec numbers aren't used here, and TODO_MANUAL.md for the filming recipe
# to populate a real entry). Devices not in this table fall back to the
# ASSUMED_CAMERA_TO_NET_M approximation above, unchanged from v2.
DEVICE_FOCAL_PX_PER_WIDTH = {}

# ffmpeg (via imageio_ffmpeg's bundled binary -- already an installed
# dependency, no new one added) reading container metadata is fast (reads
# the moov atom's tags, does not decode video), but still bounded in case a
# corrupt/unusual file hangs it.
DEVICE_METADATA_TIMEOUT_SECONDS = 10

# Ball bounding boxes are noisier than the plain presence/absence confidence
# used elsewhere (racket_tracker.CONF_THRESHOLD=0.15) -- a low-confidence box
# on a small, fast-moving, sometimes-occluded ball is often the right general
# area but a badly-fitted box, which corrupts a size-derivative estimate much
# more than it corrupts a centre-position one. Require more confidence before
# trusting a frame's diameter reading.
MIN_BALL_CONF_FOR_DIAMETER = 0.30

# Same half-window/degree pattern as the lateral velocity fit, applied to the
# diameter-vs-frame series instead of position.
DIAMETER_HALF_WINDOW = VELOCITY_HALF_WINDOW
DIAMETER_POLY_DEGREE = VELOCITY_POLY_DEGREE


def _device_model_from_video(video_path):
    """
    Reads the `com.apple.quicktime.model` container-metadata tag (e.g.
    'iPhone 13') via ffmpeg's ffmetadata dump, or None whenever it's absent
    (non-phone source, different platform's equivalent tag not yet added
    here, corrupt file) or ffmpeg can't be run at all -- same fail-open
    philosophy as the rest of this module: an unidentified device just means
    DEVICE_FOCAL_PX_PER_WIDTH has nothing to look up, not an error.

    Uses imageio_ffmpeg's bundled ffmpeg binary (already an installed
    dependency elsewhere in this venv) rather than requiring a system ffmpeg
    install. `-f ffmetadata -` reads container tags without decoding video,
    so this is fast even on a large file.
    """
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [ffmpeg_exe, '-i', video_path, '-f', 'ffmetadata', '-'],
            capture_output=True, timeout=DEVICE_METADATA_TIMEOUT_SECONDS,
            text=True, errors='ignore')
    except Exception:  # noqa: BLE001 -- ffmpeg missing/broken, never fatal
        return None

    for line in result.stdout.splitlines():
        if line.startswith('com.apple.quicktime.model='):
            model = line.split('=', 1)[1].strip()
            return model or None
    return None


def _solve_camera_geometry(vp_y_px, net_y_px, net_width_px, baseline_y_px, cy_px):
    """
    Solve for (focal_px, camera_height_m, pitch_deg, camera_to_baseline_m)
    from four measured image rows/widths and the court's fixed dimensions --
    no assumed distance or height anywhere. See module docstring (v3) for how
    this system was arrived at; verified against 320 synthetic
    (f, H, pitch, d_baseline) combinations in
    test_court_geometry_calibration_pytest.py before ever running on a real
    frame.

    Pinhole geometry (zero roll -- run on roll-corrected coordinates; H =
    camera height above the ground, theta = pitch down from horizontal, d =
    horizontal ground distance from the camera's foot-point to a ground
    point):
        Yc(d) = H*cos(theta) - d*sin(theta)
        Zc(d) = H*sin(theta) + d*cos(theta)
        row - cy = f * Yc(d) / Zc(d)
        vp_y - cy = -f * tan(theta)                          (d -> infinity)
        net_width_px = f * NET_WIDTH_M / Zc(d_net)
    with d_net = d_baseline + BASELINE_TO_NET_M.

    Given theta, (1) pins f directly; (2)+(4) are then LINEAR in (H, d_baseline)
    and solve in closed form; the net-row equation (3) is not used in that
    closed form and instead becomes the residual driven to zero by a 1-D
    search over theta -- reduces a 4-unknown nonlinear system to a 1-D root
    find, which is both exact (verified) and numerically well-behaved,
    rather than a general 4-D solve.

    Returns None on any degenerate input (rows not in the expected vp_y <
    net_y < baseline_y order, no sign change found for the 1-D search, a
    solve that fails to converge, or a recovered height/pitch/distance
    outside PLAUSIBLE_*) -- this is the top calibration tier and must fall
    through cleanly, never raise or return a wild number.
    """
    if not (vp_y_px < net_y_px < baseline_y_px):
        return None  # not the expected horizon/net/baseline ordering -- bad input

    def solve_given_theta(theta):
        tan_t = np.tan(theta)
        if abs(tan_t) < 1e-9:
            return None
        f = -(vp_y_px - cy_px) / tan_t
        if f <= 0:
            return None
        zc3_target = f * NET_WIDTH_M / net_width_px
        rhs4 = zc3_target - BASELINE_TO_NET_M * np.cos(theta)
        bmc = baseline_y_px - cy_px
        a2 = f * np.cos(theta) - bmc * np.sin(theta)
        b2 = f * np.sin(theta) + bmc * np.cos(theta)
        if abs(a2) < 1e-9:
            return None
        denom = b2 * np.sin(theta) / a2 + np.cos(theta)
        if abs(denom) < 1e-9:
            return None
        d1 = rhs4 / denom
        h_cam = d1 * b2 / a2
        return f, h_cam, d1

    def residual(theta):
        solved = solve_given_theta(theta)
        if solved is None:
            return None
        f, h_cam, d1 = solved
        d3 = d1 + BASELINE_TO_NET_M
        zc3 = h_cam * np.sin(theta) + d3 * np.cos(theta)
        if zc3 == 0:
            return None
        yc3 = h_cam * np.cos(theta) - d3 * np.sin(theta)
        pred_net_y = cy_px + f * yc3 / zc3
        return pred_net_y - net_y_px

    thetas = np.radians(np.linspace(0.5, 44.0, 400))
    vals = [residual(t) for t in thetas]

    root_theta = None
    for i in range(len(thetas) - 1):
        v0, v1 = vals[i], vals[i + 1]
        if v0 is None or v1 is None:
            continue
        if np.sign(v0) != np.sign(v1):
            try:
                root_theta = brentq(
                    lambda t: residual(t) if residual(t) is not None else float('nan'),
                    thetas[i], thetas[i + 1])
            except Exception:  # noqa: BLE001 -- degenerate bracket, try the next one
                continue
            break
    if root_theta is None:
        return None

    solved = solve_given_theta(root_theta)
    if solved is None:
        return None
    f, h_cam, d1 = solved
    pitch_deg = np.degrees(root_theta)

    if not (PLAUSIBLE_CAMERA_HEIGHT_M[0] <= h_cam <= PLAUSIBLE_CAMERA_HEIGHT_M[1]):
        return None
    if not (PLAUSIBLE_PITCH_DEG[0] <= pitch_deg <= PLAUSIBLE_PITCH_DEG[1]):
        return None
    if not (PLAUSIBLE_BASELINE_DISTANCE_M[0] <= d1 <= PLAUSIBLE_BASELINE_DISTANCE_M[1]):
        return None
    if f <= 0:
        return None
    return f, h_cam, pitch_deg, d1


def _focal_px_from_court_geometry(video_path, frame_number, net_y_px, net_width_px,
                                   frame_width_px, frame_height_px):
    """
    Top-tier focal_px source: self-calibrated from this specific video's own
    court geometry, no assumption of any kind (see module docstring, v3).
    Returns None whenever the vanishing point or baseline isn't confidently
    detected on this frame, the frame itself can't be read (bad path,
    corrupt video -- never fatal here, same fail-open philosophy as the rest
    of this module even though extract_frame itself can raise), or the
    geometry solve fails/lands outside a plausible range -- callers fall
    through to the device table, then the assumed-distance approximation.
    """
    try:
        frame = extract_frame(video_path, frame_number)
    except Exception:  # noqa: BLE001 -- unreadable frame, fall through, never fatal
        return None
    vp_y = sideline_vanishing_point_y(frame)
    if vp_y is None:
        return None
    baseline_y = detect_near_baseline(frame, net_y_px / frame_height_px)
    if baseline_y is None:
        return None

    solved = _solve_camera_geometry(
        vp_y * frame_height_px, net_y_px, net_width_px,
        baseline_y * frame_height_px, frame_height_px / 2.0)
    if solved is None:
        return None
    f, _h_cam, _pitch_deg, _d1 = solved
    return f


def _focal_px_for_video(video_path, frame_number, net_y_px, net_width_px,
                        frame_width_px, frame_height_px):
    """
    focal_px for the radial estimator, best available source first:
      1. Court-geometry self-calibration (v3) -- no assumption, this video's
         own measurements only. Tried first since it's strictly the best
         source when available.
      2. A calibrated per-device ratio (DEVICE_FOCAL_PX_PER_WIDTH, v2.1) when
         this video's device model has one.
      3. The v2 fallback derived from the net's own pixel width and
         ASSUMED_CAMERA_TO_NET_M.
    See module docstring for why each tier exists and what it trades off.
    """
    geometry_focal_px = _focal_px_from_court_geometry(
        video_path, frame_number, net_y_px, net_width_px, frame_width_px, frame_height_px)
    if geometry_focal_px is not None:
        print('  [ball_speed] focal_px: court-geometry self-calibration', file=sys.stderr)
        return geometry_focal_px

    device_model = _device_model_from_video(video_path)
    ratio = DEVICE_FOCAL_PX_PER_WIDTH.get(device_model) if device_model else None
    if ratio is not None:
        print(f'  [ball_speed] focal_px: device table ({device_model})', file=sys.stderr)
        return ratio * frame_width_px

    print('  [ball_speed] focal_px: assumed-distance fallback', file=sys.stderr)
    return net_width_px * ASSUMED_CAMERA_TO_NET_M / NET_WIDTH_M


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


def _ball_diameter_track(detections):
    """
    (frame, diameter_px) for every detection with a ball_box whose ball_conf
    clears MIN_BALL_CONF_FOR_DIAMETER, in raw detection order. Uses the
    geometric mean of box width/height (sqrt(w*h)) rather than either alone --
    robust to the box being slightly non-square from motion blur or a jittery
    regression, without needing to assume which axis is more trustworthy.

    Deliberately reads the raw per-frame `detections` (track_racket_and_ball's
    output), not the Kalman-filtered `_interpolated_ball_track` -- that filter
    only tracks (x, y) centre position, carries no size state, and a size
    trend needs the actual measured box, not a position-only prediction.
    """
    track = []
    for d in detections:
        box, conf = d.get('ball_box'), d.get('ball_conf')
        if box is None or conf is None or conf < MIN_BALL_CONF_FOR_DIAMETER:
            continue
        x1, y1, x2, y2 = box
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            continue
        track.append((d['frame'], float(np.sqrt(w * h))))
    return track


def _diameter_fit_at(diam_track, frame, half_window=DIAMETER_HALF_WINDOW,
                      degree=DIAMETER_POLY_DEGREE):
    """
    Polynomial-fit the diameter-vs-frame series the same way
    _ball_speed_px_per_frame_at fits position, returning
    (diameter_px_at_frame, d_diameter_px_per_frame) or None if there isn't
    enough data in the window to fit reliably.
    """
    pts = [(f, diam) for f, diam in diam_track if abs(f - frame) <= half_window]
    if len(pts) < 2:
        return None
    pts.sort(key=lambda p: p[0])

    degree = min(degree, len(pts) - 1)
    if degree < 1:
        return None

    frames = np.array([p[0] for p in pts], dtype=float)
    diams = np.array([p[1] for p in pts], dtype=float)

    t0 = frames[0]
    t = frames - t0
    p = np.polyfit(t, diams, degree)
    dp = np.polyder(p)

    eval_t = frame - t0
    diameter_at_frame = float(np.polyval(p, eval_t))
    d_diameter = float(np.polyval(dp, eval_t))
    return diameter_at_frame, d_diameter


def _radial_speed_m_per_s(diam_track, frame, focal_px, fps):
    """
    Radial (toward/away from camera) speed at `frame`, from how fast the
    ball's apparent diameter is shrinking/growing. Similar-triangles distance
    estimate: distance_px = focal_px * BALL_DIAMETER_M / diameter_px. Its time
    derivative (chain rule) turns the fitted d(diameter)/dframe into
    d(distance)/dframe, scaled to per-second by fps.

    Returns None whenever there isn't a confident diameter fit at this frame,
    or the fitted diameter is non-positive (degenerate fit) -- this is an
    additive signal, never a required one; callers fall back to lateral-only.
    """
    fit = _diameter_fit_at(diam_track, frame)
    if fit is None:
        return None
    diameter_at_frame, d_diameter_per_frame = fit
    if diameter_at_frame <= 0:
        return None

    d_distance_per_frame = -focal_px * BALL_DIAMETER_M / (diameter_at_frame ** 2) * d_diameter_per_frame
    return abs(d_distance_per_frame) * fps


def estimate_net_crossing_ball_speed_kmh(video_path, contact_frame, fps, camera_angle_deg,
                                         use_roi_tracker=False):
    """
    Best-effort ball speed (km/h) at the moment the ball crosses the net
    after `contact_frame`, or None whenever the estimate can't be trusted
    (see module docstring) -- never raises for an "unavailable" case, only
    for a genuinely broken video_path/model load, same as this pipeline's
    other non-fatal-on-failure stats.

    use_roi_tracker: run ball_roi_tracker.refine_ball_track (pass 2) over the
    pass-1 detections before fitting the crossing. Plumbing is kept but the
    default is OFF -- the honest dense-set eval (2026-09-07, after an
    inflated-continuity bug in eval_ball_roi_tracker._densify was fixed)
    showed it helps only 2/10 clips (~+0.1 continuity), no-ops 7/10, and
    regresses 1/10. Flip to True per-call to experiment / once the tracker
    earns it.
    """
    # camera_angle_deg is still required -- it's how compare_swing.py knows
    # the camera setup was read at all -- but no longer thresholded against
    # MIN_RELIABLE_ANGLE_DEG (see module docstring: that gate was rejecting
    # exactly the low-angle, less-foreshortened framing where the net-width
    # scale is fine and only the lateral *motion* signal is naturally weak,
    # which the radial term below now covers instead of losing the stat).
    if camera_angle_deg is None:
        return None

    bounds = _net_scale_and_bounds(video_path, contact_frame)
    if bounds is None:
        return None
    scale, net_y_px, left_x_px, right_x_px = bounds
    net_width_px = NET_WIDTH_M / scale

    cap = cv2.VideoCapture(video_path)
    frame_width_px = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    frame_height_px = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    cap.release()
    focal_px = _focal_px_for_video(video_path, contact_frame, net_y_px, net_width_px,
                                   frame_width_px, frame_height_px)

    end_frame = contact_frame + int(MAX_SEARCH_SECONDS * fps)
    detections, _ = track_racket_and_ball(video_path, frame_range=(contact_frame, end_frame))
    track = None
    if use_roi_tracker:
        try:
            track = refine_ball_track(video_path, detections, fps,
                                      contact_frame=contact_frame).filled_track
        except Exception as e:  # noqa: BLE001 -- fall back to pass-1, never fatal
            print(f'  [ball_speed] ROI tracker failed, using pass-1 track: {e}', file=sys.stderr)
    if not track:  # ROI off, declined (cold clip), or errored
        track = _interpolated_ball_track(detections, contact_frame, end_frame)
    if not track:
        return None

    crossing_frame = _find_net_crossing(track, net_y_px, left_x_px, right_x_px)
    if crossing_frame is None:
        return None

    speed_px_per_frame = _ball_speed_px_per_frame_at(track, crossing_frame)
    if speed_px_per_frame is None:
        return None
    lateral_m_per_s = speed_px_per_frame * fps * scale

    diam_track = _ball_diameter_track(detections)
    radial_m_per_s = _radial_speed_m_per_s(diam_track, crossing_frame, focal_px, fps) or 0.0

    total_m_per_s = float(np.hypot(lateral_m_per_s, radial_m_per_s))
    kmh = total_m_per_s * 3.6
    if not (MIN_PLAUSIBLE_KMH <= kmh <= MAX_PLAUSIBLE_KMH):
        return None
    return round(kmh, 1)
