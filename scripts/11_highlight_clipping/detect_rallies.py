"""
Detect rally (point) boundaries in a full match/practice video and clip
each rally out to its own file.

Reuses the existing swing-detection building blocks (already validated on
multi-minute compilation videos, not just short clips) rather than
inventing new detection logic:
  - extract_poses()                              scripts/02_pose_extraction
  - compute_wrist_velocity(), find_swing_peaks()  scripts/03_swing_detection
  - extract_clip()                                scripts/04_clip_extraction

Rally grouping is done on VERIFIED real shots, not raw wrist-velocity
peaks -- a raw peak can be camera fiddling or a ball bounce (see
scripts/16_shot_verification/'s module docstring for why that distinction
matters), and letting those anchor/extend a rally group produced rallies
padded around noise instead of actual play. Every candidate swing is run
through the same Claude teacher-student verifier already proven on saved
history (scripts/16_shot_verification/verify_shot_contact_verified.py),
and shot-typed via scripts/14_shot_classifier/ so serves -- which shouldn't
start or extend a rally, only forehand/backhand exchanges should -- are
excluded before grouping. No ball tracking beyond what verification
already does, no point-outcome detection -- reduced scope by design.

Usage:
  python detect_rallies.py <video_path> <output_dir> [--rally-gap SEC]

Output (stdout): JSON -- see detect_rallies() docstring.
On error: {"error": "..."}
"""
import sys
import os
import json
import argparse
import tempfile
import contextlib
import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '03_swing_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '04_clip_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '14_shot_classifier'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '16_shot_verification'))

from extract_poses import extract_poses
from detect_swings import compute_wrist_velocity, find_swing_peaks, THRESHOLD_PERCENTILE
from extract_clips import extract_clip
from verify_shot_contact import verify_swings
from verify_shot_contact_verified import get_verified_shot_contact
from classify_shot_verified import get_verified_shot_type

# Max gap (seconds) between consecutive swing peaks still considered part of
# the same rally -- a larger gap marks the boundary between points. This is
# a starting guess tuned on nothing but intuition about recreational point
# pacing; it MUST be sanity-checked against real match footage (see the
# module docstring) before being trusted, since the underlying swing
# detector itself was only ever validated on curated compilation videos.
RALLY_GAP_SEC = 6.0

# Opt-outs for the Claude teacher-student calls, both gated off by default
# (unchanged normal behaviour). Set when the caller has explicitly decided
# to accept the local, untrusted rule-based heuristics instead of Claude
# verification -- e.g. no API credits available.
SKIP_CONTACT_VERIFIER = os.environ.get('RALLYMAX_SKIP_CONTACT_VERIFIER') == '1'
SKIP_CLASSIFIER_VERIFIER = os.environ.get('RALLYMAX_SKIP_CLASSIFIER_VERIFIER') == '1'

# Reuses detect_swings.py's own tuned value so a single stroke is never
# double-counted as two swings.
MIN_SWING_GAP_SEC = 1.5

# Padding so a rally clip doesn't start/end mid-stroke.
PRE_PAD_SEC = 1.0
POST_PAD_SEC = 1.5

# Rallies with fewer swings than this are almost certainly noise (a single
# mis-detected "swing" with nothing around it) and are dropped.
MIN_RALLY_SWINGS = 2


def _as_classify_frames(frames):
    """
    02_pose_extraction/extract_poses.py (used here, for wrist-velocity
    swing detection) stores each frame's landmarks as a LIST indexed
    positionally; classify_shot.py expects the dict-keyed-by-joint-name
    shape compare_swing.extract_user_poses() produces. Both extractors
    write identical per-landmark fields (name/x/y/z/visibility) in the
    same LANDMARK_NAMES order, so this is a cheap reshape of data already
    in hand -- NOT a second pose-extraction pass (frames_fps=None would
    make classify() re-extract poses over the *entire source video* once
    per swing candidate, which is pathologically slow for a full match
    video with 100+ candidates -- confirmed live, killed after 7+ hours
    stuck redoing extraction for the same video over and over).
    """
    return [
        {'frame': f['frame'], 'timestamp': f['timestamp'],
         'landmarks': {lm['name']: lm for lm in f['landmarks']} if f['landmarks'] else None}
        for f in frames
    ]


def filter_to_real_rally_shots(video_path, swings, fps, frames, log_lock=None):
    """
    Runs every wrist-velocity candidate through the shot-contact verifier
    and, for real shots, the shot-type classifier -- keeping only verified
    real, non-serve swings so a rally group is built from actual
    forehand/backhand exchanges, not camera fiddling, ball bounces, or
    serves. Mutates nothing; returns a new filtered+annotated list.
    """
    verify_swings(video_path, swings, fps, frames=frames)
    classify_frames = _as_classify_frames(frames)

    kept = []
    for i, sw in enumerate(swings, 1):
        is_real_shot, verify_meta = get_verified_shot_contact(
            video_path, sw, fps, use_verifier=not SKIP_CONTACT_VERIFIER, log_lock=log_lock)
        if not is_real_shot:
            print(f'  swing {i}/{len(swings)} at {sw["peak_time"]:.1f}s: not a real shot, skipping'
                  f' ({verify_meta.get("reasoning", "")})', file=sys.stderr)
            continue

        shot_type = verify_meta.get('shot_type')
        if shot_type is None:
            # Teacher wasn't called (student already trusted, or the
            # verifier's skipped) -- classify separately, same as
            # analyze_rallies_parallel.py does. Reuses the already-extracted
            # poses (reshaped by _as_classify_frames above) instead of
            # letting classify() re-extract from scratch -- see that
            # function's docstring for why that matters.
            shot_type, _classify_meta = get_verified_shot_type(
                video_path, sw['peak_time'], use_verifier=not SKIP_CLASSIFIER_VERIFIER,
                frames_fps=(classify_frames, fps), log_lock=log_lock)

        if shot_type == 'serve':
            print(f'  swing {i}/{len(swings)} at {sw["peak_time"]:.1f}s: serve, excluded from rally grouping',
                  file=sys.stderr)
            continue

        sw['shot_type'] = shot_type
        sw['verify_source'] = verify_meta.get('source')
        kept.append(sw)

    return kept


def group_into_rallies(swings, max_gap_sec):
    """swings: chronologically-ordered list of dicts with 'peak_time'
    (find_swing_peaks walks frames in order, so this holds already).
    Returns a list of swing-groups, one per detected rally."""
    if not swings:
        return []
    rallies = [[swings[0]]]
    for sw in swings[1:]:
        gap = sw['peak_time'] - rallies[-1][-1]['peak_time']
        if gap > max_gap_sec:
            rallies.append([sw])
        else:
            rallies[-1].append(sw)
    return rallies


def detect_rallies(video_path, output_dir, rally_gap_sec=RALLY_GAP_SEC):
    os.makedirs(output_dir, exist_ok=True)

    print('  Extracting poses (slow step for a full match video)...', file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        pose_path = os.path.join(tmp, 'poses.json')
        # extract_poses() logs its progress with plain print() (stdout), but
        # this script's stdout is reserved for the final JSON result only
        # (Node's caller does a strict JSON.parse on it) -- redirect to
        # stderr for the duration of this call rather than touching the
        # shared extract_poses.py, which other pipeline stages call directly
        # from the command line and want stdout output from.
        with contextlib.redirect_stdout(sys.stderr):
            extract_poses(video_path, pose_path, sample_every=3)
        with open(pose_path) as f:
            pose_data = json.load(f)

    fps = pose_data['fps']
    total_frames = pose_data['total_frames']
    frames = pose_data['frames']

    print('  Computing wrist velocity / finding swing peaks...', file=sys.stderr)
    velocities = compute_wrist_velocity(frames)
    raw_swings = find_swing_peaks(velocities, frames, fps, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC)
    print(f'  {len(raw_swings)} raw swing candidates detected across the video', file=sys.stderr)

    print('  Verifying candidates are real shots (Claude teacher-student, per candidate)...', file=sys.stderr)
    swings = filter_to_real_rally_shots(video_path, raw_swings, fps, frames)
    print(f'  {len(swings)} verified real, non-serve swings remain', file=sys.stderr)

    groups = group_into_rallies(swings, rally_gap_sec)
    groups = [g for g in groups if len(g) >= MIN_RALLY_SWINGS]
    print(f'  Grouped into {len(groups)} rallies (>= {MIN_RALLY_SWINGS} swings each)', file=sys.stderr)

    cap = cv2.VideoCapture(video_path)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')

    rallies = []
    video_duration = total_frames / fps
    for i, group in enumerate(groups, 1):
        start_sec = max(0.0, group[0]['peak_time'] - PRE_PAD_SEC)
        end_sec = min(video_duration, group[-1]['peak_time'] + POST_PAD_SEC)
        start_frame = int(start_sec * fps)
        end_frame = min(total_frames - 1, int(end_sec * fps))

        out_path = os.path.join(output_dir, f'rally_{i:03d}.mp4')
        extract_clip(cap, start_frame, end_frame, out_path, fps, fourcc)
        print(f'  [{i}/{len(groups)}] {start_sec:.1f}s -> {end_sec:.1f}s ({len(group)} swings) -> {out_path}', file=sys.stderr)

        rallies.append({
            'rally_id': i,
            'start_sec': round(start_sec, 2),
            'end_sec': round(end_sec, 2),
            'duration_sec': round(end_sec - start_sec, 2),
            'swing_count': len(group),
            'clip_path': out_path,
        })

    cap.release()

    return {
        'video': os.path.basename(video_path),
        'total_duration_sec': round(video_duration, 1),
        'swings_candidates': len(raw_swings),
        'swings_verified': len(swings),
        'rallies_detected': len(rallies),
        'rally_gap_sec': rally_gap_sec,
        'rallies': rallies,
    }


def main():
    parser = argparse.ArgumentParser(description='Detect rally boundaries in a match video and clip each one out')
    parser.add_argument('video', help='Path to full match/practice video')
    parser.add_argument('output_dir', help='Directory to write rally clips into')
    parser.add_argument('--rally-gap', type=float, default=RALLY_GAP_SEC, help='Max seconds between swings to still count as the same rally')
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(json.dumps({'error': f'Video not found: {args.video}'}))
        sys.exit(1)

    try:
        result = detect_rallies(args.video, args.output_dir, rally_gap_sec=args.rally_gap)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
