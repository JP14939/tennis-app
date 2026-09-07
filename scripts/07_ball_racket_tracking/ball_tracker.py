"""
Shared ball-trajectory tracking: a constant-velocity Kalman filter over
raw per-frame YOLO ball detections (racket_tracker.py's track_racket_and_ball).

Replaces plain gap-only linear interpolation with one continuous tracked
state (position + velocity): a missing frame is bridged by prediction
(not just linear fill), and a detection that doesn't fit the ball's
established motion -- a stray ball-shaped object elsewhere in frame, not
the one actually in play -- is rejected rather than snapped to. This is
the continuous, physics-aware generalization of the "if it isn't moving,
it's not the ball being played" rule used to audit the manual ball labels
(see audit_ball_label_motion.py) -- there it's a hard per-clip threshold on
already-collected labels; here it's a live, per-frame consistency check
against a moving estimate.

Deliberately constant-velocity, not gravity/parabola-aware -- simpler to
validate first; a physics-informed post-contact flight model is a real
future refinement once this version is proven on real clips (see the plan
that scoped this module).
"""
import numpy as np

# How many standard deviations a measurement may deviate from the filter's
# predicted position before it's rejected as an outlier (a different
# ball-shaped object, not the one being tracked) rather than accepted.
OUTLIER_GATE_SIGMAS = 3.0

# Process noise: how much we expect true (unmodeled) velocity change between
# frames -- small, since a real ball's velocity changes smoothly frame to
# frame except right at contact (which this constant-velocity model doesn't
# special-case; see the deferred physics-informed variant).
PROCESS_VAR = 4.0
# Measurement noise: expected pixel-space jitter in a real YOLO detection's
# box center.
MEASUREMENT_VAR = 16.0


class BallTracker:
    """
    State: [x, y, vx, vy] in original-frame pixel space. One predict+update
    step per frame; call update(None) for a frame with no accepted
    detection to advance via pure prediction.
    """

    def __init__(self, x, y, process_var=PROCESS_VAR, measurement_var=MEASUREMENT_VAR):
        self.x = np.array([x, y, 0.0, 0.0])
        # Large initial velocity uncertainty -- first frame gives no
        # velocity evidence yet.
        self.P = np.diag([measurement_var, measurement_var, 1e3, 1e3])
        self.process_var = process_var
        self.measurement_var = measurement_var
        self.last_d2 = None

    def _predict(self):
        F = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ])
        q = self.process_var
        Q = np.diag([q, q, q, q])
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def _mahalanobis_gate(self, z):
        H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
        R = np.diag([self.measurement_var, self.measurement_var])
        S = H @ self.P @ H.T + R
        y = z - H @ self.x
        d2 = y.T @ np.linalg.solve(S, y)
        return d2, H, R, S, y

    def update(self, measurement):
        """measurement: (x, y) or None. Returns (x, y, accepted: bool) --
        accepted is False for a rejected-as-outlier or missing measurement,
        both of which still advance the tracked state via prediction alone.

        Side effect: sets self.last_d2 to the Mahalanobis distance^2 of the
        measurement against the pre-update prediction (None when measurement
        is None) so callers that want the gate diagnostic don't have to
        recompute it."""
        self._predict()
        self.last_d2 = None
        if measurement is None:
            return self.x[0], self.x[1], False

        z = np.array(measurement)
        d2, H, R, S, y = self._mahalanobis_gate(z)
        self.last_d2 = float(d2)
        # d2 is chi-squared distributed (2 DoF); OUTLIER_GATE_SIGMAS^2 is a
        # generous approximation of "how many sigma away" in the isotropic
        # case, consistent with this module's simple diagonal-noise model.
        if d2 > OUTLIER_GATE_SIGMAS ** 2:
            return self.x[0], self.x[1], False

        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ H) @ self.P
        return self.x[0], self.x[1], True


def track_ball_states(detections, start_frame, end_frame, center_fn,
                      max_gap_frames=4, predict_only_frames=(), extrapolate_frames=0):
    """
    Per-frame Kalman filter state over [start_frame, end_frame], the engine
    track_ball() is a thin wrapper over. Same streaming gap logic (see
    track_ball's docstring): emit rows from the first usable measurement
    onward, break the track once misses exceed max_gap_frames in a row, and
    let a later real detection start a fresh track.

    center_fn: e.g. racket_tracker.py's _center_in_original_space -- a
    parameter rather than an import to keep this module free of a circular
    dependency on its only current caller.

    predict_only_frames: iterable of frame numbers to force-coast -- feed the
    filter measurement=None there even when a detection exists, so a caller
    (the ROI re-detector's pass 2) can read the filter's own prediction at a
    frame whose pass-1 detection it wants to re-judge.

    extrapolate_frames: after end_frame, emit N extra pure-prediction rows
    (measurement always None, gap cap bypassed) as long as a live track
    reaches end_frame -- lets a caller see where a constant-velocity ball
    would have gone just past the window.

    Returns a list of dicts, one per emitted frame:
      frame          -- int
      pos            -- (x, y) filter estimate (raw measurement on the init frame)
      vel            -- (vx, vy) filter velocity estimate
      cov            -- 2x2 position covariance (list of lists), P[:2, :2]
      accepted       -- bool: a measurement was present and passed the gate
      predicted      -- bool: pos came from prediction alone (not accepted == True
                        except the init frame, where both are False/measurement)
      measurement    -- (x, y) fed to the filter this frame, or None
      mahalanobis_d2 -- gate distance^2 of measurement vs prediction, or None
    """
    frame_dets = {d['frame']: d for d in detections if start_frame <= d['frame'] <= end_frame}
    predict_only = set(predict_only_frames)

    tracker = None
    consecutive_misses = 0
    states = []
    last_emitted_frame = None
    for frame in range(start_frame, end_frame + 1):
        det = frame_dets.get(frame)
        measurement = center_fn(det['ball_box'], det) if det and det['ball_box'] else None
        if frame in predict_only:
            measurement = None

        if tracker is None:
            if measurement is None:
                continue  # nothing to initialize from yet
            tracker = BallTracker(*measurement)
            consecutive_misses = 0
            states.append({
                'frame': frame,
                'pos': tuple(measurement),
                'vel': (float(tracker.x[2]), float(tracker.x[3])),
                'cov': tracker.P[:2, :2].tolist(),
                'accepted': False,
                'predicted': False,
                'measurement': tuple(measurement),
                'mahalanobis_d2': None,
            })
            last_emitted_frame = frame
            continue

        x, y, accepted = tracker.update(measurement)
        consecutive_misses = 0 if accepted else consecutive_misses + 1
        if consecutive_misses > max_gap_frames:
            tracker = None  # gap too long to keep predicting through
            continue
        states.append({
            'frame': frame,
            'pos': (float(x), float(y)),
            'vel': (float(tracker.x[2]), float(tracker.x[3])),
            'cov': tracker.P[:2, :2].tolist(),
            'accepted': accepted,
            'predicted': not accepted,
            'measurement': tuple(measurement) if measurement is not None else None,
            'mahalanobis_d2': tracker.last_d2,
        })
        last_emitted_frame = frame

    if extrapolate_frames and tracker is not None and last_emitted_frame == end_frame:
        for frame in range(end_frame + 1, end_frame + 1 + extrapolate_frames):
            x, y, _ = tracker.update(None)
            states.append({
                'frame': frame,
                'pos': (float(x), float(y)),
                'vel': (float(tracker.x[2]), float(tracker.x[3])),
                'cov': tracker.P[:2, :2].tolist(),
                'accepted': False,
                'predicted': True,
                'measurement': None,
                'mahalanobis_d2': None,
            })

    return states


def track_ball(detections, start_frame, end_frame, center_fn, max_gap_frames=4):
    """
    Tracks the ball across [start_frame, end_frame] using every frame's
    ball_box (via center_fn, e.g. racket_tracker.py's
    _center_in_original_space -- kept as a parameter rather than imported
    to avoid a circular import, since racket_tracker.py is this module's
    only current caller).

    Returns [(frame, (x, y)), ...] -- matches _interpolated_ball_track()'s
    existing shape so it's a drop-in. Predicts through up to max_gap_frames
    CONSECUTIVE missing/rejected measurements in a row (the ball vanishing
    for a frame or two is expected -- see _find_gap_contact's comment); once
    misses exceed that streak, prediction stops (no real basis left to guess
    where the ball went) and the track breaks there -- a later real
    detection starts a fresh track rather than resuming the stale one. This
    is a streaming/sliding cap, not a lookahead at total gap length: a very
    long gap gets bridged for its first max_gap_frames frames on faith, then
    abandoned, rather than being rejected as a whole up front (the tracker
    can't know how long a gap will run until it's already inside it).

    Thin wrapper over track_ball_states -- the position column of its rows.
    """
    return [(s['frame'], s['pos'])
            for s in track_ball_states(detections, start_frame, end_frame,
                                       center_fn, max_gap_frames)]
