"""
Short-gap interpolation for per-frame tracked series (racket keypoints, ball
centre, pose landmarks) before they're serialised into an overlay payload.

When a per-frame detector (YOLO keypoints, MediaPipe) drops out for a frame
or two, the overlay trail just breaks there. This fills a *bounded* run of
missing samples -- one that has real values on BOTH sides and spans no more
than `max_gap_seconds` of wall-clock time -- with a local quadratic fit
(linear when only two anchors are available, or when the fitting anchors
straddle too wide a baseline to trust a curve through). Longer gaps, and any
leading/trailing gap, are left untouched: there's no real basis to guess
where the thing went, and extrapolating past the first/last real detection
fabricates motion.

Same np.polyfit/np.polyval idiom already used for velocity fitting in
scripts/16_shot_verification/verify_shot_contact.py and
scripts/07_ball_racket_tracking/ball_speed.py -- here it's a positional
gap-fill, not a derivative.

The cap is in *seconds*, not samples, on purpose: the overlay builders don't
all sample at the same rate (the racket/pose overlays keep every 3rd source
frame, the ball overlay keeps every frame), so a sample-count cap would mean
a 3x tighter bridge on the ball path than on the racket path for the same
real occlusion. DEFAULT_MAX_GAP_SECONDS=0.25 is a deliberately generous read
of "a couple of frames" (~7 frames at 30fps) -- tune it down if a bridged arc
visibly over-reaches a real tracking loss.
"""
import numpy as np

# Bridge a detection dropout only if the real samples bracketing it are no
# more than this far apart in time.
DEFAULT_MAX_GAP_SECONDS = 0.25

# Real samples to fit through on each side of a gap.
_ANCHORS_PER_SIDE = 2

# A quadratic through 4 points genuinely tracks a curving path better than a
# chord for a *single* missing sample (~one frame). Across 2+ missing samples
# it starts bowing/overshooting between the real points -- worst exactly on a
# fast curving wrist/racket arc, where the hole is widest and the motion is
# least linear. So: quadratic only for a 1-sample hole, straight line for
# anything longer.
_MAX_QUADRATIC_GAP_SAMPLES = 1


def _median_spacing(ts):
    if len(ts) < 2:
        return 0.0
    diffs = sorted(ts[i + 1] - ts[i] for i in range(len(ts) - 1))
    return diffs[len(diffs) // 2]


def _gap_runs(values):
    """Yield (start, end) index pairs (inclusive) of each maximal run of
    None in `values` that is bounded by a non-None on both sides. Leading
    and trailing None runs are skipped -- nothing to interpolate between."""
    n = len(values)
    i = 0
    while i < n and values[i] is None:  # skip a leading None run
        i += 1
    while i < n:
        if values[i] is None:
            start = i
            while i < n and values[i] is None:
                i += 1
            if i < n:  # bounded on the right (left is guaranteed by construction)
                yield (start, i - 1)
        else:
            i += 1


def interpolate_series(ts, values, max_gap_seconds=DEFAULT_MAX_GAP_SECONDS):
    """Return a copy of `values` with each bounded, short-enough gap of
    consecutive None entries filled by a local polynomial fit.

    ts:     strictly increasing sample axis in seconds (frame numbers work
            too -- the cap is then just "units of ts"), same length as
            `values`.
    values: list of float | None.
    """
    if len(ts) != len(values):
        raise ValueError('ts and values must be the same length')
    out = list(values)
    spacing = _median_spacing(ts)
    # allow the cap to include the gap's own bracketing sample step, so a cap
    # of 0.25s doesn't reject a gap whose brackets are 0.25s + one frame apart
    tolerance = spacing * 0.5

    for start, end in _gap_runs(values):
        gap_span = ts[end + 1] - ts[start - 1]
        if gap_span > max_gap_seconds + tolerance:
            continue

        left = [j for j in range(start - 1, -1, -1) if values[j] is not None][:_ANCHORS_PER_SIDE]
        right = [j for j in range(end + 1, len(values)) if values[j] is not None][:_ANCHORS_PER_SIDE]
        anchors = sorted(left + right)
        if len(anchors) < 2:
            continue

        missing = end - start + 1
        if missing <= _MAX_QUADRATIC_GAP_SAMPLES and len(anchors) >= 3:
            fit_idx = anchors
            degree = 2
        else:
            # straight line through the innermost real sample on each side
            fit_idx = [max(left), min(right)] if left and right else anchors[:2]
            degree = 1

        at = np.array([ts[j] for j in fit_idx], dtype=float)
        av = np.array([values[j] for j in fit_idx], dtype=float)
        t0 = at[0]  # shift x so the fit is well-conditioned regardless of absolute ts
        coeffs = np.polyfit(at - t0, av, degree)
        for j in range(start, end + 1):
            out[j] = float(np.polyval(coeffs, ts[j] - t0))

    return out


def interpolate_named_points(frames, point_names, key='points',
                             max_gap_seconds=DEFAULT_MAX_GAP_SECONDS):
    """Gap-fill a list of per-frame dicts in place.

    Each frame is `{'t': <seconds>, key: {name: {'x':.., 'y':..} | None, ...}}`
    (the shape build_racket_overlay_trajectory / build_overlay_trajectory
    produce). Every name in `point_names` has its x and y series interpolated
    independently. A frame whose point was None but sits in a filled gap gets
    a fresh `{'x':.., 'y':..}` dict; points outside a fillable gap stay None.
    """
    ts = [f['t'] for f in frames]
    for name in point_names:
        xs = [(_pt(f, key, name) or {}).get('x') for f in frames]
        ys = [(_pt(f, key, name) or {}).get('y') for f in frames]
        fx = interpolate_series(ts, xs, max_gap_seconds)
        fy = interpolate_series(ts, ys, max_gap_seconds)
        for i, f in enumerate(frames):
            if _pt(f, key, name) is None and fx[i] is not None and fy[i] is not None:
                f[key][name] = {'x': fx[i], 'y': fy[i]}
    return frames


def _pt(frame, key, name):
    return frame.get(key, {}).get(name)
