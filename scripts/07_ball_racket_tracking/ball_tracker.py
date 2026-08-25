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
        both of which still advance the tracked state via prediction alone."""
        self._predict()
        if measurement is None:
            return self.x[0], self.x[1], False

        z = np.array(measurement)
        d2, H, R, S, y = self._mahalanobis_gate(z)
        # d2 is chi-squared distributed (2 DoF); OUTLIER_GATE_SIGMAS^2 is a
        # generous approximation of "how many sigma away" in the isotropic
        # case, consistent with this module's simple diagonal-noise model.
        if d2 > OUTLIER_GATE_SIGMAS ** 2:
            return self.x[0], self.x[1], False

        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ H) @ self.P
        return self.x[0], self.x[1], True


def track_ball(detections, start_frame, end_frame, center_fn, max_gap_frames=3):
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
    """
    frame_dets = {d['frame']: d for d in detections if start_frame <= d['frame'] <= end_frame}
    if not frame_dets:
        return []

    tracker = None
    consecutive_misses = 0
    track = []
    for frame in range(start_frame, end_frame + 1):
        det = frame_dets.get(frame)
        measurement = center_fn(det['ball_box'], det) if det and det['ball_box'] else None

        if tracker is None:
            if measurement is None:
                continue  # nothing to initialize from yet
            tracker = BallTracker(*measurement)
            track.append((frame, tuple(measurement)))
            continue

        x, y, accepted = tracker.update(measurement)
        consecutive_misses = 0 if accepted else consecutive_misses + 1
        if consecutive_misses > max_gap_frames:
            tracker = None  # gap too long to keep predicting through
            continue
        track.append((frame, (float(x), float(y))))

    return track
