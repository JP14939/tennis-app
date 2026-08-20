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

Usage:
  python list_swing_candidates.py <job_id>

Output (stdout): {"candidates": [{job_id, rally_id, swing_index,
  peak_time_sec, peak_frame, duration_sec, student_contact_confidence,
  student_contact_method, student_shot_type, student_shot_scores}, ...]}
"""
import contextlib
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '03_swing_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '16_shot_verification'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '14_shot_classifier'))

from paths import DATA_DIR  # noqa: E402
from extract_poses import extract_poses  # noqa: E402
from detect_swings import compute_wrist_velocity, find_swing_peaks, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC  # noqa: E402
from verify_shot_contact import verify_swings, filter_verified_swings  # noqa: E402
from classify_shot import classify  # noqa: E402
from reviewed_candidates_log import get_reviewed_set  # noqa: E402

HIGHLIGHT_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'highlight_clips', '13')
POSES_CACHE_DIR = os.path.join(DATA_DIR, 'runtime', 'shot_verification_batch', 'poses')

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

    clips = sorted(f for f in os.listdir(job_dir) if f.startswith('rally_') and f.endswith('.mp4'))
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

            for i, sw in enumerate(swings, 1):
                if (rally_id, i) in reviewed:
                    continue  # already given a verdict in a previous session -- don't re-serve it
                shot_type = scores = None
                try:
                    result = classify(clip_path, sw['peak_time'], frames_fps=(classify_frames, fps))
                    shot_type, scores = result['shot_type'], result['scores']
                except Exception:
                    pass  # student classification failing isn't fatal -- just omit it, Jack can still review

                candidates.append({
                    'job_id': job_id, 'rally_id': rally_id, 'swing_index': i,
                    'peak_time_sec': sw['peak_time'], 'peak_frame': sw['peak_frame'],
                    'fps': fps,
                    'clip_url': f'/highlight-clips/13/{job_id}/{clip_name}',
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
        except Exception as e:
            print(f'  rally {rally_id}: FAILED -- {e}', file=sys.stderr)

    print(json.dumps({'candidates': candidates}))


if __name__ == '__main__':
    main()
