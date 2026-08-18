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

HIGHLIGHT_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'highlight_clips', '13')
POSES_CACHE_DIR = os.path.join(DATA_DIR, 'runtime', 'shot_verification_batch', 'poses')


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

            for i, sw in enumerate(swings, 1):
                shot_type = scores = None
                try:
                    result = classify(clip_path, sw['peak_time'], frames_fps=(frames, fps))
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
