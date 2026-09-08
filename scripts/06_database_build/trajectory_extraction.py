"""
Pure pose-math trajectory extraction, split out of build_pro_database.py
(2026-08-27) so scripts that only need this -- like split_pro_clip.py,
which re-derives a trajectory for a manually-split second swing -- don't
have to import build_pro_database.py's own top-level infer_angle.py import,
which pulls in mediapipe (unnecessary cost for something that never runs
camera-angle inference). No logic changes from the originals; this is a
straight move, not a rewrite. build_pro_database.py itself imports these
back (`from trajectory_extraction import ...`) rather than redefining them,
and several other scripts import these names via build_pro_database.py
directly (compare_swing.py, compare_videos.py, track_racket_in_clip.py,
train_tip_selector_on_amateur_footage.py, build_pro_overlay_trajectories.py,
test_build_pro_database_pytest.py) -- that continues to work unchanged
since Python re-exports names imported into a module's own namespace.
"""
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viewpoint_normalization import (  # noqa: E402
    rotate_world_landmarks, project_canonical_2d,
)

# Upper-body landmarks used for comparison (ignore legs)
KEY_LANDMARKS = [
    'nose',
    'left_shoulder', 'right_shoulder',
    'left_elbow',    'right_elbow',
    'left_wrist',    'right_wrist',
    'left_hip',      'right_hip',
]

MIN_LANDMARK_VISIBILITY = 0.3


def build_pose_index(frames):
    index = {}
    for f in frames:
        if f['landmarks']:
            index[f['frame']] = {lm['name']: lm for lm in f['landmarks']}
    return index


def build_world_pose_index(frames):
    """Like build_pose_index but off f['world_landmarks'] (MediaPipe metric 3D).
    Returns {} for pose files predating world-landmark capture -- every yaw
    consumer treats an empty index as "no yaw estimate available"."""
    index = {}
    for f in frames:
        wl = f.get('world_landmarks')
        if wl:
            index[f['frame']] = {lm['name']: lm for lm in wl}
    return index


def get_shoulder_ref(lm_dict):
    ls = lm_dict.get('left_shoulder')
    rs = lm_dict.get('right_shoulder')
    if not ls or not rs:
        return None, None, None
    # Every other landmark normalise_landmarks() outputs is gated on this same
    # 0.3 visibility threshold -- the shoulders themselves weren't, even
    # though mid_x/mid_y become the translation ORIGIN every other landmark in
    # the frame is measured against. An occluded/low-confidence shoulder still
    # gets a real (non-null) x/y from MediaPipe, so `not ls or not rs` alone
    # never catches it -- it would silently shift every "confident" landmark
    # in that frame by however wrong the shoulder guess was, worst right at
    # contact where occlusion is most likely. Reject the whole frame instead.
    if ls.get('visibility', 0) < MIN_LANDMARK_VISIBILITY or rs.get('visibility', 0) < MIN_LANDMARK_VISIBILITY:
        return None, None, None
    mid_x = (ls['x'] + rs['x']) / 2
    mid_y = (ls['y'] + rs['y']) / 2
    width = math.sqrt((ls['x'] - rs['x'])**2 + (ls['y'] - rs['y'])**2)
    return mid_x, mid_y, width


def normalise_landmarks(lm_dict, scale=None):
    """Return normalised (x, y, z) for KEY_LANDMARKS. Returns None if ref missing.

    `scale` should be a single stable shoulder-width value shared across an
    entire trajectory (see trajectory_scale()) rather than this frame's own
    shoulder width. Shoulder width fluctuates ~30% frame-to-frame as the body
    rotates through a swing (foreshortening), so dividing by the per-frame
    width amplifies ordinary pose-detection noise into large coordinate swings
    at exactly the frames that matter (mid-swing, near contact). Translation
    (mid_x/mid_y) is still taken per-frame since it should track the body.

    z: MediaPipe already reports a z per landmark (roughly hip-centered depth,
    same normalized-image-width units as x/y) on every frame -- previously
    captured at extraction and never read again past this function. No
    translation offset for z (MediaPipe's own origin is already usable),
    same `scale` divisor as x/y for consistency. Note MediaPipe's z is a
    rougher, noisier monocular depth estimate than x/y -- callers that
    consume it (trajectory_compare.py, phase_breakdown.py) should treat it
    as a lower-confidence signal, not equally trustworthy to x/y."""
    mid_x, mid_y, width = get_shoulder_ref(lm_dict)
    # mid_x can legitimately be 0.0 (shoulder midpoint sitting exactly at the
    # frame's left edge) -- `not mid_x` treated that as "missing" the same as
    # get_shoulder_ref()'s real missing-ref case (None), incorrectly
    # dropping a valid frame. width is never a valid 0.0 (two distinct
    # shoulder points), so `width < 0.01` alone still correctly guards that.
    if mid_x is None or width < 0.01:
        return None
    if scale is None:
        scale = width

    result = {}
    for name in KEY_LANDMARKS:
        lm = lm_dict.get(name)
        if lm and lm.get('visibility', 0) >= MIN_LANDMARK_VISIBILITY:
            result[name] = {
                'x': round((lm['x'] - mid_x) / scale, 4),
                'y': round((lm['y'] - mid_y) / scale, 4),
                'z': round(lm['z'] / scale, 4) if lm.get('z') is not None else None,
            }
        else:
            result[name] = None
    return result


def trajectory_scale(lm_dicts):
    """Median shoulder width across a window of raw landmark dicts — a
    single stable scale for the whole trajectory instead of per-frame width."""
    widths = [w for lm in lm_dicts if lm and (w := get_shoulder_ref(lm)[2]) is not None and w >= 0.01]
    return statistics.median(widths) if widths else None


# ── Trajectory extraction for one swing ──────────────────────────────────────

PRE_SEC = 0.5
POST_SEC = 1.0
MIN_TRAJECTORY_POINTS = 5


def extract_swing_trajectory(swing, pose_index, fps):
    """
    Sample every available pose frame (native ~20fps from extract_poses.py)
    from PRE_SEC before to POST_SEC after the peak (contact) frame, instead
    of 3 fixed snapshots — this preserves the actual shape/speed of the swing
    for DTW comparison rather than compressing it to 3 points.

    Returns a list of {'t': seconds relative to contact, 'landmarks': {...}},
    or None if too few usable frames are found.

    Pro-side builder -- deliberately does NOT yaw-normalise (the pro database
    trajectories are left as they are; see the yaw-norm plan). The user side
    goes through extract_trajectory_from_index() instead.
    """
    peak = swing['peak_frame']
    lo = peak - int(PRE_SEC * fps)
    hi = peak + int(POST_SEC * fps)

    window_frames = [pose_index[f] for f in range(lo, hi + 1) if f in pose_index]
    scale = trajectory_scale(window_frames)
    if scale is None:
        return None

    trajectory = []
    for f in sorted(fr for fr in pose_index if lo <= fr <= hi):
        norm = normalise_landmarks(pose_index[f], scale)
        if norm is not None:
            trajectory.append({'t': round((f - peak) / fps, 4), 'landmarks': norm})

    if len(trajectory) < MIN_TRAJECTORY_POINTS:
        return None
    return trajectory


def extract_trajectory_from_index(pose_index, fps, contact_frame, *,
                                  world_pose_index=None, yaw_deg=None):
    """
    Window-sampling core for the USER side (compare_swing.build_user_trajectory).

    Same PRE_SEC..POST_SEC sampling + single-median-scale normalisation as
    extract_swing_trajectory, but optionally yaw-normalised: when a `yaw_deg`
    is supplied (the caller estimates it from the clip lead-in -- NOT from the
    DTW window, which is dominated by the swing itself) and `world_pose_index`
    covers the window, each frame's world landmarks are rotated by -yaw_deg
    about the vertical axis and projected to 2D before scale/normalise.
    yaw_deg None, or too few world-landmark frames in the window -> identity,
    byte-identical to the no-yaw path.

    Returns (trajectory, meta) where trajectory is [] on the same too-few-frames
    guard as extract_swing_trajectory's None, and meta is {'yaw_deg': float|None}.
    """
    lo = contact_frame - int(PRE_SEC * fps)
    hi = contact_frame + int(POST_SEC * fps)
    frame_nums = sorted(f for f in pose_index if lo <= f <= hi)

    lm_by_frame = {f: pose_index[f] for f in frame_nums}
    applied_yaw = None

    if yaw_deg is not None and world_pose_index:
        rotated = {}
        for f in frame_nums:
            w = world_pose_index.get(f)
            if w is None:
                continue
            rotated[f] = project_canonical_2d(rotate_world_landmarks(w, yaw_deg),
                                              pose_index[f])
        if len(rotated) >= MIN_TRAJECTORY_POINTS:
            lm_by_frame = rotated
            frame_nums = sorted(rotated)
            applied_yaw = yaw_deg
        # else: not enough world-landmark frames in the window -- fall back to
        # the raw image trajectory rather than a stub.

    meta = {'yaw_deg': applied_yaw}

    scale = trajectory_scale([lm_by_frame[f] for f in frame_nums])
    if scale is None:
        return [], meta

    trajectory = []
    for f in frame_nums:
        norm = normalise_landmarks(lm_by_frame[f], scale)
        if norm is not None:
            trajectory.append({'t': round((f - contact_frame) / fps, 4), 'landmarks': norm})

    if len(trajectory) < MIN_TRAJECTORY_POINTS:
        return [], meta
    return trajectory, meta


def build_swing_overlay(pose_index, fps, peak_frame, clip_start_frame):
    """Raw image-space (0-1) x/y for the same PRE_SEC..POST_SEC contact window
    as extract_swing_trajectory(), WITHOUT the shoulder-normalisation -- a
    frontend skeleton overlay needs landmarks that line up with the clip's
    actual video pixels, not DTW-comparable normalised coords.

    't' is seconds relative to the CLIP FILE's own frame 0 (clip_start_frame),
    not the contact frame -- the played-back clip was cut starting at
    clip_start_frame, so this is the timestamp convention that matches that
    video's playhead. Moved here from 13_overlay_trajectories/
    build_pro_overlay_trajectories.py (2026-08-27) so rebuild_helpers.py can
    reuse it without that script's `from build_pro_database import ...`
    (mediapipe) import; the overlay builder re-imports it from here unchanged.
    """
    lo = peak_frame - int(PRE_SEC * fps)
    hi = peak_frame + int(POST_SEC * fps)
    trajectory = []
    for f in sorted(fr for fr in pose_index if lo <= fr <= hi):
        lm_dict = pose_index[f]
        landmarks = {}
        for name in KEY_LANDMARKS:
            lm = lm_dict.get(name)
            landmarks[name] = (
                {'x': lm['x'], 'y': lm['y']}
                if lm and lm.get('visibility', 0) >= MIN_LANDMARK_VISIBILITY
                else None
            )
        trajectory.append({'t': round((f - clip_start_frame) / fps, 4), 'landmarks': landmarks})
    return trajectory


# ── Handedness mirroring ─────────────────────────────────────────────────────

# Left/right landmark name pairs, for reflecting a swing across the vertical
# centre line. 'nose' has no pair.
_MIRROR_SWAP = {
    'left_shoulder': 'right_shoulder', 'right_shoulder': 'left_shoulder',
    'left_elbow': 'right_elbow',       'right_elbow': 'left_elbow',
    'left_wrist': 'right_wrist',       'right_wrist': 'left_wrist',
    'left_hip': 'right_hip',           'right_hip': 'left_hip',
}


def rotate_landmarks(norm_landmarks, roll_deg):
    """
    Rotate an already shoulder-midpoint-centred landmark dict (the shape
    normalise_landmarks() returns) about the origin by -roll_deg, undoing an
    in-plane camera roll of +roll_deg (net-cord slope convention, see
    infer_angle.net_roll_deg). Coords are already origin-centred so a plain
    rotation about (0, 0) is exactly right -- no translate needed.

    z and None entries pass through untouched. roll_deg None or 0 returns the
    dict unchanged (same object).
    """
    if not roll_deg:
        return norm_landmarks
    theta = math.radians(-roll_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    out = {}
    for name, v in norm_landmarks.items():
        if v is None:
            out[name] = None
            continue
        x, y = v['x'], v['y']
        out[name] = {
            'x': round(x * cos_t - y * sin_t, 4),
            'y': round(x * sin_t + y * cos_t, 4),
            'z': v.get('z'),
        }
    return out


def rotate_trajectory(trajectory, roll_deg):
    """
    Apply rotate_landmarks(-roll_deg) to every point in a normalised
    trajectory, preserving 't'. No-op (returns the input unchanged) when
    roll_deg is None or 0. Not idempotent -- rotating twice compounds; the
    pro-DB enrichment guards against a double pass with a per-entry flag.
    """
    if not roll_deg:
        return trajectory
    return [{'t': pt['t'], 'landmarks': rotate_landmarks(pt['landmarks'], roll_deg)}
            for pt in trajectory]


def mirror_trajectory(trajectory):
    """
    Horizontally mirror a normalised trajectory so a left-handed player's
    swing becomes directly comparable to the (all right-handed) pro database.

    Coords are already shoulder-midpoint-centred (normalise_landmarks), so the
    reflection is x -> -x. The left_/right_ landmark NAMES must also be
    swapped: trajectory_compare._frame_dist matches landmarks by name, so
    without the swap a lefty's hitting-hand wrist would be compared against a
    righty pro's non-hitting-hand wrist. y is unchanged; z rides along with
    the name swap (and is inert in the metric, Z_WEIGHT=0.0). Applying this
    twice is the identity.
    """
    out = []
    for pt in trajectory:
        landmarks = {}
        for name, v in pt['landmarks'].items():
            target = _MIRROR_SWAP.get(name, name)
            landmarks[target] = None if v is None else {'x': -v['x'], 'y': v['y'], 'z': v.get('z')}
        out.append({'t': pt['t'], 'landmarks': landmarks})
    return out
