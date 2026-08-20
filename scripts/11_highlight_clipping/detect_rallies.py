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
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))

from extract_poses import extract_poses
from detect_swings import compute_wrist_velocity, find_swing_peaks, THRESHOLD_PERCENTILE
from extract_clips import extract_clip
from verify_shot_contact import verify_swings
from verify_shot_contact_verified import get_verified_shot_contact
from classify_shot_verified import get_verified_shot_type
from classify_shot import classify, classify_ml
from shot_classifier_training_log import log_example as log_rule_classifier_example
import shot_classifier_ml_training_log as classifier_ml_log
from video_io import reencode_to_h264

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


def _log_classifiers_against_known_teacher_pick(video_path, peak_time, teacher_pick, classify_frames, fps, log_lock):
    """
    Runs both candidate students (the rule-based classify() and the
    trained classify_ml(), if a model exists) locally -- free, no Claude
    call -- and logs each against a shot_type the teacher (Claude) already
    answered elsewhere in this same request, so a real verdict that would
    otherwise go unused for classifier training gets used. Never lets a
    student-side failure (e.g. no trained model yet) block the caller.
    """
    try:
        rule_result = classify(video_path, peak_time, frames_fps=(classify_frames, fps))
        log_rule_classifier_example(
            rule_result['scores'], rule_result['shot_type'], teacher_pick,
            rule_result['shot_type'] == teacher_pick, lock=log_lock,
            clip_path=video_path, contact_frame=round(peak_time * fps))
    except Exception as e:
        print(f'  rule-based classifier logging failed: {e}', file=sys.stderr)

    try:
        ml_result = classify_ml(video_path, peak_time, frames_fps=(classify_frames, fps))
        classifier_ml_log.log_example(
            ml_result['scores'], ml_result['shot_type'], teacher_pick,
            ml_result['shot_type'] == teacher_pick, lock=log_lock,
            clip_path=video_path, contact_frame=round(peak_time * fps))
    except Exception:
        pass  # no trained model yet, or it failed on this swing -- not fatal, same as classify_shot_verified.py's own handling


def filter_to_real_rally_shots(video_path, swings, fps, frames, log_lock=None):
    """
    Runs every wrist-velocity candidate through the shot-contact verifier
    and, for real shots, the shot-type classifier -- keeping every verified
    real shot (serves included, tagged shot_type='serve') in chronological
    order. Serves themselves are filtered back out downstream by
    apply_serve_gate(), which also needs to SEE them to know when a point
    has legitimately opened -- unlike before, they can't just be dropped
    here. Mutates nothing; returns a new filtered+annotated list.
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
        elif verify_meta.get('source') == 'claude_verified':
            # The contact verifier's combined call already answered
            # shot_type -- confirmed live 2026-08-19 this is the common
            # case, which means get_verified_shot_type() above (the only
            # place that logs to the classifier training logs) almost
            # never actually runs, so a real, already-paid-for Claude
            # verdict was going unused for classifier training. Log both
            # candidate students' LOCAL (free -- no extra Claude call)
            # predictions against this same verdict instead of wasting it.
            # (This branch compared against the literal string 'claude'
            # until 2026-08-19, but get_verified_shot_contact() actually
            # returns 'claude_verified' on a real call -- so it never fired;
            # 108 real Claude calls on IMG_5822.MOV only produced 1 logged
            # training example before this fix.)
            _log_classifiers_against_known_teacher_pick(
                video_path, sw['peak_time'], shot_type, classify_frames, fps, log_lock)

        sw['shot_type'] = shot_type
        sw['verify_source'] = verify_meta.get('source')
        kept.append(sw)

    return kept


def apply_serve_gate(classified_swings, rally_gap_sec):
    """
    No groundstroke should be confirmed as a real rally shot until a serve
    has opened the point -- a shot can't happen without one coming before
    it. Walks the chronologically-ordered, already-verified+classified
    swing list (serves included -- see filter_to_real_rally_shots()) and
    keeps a non-serve shot only once a serve has been seen since the last
    point boundary.

    Doesn't need to know WHICH side served, or whether a given serve was
    "first" or "second" (no fault/in-out detection exists to tell) -- a
    later serve simply re-opens the gate before any non-serve shot had a
    chance to slip through in between, which is exactly the
    first-serve-fault-then-second-serve sequence: nothing real to
    (wrongly) confirm ever occurs between two serves in that case.

    A gap since the last swing bigger than rally_gap_sec is a point
    boundary (reuses the same threshold group_into_rallies() already uses
    for this, rather than inventing a second one) -- closes the gate again,
    so the next point needs its own fresh serve.

    Serves are excluded from the returned list -- still not rally content,
    same as before this function existed.
    """
    kept = []
    serve_open = False
    last_time = None

    for sw in classified_swings:
        peak_time = sw['peak_time']
        if last_time is not None and (peak_time - last_time) > rally_gap_sec:
            serve_open = False
        last_time = peak_time

        if sw['shot_type'] == 'serve':
            serve_open = True
            print(f'  swing at {peak_time:.1f}s: serve, opens the point (excluded from rally grouping)',
                  file=sys.stderr)
            continue

        if not serve_open:
            print(f'  swing at {peak_time:.1f}s: {sw["shot_type"]}, no serve has opened this point yet -- skipping',
                  file=sys.stderr)
            continue

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
    classified_swings = filter_to_real_rally_shots(video_path, raw_swings, fps, frames)
    print(f'  {len(classified_swings)} verified real swings remain (serves included)', file=sys.stderr)

    print('  Gating on serve sequencing...', file=sys.stderr)
    swings = apply_serve_gate(classified_swings, rally_gap_sec)
    print(f'  {len(swings)} non-serve swings confirmed after a serve opened their point', file=sys.stderr)

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
        # cv2.VideoWriter's mp4v fourcc produces old MPEG-4 Part 2 video on
        # this machine (fourcc reads back as 'FMP4'), which no browser can
        # play -- see video_io.py's module docstring. Re-encode to real
        # H.264 immediately so every rally clip served to the app is
        # actually playable.
        reencode_to_h264(out_path)
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
