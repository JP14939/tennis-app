"""
Lists every wrist-velocity swing candidate for a highlight job's rally
clips, with the geometric student's (free, no-API-cost) opinion on each --
contact confidence/method (verify_shot_contact.verify_swings) and shot-type
scores (classify_shot.classify). No Claude calls at all.

Feeds the Dev Page's manual swing-review tool (DevSwingReviewScreen.js):
instead of paying for Claude as the teacher, Jack reviews each candidate
himself in the app and taps in his own verdict, which
log_manual_review.py then logs with the exact same shape/effect a Claude
verdict would have (source='user_flag') -- same training-log math, zero
API cost, and arguably more reliable ground truth than an LLM's opinion.

Candidates already given a verdict (see reviewed_candidates_log.py) are
excluded from the output -- otherwise reopening this tool for the same job
(a reload, navigating away and back) would re-serve the exact same full
list every time, forcing a full re-review of everything already done.

Also cuts each surviving swing out of its shared rally clip into its own
short file (clip_url points at that per-swing clip, not the full rally
clip), so DevSwingReviewScreen.js shows a genuinely trimmed video per swing
instead of re-scrubbing the same long clip once per swing found in it.

Usage:
  python list_swing_candidates.py <job_id>

Output (stdout): {"candidates": [{job_id, rally_id, swing_index,
  peak_time_sec, peak_frame, clip_url, clip_start_frame, fps,
  student_contact_confidence, student_contact_method,
  student_contact_frame_guess, student_shot_type, student_shot_scores}, ...]}
"""
import contextlib
import json
import os
import sys

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '03_swing_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '04_clip_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '16_shot_verification'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '14_shot_classifier'))

from paths import DATA_DIR  # noqa: E402
from extract_poses import extract_poses  # noqa: E402
from detect_swings import compute_wrist_velocity, find_swing_peaks, SHOT_WINDOWS, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC  # noqa: E402
from extract_clips import extract_clip  # noqa: E402
from verify_shot_contact import verify_swings, filter_verified_swings  # noqa: E402
from classify_shot import classify  # noqa: E402
from reviewed_candidates_log import get_reviewed_set  # noqa: E402
from video_io import reencode_to_h264  # noqa: E402

HIGHLIGHT_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'highlight_clips', '13')
POSES_CACHE_DIR = os.path.join(DATA_DIR, 'runtime', 'shot_verification_batch', 'poses')

# Per-swing cut clips live in a SIBLING dir to HIGHLIGHT_CLIPS_DIR, not
# nested inside it -- a file inside `.../13/{job_id}/` would get picked up
# by main()'s `f.startswith('rally_')` rally-clip enumeration on the next
# run. Anything under runtime/highlight_clips/ is already served by
# server.js's single express.static mount, so this needs no backend changes.
SWING_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'highlight_clips', '13_swings')
CLIP_PRE_SEC = max(w[0] for w in SHOT_WINDOWS.values())
CLIP_POST_SEC = max(w[1] for w in SHOT_WINDOWS.values())

# A job's raw source video can be hardlinked in under this prefix (see
# add_full_video_reference.py) to make it browsable in Swing Review for
# context, WITHOUT ever being run through pose extraction/swing detection --
# a full-length match video (hours, gigabytes) through that per-frame
# pipeline is exactly what hung job 9 for 10+ minutes until it hit
# dev.js's request timeout (see HANDOVER.md). Deliberately a distinct
# prefix from 'rally_' so it can never collide with/be mistaken for a real
# rally clip by the glob below.
FULL_VIDEO_PREFIX = 'full_video'

# find_swing_peaks() (shared with detect_rallies.py etc.) sometimes splits
# one real swing into two candidates -- its velocity curve can dip without
# fully bottoming out mid-swing and re-cross the threshold just past
# MIN_SWING_GAP_SEC (1.5s), producing a "before" and "after" candidate for
# the same contact event (confirmed on real data: job 7 rally 1 had peaks
# 1.87s apart that were the same swing, per Jack's own review -- he marked
# the same real contact frame on both).
#
# contact_frame_guess (verify_shot_contact.verify_swings()'s racket/ball
# evidence) looked like the more precise signal to merge on, but testing
# against that exact rally 1 case showed it ISN'T reliable here: the first
# (spurious) peak's contact_frame_guess was just as far from the second
# peak's as their raw peak_times were (both ~1.87s apart), because the
# automated guess is itself low-confidence/noisy exactly in these ambiguous
# split-swing cases -- the first "swing" is partial motion with weak
# evidence, not a real independent contact. peak_frame proximity is the
# reliable signal instead: it's what MIN_SWING_GAP_SEC (1.5s) already
# floors, so a pair landing just above that floor is the direct fingerprint
# of a floor-artifact split. 2.0s is chosen from real data collected while
# investigating this (job 7): floor-artifact gaps cluster at 1.47-1.87s,
# genuine distinct-shot gaps mostly start at 2.6s+ -- 2.0s sits in the gap
# between those clusters. contact_frame_guess is kept as a SECONDARY
# trigger (catches a merge peak_frame proximity alone would miss, when the
# racket/ball evidence agrees the two really are the same contact), not the
# primary one.
MERGE_WINDOW_SEC = 2.0


def _gap_frames(a, b, key):
    va, vb = a.get(key), b.get(key)
    if va is None or vb is None:
        return None
    return abs(va - vb)


def merge_duplicate_swings(swings, fps):
    """
    Collapses swings in ONE rally that are within MERGE_WINDOW_SEC of the
    last KEPT swing, by EITHER peak_frame (primary -- always defined, tied
    directly to the known MIN_SWING_GAP_SEC floor-artifact failure mode) OR
    contact_frame_guess (secondary, when available) being that close.
    Keeps whichever of the merged pair has higher contact_confidence
    (earlier one wins a tie). Assumes `swings` is already ordered by
    peak_frame (find_swing_peaks() produces this, but sort defensively
    rather than assume).
    """
    ordered = sorted(swings, key=lambda sw: sw['peak_frame'])
    merge_window_frames = MERGE_WINDOW_SEC * fps

    kept = []
    for sw in ordered:
        if kept:
            prev = kept[-1]
            peak_gap = _gap_frames(sw, prev, 'peak_frame')
            contact_gap = _gap_frames(sw, prev, 'contact_frame_guess')
            gaps = [g for g in (peak_gap, contact_gap) if g is not None]
            if gaps and min(gaps) <= merge_window_frames:
                prev_conf = prev.get('contact_confidence') or 0
                conf = sw.get('contact_confidence') or 0
                if conf > prev_conf:
                    kept[-1] = sw
                continue

        kept.append(sw)

    return kept


def _as_classify_frames(frames):
    """
    extract_poses.py (used here for wrist-velocity swing detection) stores
    each frame's landmarks as a LIST indexed positionally; classify_shot.py
    expects the dict-keyed-by-joint-name shape compare_swing.extract_user_poses()
    produces. Passing the raw list-shaped frames straight to classify()'s
    frames_fps (as this file used to) throws inside classify() the moment it
    tries dict-style lookups on a list -- silently swallowed by the bare
    except below, so student_shot_type has been None for every candidate
    this tool has ever served. Same reshape/fix already applied in
    detect_rallies.py's identically-named helper -- both extractors write
    identical per-landmark fields (name/x/y/z/visibility) in the same
    LANDMARK_NAMES order, so this is a cheap reshape of data already in
    hand, not a second pose-extraction pass.
    """
    return [
        {'frame': f['frame'], 'timestamp': f['timestamp'],
         'landmarks': {lm['name']: lm for lm in f['landmarks']} if f['landmarks'] else None}
        for f in frames
    ]


def get_poses(job_id, rally_id, clip_path):
    os.makedirs(POSES_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(POSES_CACHE_DIR, f'{job_id}_{rally_id}.json')
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)
    with contextlib.redirect_stdout(sys.stderr):
        extract_poses(clip_path, cache_path, sample_every=1)
    with open(cache_path) as f:
        return json.load(f)


def _partition_job_files(job_dir):
    """
    Splits a job's clip directory into (rally clip filenames, full-video
    reference filenames) -- pulled out as a pure function so this split is
    unit-testable without mocking cv2/pose extraction/YOLO (see
    test_list_swing_candidates_pytest.py). Anything matching neither prefix
    (a stray pose-cache file, .DS_Store, etc.) is ignored by both.
    """
    all_files = os.listdir(job_dir)
    clips = sorted(f for f in all_files if f.startswith('rally_') and f.endswith('.mp4'))
    full_video_files = sorted(
        f for f in all_files if f.startswith(FULL_VIDEO_PREFIX) and f.endswith('.mp4'))
    return clips, full_video_files


def main():
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'usage: list_swing_candidates.py <job_id>'}))
        sys.exit(1)
    job_id = sys.argv[1]

    job_dir = os.path.join(HIGHLIGHT_CLIPS_DIR, job_id)
    if not os.path.isdir(job_dir):
        print(json.dumps({'error': f'no clips dir for job {job_id}'}))
        sys.exit(1)

    reviewed = get_reviewed_set(job_id)

    clips, full_video_files = _partition_job_files(job_dir)
    candidates = []
    for clip_name in clips:
        rally_id = int(clip_name.replace('rally_', '').replace('.mp4', ''))
        clip_path = os.path.join(job_dir, clip_name)
        try:
            pose_data = get_poses(job_id, rally_id, clip_path)
            fps = pose_data['fps']
            frames = pose_data['frames']
            velocities = compute_wrist_velocity(frames)
            swings = find_swing_peaks(velocities, frames, fps, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC)
            verify_swings(clip_path, swings, fps, frames=frames)  # adds contact_confidence/contact_method, no API cost
            swings = merge_duplicate_swings(swings, fps)
            classify_frames = _as_classify_frames(frames)

            # Swings still needing a candidate emitted (already-reviewed ones
            # skipped) are the only ones worth opening the source clip for --
            # cheap early-exit when a rally is fully reviewed already.
            pending = [(i, sw) for i, sw in enumerate(swings, 1) if (rally_id, i) not in reviewed]
            cap = None
            if pending:
                cap = cv2.VideoCapture(clip_path)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            try:
                for i, sw in pending:
                    shot_type = scores = None
                    try:
                        result = classify(clip_path, sw['peak_time'], frames_fps=(classify_frames, fps))
                        shot_type, scores = result['shot_type'], result['scores']
                    except Exception:
                        pass  # student classification failing isn't fatal -- just omit it, Jack can still review

                    # Cut this swing out of the shared rally clip into its own
                    # short file, so Swing Review shows a genuinely trimmed
                    # clip per swing instead of re-scrubbing the same long
                    # rally video for every swing found in it. Reuses the same
                    # extract_clip()/reencode_to_h264() combo already proven
                    # in ingest_raw_footage_to_history.py. Skipped if already
                    # cut on a previous run of this job (file-exists cache,
                    # same pattern as get_poses() above).
                    os.makedirs(os.path.join(SWING_CLIPS_DIR, job_id), exist_ok=True)
                    swing_clip_path = os.path.join(SWING_CLIPS_DIR, job_id, f'rally_{rally_id}_swing_{i}.mp4')
                    start_frame = max(0, int(sw['peak_frame'] - CLIP_PRE_SEC * fps))
                    end_frame = min(total_frames - 1, int(sw['peak_frame'] + CLIP_POST_SEC * fps))
                    if not os.path.exists(swing_clip_path):
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        extract_clip(cap, start_frame, end_frame, swing_clip_path, fps, fourcc)
                        reencode_to_h264(swing_clip_path)

                    candidates.append({
                        'job_id': job_id, 'rally_id': rally_id, 'swing_index': i,
                        # peak_time_sec is relative to the CUT SUB-CLIP's own
                        # timeline (what DevSwingReviewScreen.js seeks/displays
                        # against); peak_frame stays in the original rally
                        # clip's frame numbering, matching
                        # student_contact_frame_guess below and everything
                        # contact_frame_training_log.py compares it against.
                        'peak_time_sec': round((sw['peak_frame'] - start_frame) / fps, 3),
                        'peak_frame': sw['peak_frame'],
                        'fps': fps,
                        'clip_url': f'/highlight-clips/13_swings/{job_id}/rally_{rally_id}_swing_{i}.mp4',
                        # Original-rally-clip frame number the sub-clip starts
                        # at -- DevSwingReviewScreen.js adds this back onto
                        # whatever contact frame it captures (in the sub-clip's
                        # local coordinates) before submitting a verdict, so
                        # log_manual_review.py keeps getting frame numbers in
                        # the same coordinate system as student_contact_frame_guess.
                        'clip_start_frame': start_frame,
                        # student_is_real_shot mirrors exactly what
                        # get_verified_shot_contact() derives student_is_shot as
                        # (filter_verified_swings on this one swing) -- needed by
                        # log_manual_review.py to log a real (student_pick,
                        # teacher_pick) pair, not just Jack's verdict alone.
                        'student_is_real_shot': bool(filter_verified_swings([sw])),
                        'student_contact_confidence': sw.get('contact_confidence'),
                        'student_contact_method': sw.get('contact_method'),
                        # find_contact_frame()'s actual guessed frame (see
                        # verify_shot_contact.py's contact_frame_guess addition
                        # this session) -- the "student" side of the new
                        # contact_frame_training_log.py comparison.
                        'student_contact_frame_guess': sw.get('contact_frame_guess'),
                        'student_shot_type': shot_type,
                        'student_shot_scores': scores,
                    })
            finally:
                if cap is not None:
                    cap.release()
        except Exception as e:
            print(f'  rally {rally_id}: FAILED -- {e}', file=sys.stderr)

    # Full-source-video reference entries -- browse-only, never pose-
    # extracted/swing-detected (that's exactly what hung job 9 -- see
    # FULL_VIDEO_PREFIX's comment above). No DB row, no verdict submission
    # path; DevSwingReviewScreen.js just lets Jack scrub it for context and
    # move on (is_full_video: True is its cue to skip the verdict stepper).
    for i, fname in enumerate(full_video_files, 1):
        candidates.append({
            'job_id': job_id, 'rally_id': None, 'swing_index': i,
            'is_full_video': True,
            'clip_url': f'/highlight-clips/13/{job_id}/{fname}',
            'peak_time_sec': 0, 'peak_frame': 0, 'fps': None,
            'clip_start_frame': 0,
            'student_is_real_shot': None, 'student_contact_confidence': None,
            'student_contact_method': None, 'student_contact_frame_guess': None,
            'student_shot_type': None, 'student_shot_scores': None,
        })

    print(json.dumps({'candidates': candidates}))


if __name__ == '__main__':
    main()
