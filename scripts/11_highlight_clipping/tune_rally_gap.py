"""
Offline tuning tool for detect_rallies.py's RALLY_GAP_SEC (and a sanity
sweep over detect_swings.py's THRESHOLD_PERCENTILE) against real match
footage, scored against Jack's boundary_note ground truth from
HighlightReviewScreen instead of guessing.

Unlike detect_rallies.py's production path, this persists the expensive
pose-extraction step to disk once per video (production throws it away in a
tempfile.TemporaryDirectory() -- fine when you only ever group once, wasteful
here where the same swings get regrouped many times). Pose extraction over a
full match video is the slow part; regrouping swings into rallies is nearly
free, so every value in the sweep below reuses the same cached extraction.

Usage:
  python tune_rally_gap.py <video_path> <job_id> [--gaps 6,9,12,15] [--percentiles 85]

<job_id> is the highlight_jobs id whose rally_clips rows already carry
boundary_note values ('ok' | 'cut_off_early' | 'should_split' |
'started_too_late') from the review screen -- pulled read-only from
backend/data/app.db. Clips with no boundary_note are ignored (Jack hasn't
reviewed them yet).

Scoring logic, per candidate (rally_gap_sec, threshold_percentile) pair:
  - 'ok':             candidate should reproduce the same rally boundaries
                       (same first/last swing) as the original clip -- a
                       match counts as a hit, any change is a miss.
  - 'should_split':   the clip's swing group should now be split into 2+
                       groups under the candidate -- only possible if the
                       gap is smaller than whatever internal gap already let
                       those swings merge; a real split counts as a hit.
  - 'cut_off_early':  the clip's swing group should now be merged with its
                       chronological neighbor -- only possible if the gap is
                       large enough to bridge the boundary; a real merge
                       counts as a hit.
  - 'started_too_late': a start-boundary problem (PRE_PAD_SEC, not this
                       sweep's RALLY_GAP_SEC/THRESHOLD_PERCENTILE) --
                       collected as ground truth but excluded from scoring
                       here; see score_candidate().
Score = hits / scored labeled clips for that job. Pick the (gap, percentile) pair
with the highest score; ties broken toward values closest to the current
defaults (smallest change, least risk of new regressions elsewhere).
"""
import sys
import os
import sqlite3
import argparse
import tempfile
import contextlib
import json

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '03_swing_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '11_highlight_clipping'))

from paths import BACKEND_DIR  # noqa: E402
from extract_poses import extract_poses  # noqa: E402
from detect_swings import compute_wrist_velocity, find_swing_peaks, MIN_SWING_GAP_SEC  # noqa: E402
from detect_rallies import group_into_rallies, MIN_RALLY_SWINGS, PRE_PAD_SEC, POST_PAD_SEC  # noqa: E402

DB_PATH = os.path.join(BACKEND_DIR, 'data', 'app.db')

DEFAULT_GAPS = [6.0, 9.0, 12.0, 15.0]
DEFAULT_PERCENTILES = [85]

# Cache extracted poses next to this script so re-running the sweep (or
# adding more candidates later) never re-pays pose extraction.
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.tuning_cache')


def get_or_extract_poses(video_path):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_key = os.path.splitext(os.path.basename(video_path))[0]
    cache_path = os.path.join(CACHE_DIR, f'{cache_key}_poses.json')
    if os.path.exists(cache_path):
        print(f'  Using cached pose extraction: {cache_path}', file=sys.stderr)
        with open(cache_path) as f:
            return json.load(f)

    print(f'  No cache found -- extracting poses from {video_path} (slow)...', file=sys.stderr)
    with contextlib.redirect_stdout(sys.stderr):
        extract_poses(video_path, cache_path, sample_every=3)
    with open(cache_path) as f:
        return json.load(f)


def load_labeled_clips(job_id):
    """Read-only DB access -- must not conflict with the live Node server's
    writes, and this script never needs to write to app.db itself."""
    conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, start_sec, end_sec, boundary_note FROM rally_clips '
        'WHERE job_id = ? AND boundary_note IS NOT NULL ORDER BY start_sec',
        (job_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def swings_to_groups_with_bounds(groups):
    """groups: list of swing-groups (each a list of swing dicts) -- returns
    parallel (start_sec, end_sec) padded bounds matching detect_rallies.py's
    own padding logic, so they line up with rally_clips.start_sec/end_sec."""
    bounds = []
    for g in groups:
        start_sec = max(0.0, g[0]['peak_time'] - PRE_PAD_SEC)
        end_sec = g[-1]['peak_time'] + POST_PAD_SEC
        bounds.append((start_sec, end_sec))
    return bounds


def find_matching_group_index(bounds, clip_start_sec, tolerance=2.0):
    """Original clip -> the regrouped rally whose start lines up, within a
    tolerance (padding/frame-rounding can shift start_sec by a fraction of a
    second even when nothing structural changed)."""
    for i, (start_sec, _) in enumerate(bounds):
        if abs(start_sec - clip_start_sec) <= tolerance:
            return i
    return None


def score_candidate(labeled_clips, groups, bounds):
    hits, total = 0, 0
    for clip in labeled_clips:
        # boundary_note is a comma-joined set of independently-toggled values
        # since the review screen went multi-select (a clip can be wrong on
        # both ends at once, e.g. 'started_too_late,cut_off_early') -- a bare
        # single value like 'ok' still splits fine into a one-element set.
        notes = set((clip['boundary_note'] or '').split(','))
        idx = find_matching_group_index(bounds, clip['start_sec'])

        # started_too_late has no lever in this sweep -- this sweep only
        # varies RALLY_GAP_SEC/THRESHOLD_PERCENTILE, neither of which can
        # move where a clip *starts* (that's PRE_PAD_SEC, a separate untuned
        # constant -- see module docstring). Score whatever ELSE is tagged
        # alongside it (cut_off_early can coexist), and skip entirely only if
        # it's the sole note -- scoring it here would count as a miss against
        # every candidate regardless of gap value, unfairly deflating every
        # score for a problem this sweep has no lever to fix.
        scorable = notes - {'started_too_late'}
        if not scorable:
            continue

        total += 1
        if 'ok' in scorable:
            # Same clip should still exist with (about) the same end_sec.
            if idx is not None and abs(bounds[idx][1] - clip['end_sec']) <= 2.0:
                hits += 1
        elif 'should_split' in scorable:
            # No single regrouped rally should span the old clip's full
            # start->end range unchanged -- if it still does, nothing split.
            if idx is None or abs(bounds[idx][1] - clip['end_sec']) > 2.0:
                hits += 1
        elif 'cut_off_early' in scorable:
            # The regrouped rally starting near this clip should now extend
            # further than the old end_sec (merged with what came next).
            if idx is not None and bounds[idx][1] > clip['end_sec'] + 2.0:
                hits += 1
    return hits, total


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('video')
    parser.add_argument('job_id', type=int)
    parser.add_argument('--gaps', default=','.join(str(g) for g in DEFAULT_GAPS))
    parser.add_argument('--percentiles', default=','.join(str(p) for p in DEFAULT_PERCENTILES))
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f'Video not found: {args.video}', file=sys.stderr)
        sys.exit(1)

    gaps = [float(g) for g in args.gaps.split(',')]
    percentiles = [int(p) for p in args.percentiles.split(',')]

    labeled_clips = load_labeled_clips(args.job_id)
    if not labeled_clips:
        print(f'No boundary_note-labeled clips found for job {args.job_id} -- '
              f'have this job\'s rallies been reviewed in the app yet?', file=sys.stderr)
        sys.exit(1)
    print(f'  {len(labeled_clips)} labeled clips loaded for job {args.job_id} '
          f'({sum(1 for c in labeled_clips if c["boundary_note"] == "ok")} ok, '
          f'{sum(1 for c in labeled_clips if c["boundary_note"] == "should_split")} should_split, '
          f'{sum(1 for c in labeled_clips if c["boundary_note"] == "cut_off_early")} cut_off_early)',
          file=sys.stderr)

    pose_data = get_or_extract_poses(args.video)
    fps = pose_data['fps']
    frames = pose_data['frames']
    velocities = compute_wrist_velocity(frames)

    results = []
    for percentile in percentiles:
        swings = find_swing_peaks(velocities, frames, fps, percentile, MIN_SWING_GAP_SEC)
        print(f'\n  percentile={percentile}: {len(swings)} swings detected', file=sys.stderr)

        for gap in gaps:
            groups = group_into_rallies(swings, gap)
            groups = [g for g in groups if len(g) >= MIN_RALLY_SWINGS]
            bounds = swings_to_groups_with_bounds(groups)

            durations = [end - start for start, end in bounds]
            avg_duration = sum(durations) / len(durations) if durations else 0.0
            avg_swings = sum(len(g) for g in groups) / len(groups) if groups else 0.0

            hits, total = score_candidate(labeled_clips, groups, bounds)
            score = hits / total if total else 0.0

            results.append({
                'percentile': percentile, 'gap_sec': gap,
                'rally_count': len(groups), 'avg_duration_sec': round(avg_duration, 1),
                'avg_swings': round(avg_swings, 1), 'score': round(score, 3),
                'hits': hits, 'total_labeled': total,
            })
            print(f'    gap={gap:>5.1f}s -> {len(groups):>3} rallies, '
                  f'avg {avg_duration:5.1f}s / {avg_swings:.1f} swings, '
                  f'boundary score {hits}/{total} ({score:.0%})', file=sys.stderr)

    best = max(results, key=lambda r: (r['score'], -abs(r['gap_sec'] - 6.0)))
    print(f'\nBest candidate: percentile={best["percentile"]}, gap_sec={best["gap_sec"]} '
          f'(boundary score {best["score"]:.0%})', file=sys.stderr)
    print(json.dumps({'results': results, 'best': best}))


if __name__ == '__main__':
    main()
