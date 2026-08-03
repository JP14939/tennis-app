"""
Compare two pose trajectories (sequences of normalised landmark snapshots
across a swing) using Dynamic Time Warping — aligns sequences that differ in
length/speed, which a flattened fixed-length vector can't do. This replaces
comparing 3 fixed snapshots (backswing/contact/followthrough) with comparing
the full ~20fps motion path.
"""
import math


def _frame_dist(a, b, key_landmarks):
    """Average per-landmark euclidean distance between two landmark dicts."""
    total = 0.0
    n = 0
    for name in key_landmarks:
        pa, pb = a.get(name), b.get(name)
        if pa is None or pb is None:
            continue
        total += math.sqrt((pa['x'] - pb['x']) ** 2 + (pa['y'] - pb['y']) ** 2)
        n += 1
    if n == 0:
        return 1.5  # no shared landmarks this frame pair — treat as a poor match
    return total / n


def dtw_distance(traj_a, traj_b, key_landmarks):
    """
    DTW distance between two trajectories, normalised by path length so it's
    comparable across swings of different durations. Lower = more similar.
    """
    n, m = len(traj_a), len(traj_b)
    if n == 0 or m == 0:
        return float('inf')

    INF = float('inf')
    dtw = [[INF] * (m + 1) for _ in range(n + 1)]
    dtw[0][0] = 0.0

    for i in range(1, n + 1):
        li = traj_a[i - 1]['landmarks']
        row, prev_row = dtw[i], dtw[i - 1]
        for j in range(1, m + 1):
            cost = _frame_dist(li, traj_b[j - 1]['landmarks'], key_landmarks)
            row[j] = cost + min(prev_row[j], row[j - 1], prev_row[j - 1])

    return dtw[n][m] / max(n, m)


def contact_landmarks(trajectory):
    """The trajectory snapshot closest to t=0 (contact)."""
    if not trajectory:
        return {}
    return min(trajectory, key=lambda p: abs(p['t']))['landmarks']
