"""
Multi-feature outlier-detection calibration for vertical camera elevation.

Treats the 631 pro database entries as a reference "normal" population and
asks: on a combination of several weak signals (none of which separated
known-good from known-bad footage on its own, per the earlier single-feature
attempt), do the 2 known-elevated real videos land as clear outliers, or do
they sit inside the pro population's own spread?

This needs no ground-truth angle labels -- it's unsupervised: characterize
"normal" from the pro database's own distribution (median + MAD per feature,
robust to outliers given the small/messy sample), score every entry by how
many combined standard-deviations-equivalent it sits from that normal, and
see where the known-elevated videos land on the same scale.

Usage:
  python calibrate_elevation_outlier.py
"""
import json
import statistics

DB_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'
KNOWN_ELEVATED_PATH = r'C:\Users\jackp\tennis_app\data\runtime\known_elevated_features.json'

FEATURE_KEYS = ['post_height_frac', 'elevation_gap', 'net_apparent_ratio', 'net_y', 'player_net_offset', 'player_vis']

# 1.4826 * MAD approximates a standard deviation for normally-distributed data
# -- standard robust-statistics scaling constant, not a tuned/arbitrary one.
MAD_SCALE = 1.4826


def median_absolute_deviation(values, median):
    return statistics.median([abs(v - median) for v in values])


def compute_feature_stats(entries):
    """Per-feature (median, robust_std) computed only from entries where that feature exists."""
    stats = {}
    for key in FEATURE_KEYS:
        values = [e['elevation_features'][key] for e in entries
                  if e.get('elevation_features', {}).get(key) is not None]
        if len(values) < 10:  # not enough data to trust a distribution
            stats[key] = None
            continue
        median = statistics.median(values)
        mad = median_absolute_deviation(values, median)
        robust_std = mad * MAD_SCALE
        stats[key] = (median, robust_std if robust_std > 1e-6 else None)
    return stats


def anomaly_score(features, stats):
    """Sum of |z-score| across whichever features are present, using robust stats.
    Returns (score, n_features_used) -- a score from 1 feature isn't as trustworthy
    as one from 5, so n_features_used matters for interpreting the result."""
    total = 0.0
    n = 0
    for key in FEATURE_KEYS:
        val = features.get(key)
        stat = stats.get(key)
        if val is None or stat is None or stat[1] is None:
            continue
        median, robust_std = stat
        total += abs(val - median) / robust_std
        n += 1
    return total, n


def percentile(sorted_values, pct):
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * pct / 100))
    return sorted_values[idx]


if __name__ == '__main__':
    with open(DB_PATH) as f:
        db = json.load(f)
    with open(KNOWN_ELEVATED_PATH) as f:
        known_elevated = json.load(f)

    entries = db['entries']
    stats = compute_feature_stats(entries)

    print('Per-feature stats (median, robust_std) from pro database:')
    for key in FEATURE_KEYS:
        print(f'  {key}: {stats[key]}')

    pro_scores = []
    for entry in entries:
        features = entry.get('elevation_features', {})
        score, n = anomaly_score(features, stats)
        if n > 0:
            pro_scores.append((score, n))
            entry['elevation_anomaly_score'] = round(score, 3)
            entry['elevation_anomaly_n_features'] = n
        else:
            entry['elevation_anomaly_score'] = None
            entry['elevation_anomaly_n_features'] = 0

    with open(DB_PATH, 'w') as f:
        json.dump(db, f)

    scores_only = sorted(s for s, n in pro_scores)
    print(f'\nPro database anomaly scores: n={len(scores_only)}')
    print(f'  min={scores_only[0]:.3f} max={scores_only[-1]:.3f}')
    print(f'  median={statistics.median(scores_only):.3f}')
    for pct in (50, 75, 90, 95, 99):
        print(f'  p{pct}={percentile(scores_only, pct):.3f}')

    print('\nKnown-elevated videos:')
    for item in known_elevated:
        score, n = anomaly_score(item['features'], stats)
        # Where does this score rank against the pro distribution?
        rank_pct = 100 * sum(1 for s in scores_only if s <= score) / len(scores_only)
        print(f"  {item['video']}: score={score:.3f} (n_features={n}) "
              f"-> {rank_pct:.1f}th percentile of pro distribution")

    print('\n=== Verdict ===')
    print('If known-elevated videos scored above ~p90-p95 of the pro distribution,')
    print('that is a usable calibrated cutoff. If they scored within the bulk')
    print('(below p75 or so), the multi-feature combination did not separate the')
    print('groups either -- report that honestly rather than picking a cutoff that')
    print('would also flag a large fraction of legitimate pro footage.')
