"""
Viewpoint (yaw) normalization for swing pose trajectories.

The comparison pipeline already normalizes camera distance/zoom (shoulder-width
scaling), roll (net-cord tilt) and handedness (mirror). It does NOT correct for
the camera's horizontal angle to the court: a swing filmed from behind-centre
and the same swing filmed from behind-the-doubles-alley project the wrist arc
differently, so they match different pros.

This module removes that. It does not try to MEASURE the camera angle (the
net-based estimator in infer_angle.py is unreliable). Instead it reads the
player's facing direction straight out of MediaPipe's world landmarks (metric
3D, hip-origin, image-aligned axes) and rotates the swing about the vertical
axis to a canonical facing -- the same facing the pro database is effectively
built at (right-handed player filmed from behind the baseline). Camera-at-30
and player-facing-30 rotate the shoulder/hip line identically, so the camera
angle falls out with no net detection.

Pure math, no mediapipe import (same split rationale as trajectory_extraction.py
-- callers that only need the geometry shouldn't pay the import cost, and this
module is imported BY trajectory_extraction so it must not import back).

Coordinate frame (MediaPipe world landmarks): x ~ image-right, y ~ image-down,
z ~ camera depth. Canonical = shoulder/hip line along +x with ~0 z-component
=> azimuth 0. A front view of the same stance reads ~180 deg away.

Safe degradation mirrors infer_angle.usable_roll(): if the windowed azimuth
estimate is weak (too few frames, too noisy, within a deadband, or beyond a
near-side-on cap) usable_yaw() returns None and the caller applies identity --
byte-identical to the pre-yaw trajectory.
"""
import math

# Per-landmark visibility floor -- matches trajectory_extraction.MIN_LANDMARK_VISIBILITY
# (kept local to keep this module import-free).
_MIN_VIS = 0.3

# usable_yaw() banding.
YAW_MIN_FRAMES = 4            # need at least this many pre-contact frames with a readable azimuth
YAW_MAX_STDEV_DEG = 22.0      # above this the per-frame azimuth is flailing -> don't trust it
YAW_DEADBAND_DEG = 10.0       # below this the correction is within world-z noise -> not worth it
YAW_MAX_CORRECTION_DEG = 65.0 # near side-on the shoulder/hip vector aliases and depth sign is unreliable

# The player's trunk sweeps through ~100 deg during the swing, so the azimuth
# taken over the whole PRE_SEC..POST_SEC window is dominated by that rotation,
# not the camera (spike, 2026-09-08: full-window stdev 45-127 deg; even
# "everything before contact" still drifts as the takeback starts). Read the
# camera azimuth from the LEAD-IN only -- the first ~third of a second of
# whatever pre-swing footage the clip has, where the player is still in a
# roughly neutral ready stance -- and weight the hips over the shoulders (hips
# rotate far less through a groundstroke). Clips cut too tight to contain a
# lead-in get no estimate (-> identity), which is correct: there's nothing to
# read the camera position from.
YAW_PRE_CONTACT_SEC = -0.12   # a lead-in frame must be at least this far before contact
YAW_LEADIN_SEC = 0.35         # use frames within this much of the earliest available frame
_HIP_WEIGHT = 2.0
_SHOULDER_WEIGHT = 1.0


def _horiz(v):
    """(x, z) of a world-landmark dict entry, or None if it's missing / low-vis."""
    if v is None:
        return None
    if v.get('visibility', 1.0) < _MIN_VIS:
        return None
    return v['x'], v['z']


def facing_azimuth(world_lm):
    """
    Signed body-facing azimuth (degrees) in the camera's horizontal plane for
    ONE frame's world-landmark dict {name: {'x','y','z','visibility'?}}.

    0 => shoulder/hip line parallel to image-x (canonical, player square to a
    camera behind them). +/- as the line rotates toward/away from the camera.
    Front vs back view of the same stance differ by ~180 deg.

    Weighted average of the (unit-normalised) hip vector and shoulder vector,
    hips weighted higher -- the hip line rotates far less through a swing so it
    anchors the estimate. Uses whichever of the two are available; returns None
    only if neither the hips nor the shoulders are usable, or the result is
    degenerate.
    """
    ls, rs = _horiz(world_lm.get('left_shoulder')), _horiz(world_lm.get('right_shoulder'))
    lh, rh = _horiz(world_lm.get('left_hip')), _horiz(world_lm.get('right_hip'))

    ax = az = 0.0
    if lh is not None and rh is not None:
        hx, hz = rh[0] - lh[0], rh[1] - lh[1]
        hn = math.hypot(hx, hz)
        if hn > 1e-6:
            ax += _HIP_WEIGHT * hx / hn
            az += _HIP_WEIGHT * hz / hn
    if ls is not None and rs is not None:
        sx, sz = rs[0] - ls[0], rs[1] - ls[1]
        sn = math.hypot(sx, sz)
        if sn > 1e-6:
            ax += _SHOULDER_WEIGHT * sx / sn
            az += _SHOULDER_WEIGHT * sz / sn

    if math.hypot(ax, az) < 1e-6:
        return None
    return math.degrees(math.atan2(az, ax))


def _folded(deg):
    """Distance to the nearer of {0, 180} -- how far the azimuth is from square-on
    to the camera regardless of front/back. Used only for the side-on cap."""
    a = abs(deg) % 360.0
    if a > 180.0:
        a = 360.0 - a
    return min(a, abs(180.0 - a))


def usable_yaw(samples):
    """
    median(samples) if the windowed azimuth estimate passes every guard, else
    None (=> caller applies identity, exactly like infer_angle.usable_roll).

    samples: per-frame facing_azimuth() values (None already filtered out).
    """
    samples = [s for s in samples if s is not None]
    if len(samples) < YAW_MIN_FRAMES:
        return None
    # circular-safe enough for the +/-90 range we operate in; the side-on cap
    # keeps us away from the +/-180 wrap.
    med = _median(samples)
    if _stdev(samples) > YAW_MAX_STDEV_DEG:
        return None
    if abs(med) < YAW_DEADBAND_DEG:
        return None
    if _folded(med) > YAW_MAX_CORRECTION_DEG:
        return None
    return med


def soft_yaw(samples):
    """
    Like usable_yaw() but WITHOUT the YAW_DEADBAND_DEG check -- returns the
    windowed median whenever the estimate is *coherent* (enough frames, low
    per-frame spread) and not near side-on, even for a sub-10-degree camera
    angle.

    usable_yaw() drops sub-deadband angles because a <10 deg rotation of the 2D
    x/y trajectory isn't worth the risk of a slightly-off estimate. But the
    metric world-z channel IS sensitive to a few degrees (sin 10 deg ~ 0.17,
    and z magnitudes are O(1) after scaling), so the z-only path rotates
    whenever there's any trustworthy signal. None (thin / noisy / side-on
    lead-in) -> caller leaves z unrotated (still metric world z, just carrying
    the residual camera azimuth -- fine for the within-body differential depth
    axes on near-canonical footage).
    """
    samples = [s for s in samples if s is not None]
    if len(samples) < YAW_MIN_FRAMES:
        return None
    med = _median(samples)
    if _stdev(samples) > YAW_MAX_STDEV_DEG:
        return None
    if _folded(med) > YAW_MAX_CORRECTION_DEG:
        return None
    return med


def rotate_world_landmarks(world_lm, yaw_deg):
    """
    Rotate every landmark about the vertical (y) axis so its horizontal azimuth
    decreases by yaw_deg -- i.e. undo a camera yaw of +yaw_deg. y is untouched.
    None / missing entries pass through. yaw_deg None or 0 -> same object.

    (x, z) at azimuth phi -> azimuth phi - yaw:
        x' =  x*cos(yaw) + z*sin(yaw)
        z' = -x*sin(yaw) + z*cos(yaw)
    """
    if not yaw_deg:
        return world_lm
    a = math.radians(yaw_deg)
    ca, sa = math.cos(a), math.sin(a)
    out = {}
    for name, v in world_lm.items():
        if v is None:
            out[name] = None
            continue
        x, z = v['x'], v['z']
        out[name] = {
            'x': x * ca + z * sa,
            'y': v['y'],
            'z': -x * sa + z * ca,
            'visibility': v.get('visibility'),
        }
    return out


def project_canonical_2d(world_lm, image_lm):
    """
    Flatten a (yaw-normalised) world-landmark dict to the {name: {'x','y','z','visibility'}}
    shape get_shoulder_ref / normalise_landmarks already consume. World x/y/z are
    kept as-is (metric, canonical facing); visibility is copied from the matching
    IMAGE landmark for that frame (world-landmark visibility tracks it but the
    image value is what the rest of the pipeline has always gated on). 0.0 when
    the image landmark is absent.
    """
    out = {}
    image_lm = image_lm or {}
    for name, v in world_lm.items():
        if v is None:
            out[name] = None
            continue
        img = image_lm.get(name)
        out[name] = {
            'x': v['x'],
            'y': v['y'],
            'z': v['z'],
            'visibility': (img.get('visibility', 0.0) if img else 0.0),
        }
    return out


def yaw_normalise_window(world_frames_with_t):
    """
    (yaw_deg | None, samples) for a swing window.

    world_frames_with_t: list of (t, world_landmark_dict), t in seconds relative
    to contact. Only the lead-in frames are used -- those within YAW_LEADIN_SEC
    of the earliest available frame AND at least YAW_PRE_CONTACT_SEC before
    contact (see the comment on those constants). yaw_deg is the median of those
    if usable_yaw accepts it, else None. `samples` is the lead-in azimuth list
    (for logging / the calibration eval).
    """
    ts = [t for (t, _) in world_frames_with_t]
    if not ts:
        return None, []
    cutoff = min(min(ts) + YAW_LEADIN_SEC, YAW_PRE_CONTACT_SEC)
    samples = [az for (t, w) in world_frames_with_t
               if t <= cutoff and (az := facing_azimuth(w)) is not None]
    return usable_yaw(samples), samples


# ── tiny stats helpers (avoid a statistics import for hot-path callers) ──────

def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _stdev(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
