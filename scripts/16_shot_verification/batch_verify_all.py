"""
Runs the full shot-contact + shot-type teacher-student verification across
every real rally clip already extracted for Jack's match videos
(data/runtime/highlight_clips/13/<job>/rally_*.mp4) -- plan doc step 2.
For each rally clip: extract poses, find wrist-velocity swing candidates,
run the geometric student (verify_shot_contact.verify_swings), then the
Claude teacher (verify_shot_contact_verified.get_verified_shot_contact) on
every candidate -- building real training data and a genuine ground-truth
set of which candidates are real shots. For swings confirmed real, ALSO
calls the shot-CLASSIFIER teacher (classify_shot_verified.get_verified_shot_type)
-- this used to only backfill the contact loop; the classifier loop is the
worse-performing of the two (35% vs 59-73% agreement) and most needs the
data, and get_verified_shot_type() reuses the same already-extracted
frames/fps (frames_fps=) so this costs no extra pose extraction.

Checkpointed/resumable (same pattern as
scripts/15_batch_analysis/analyze_rallies_parallel.py) so a crash/restart
never re-pays already-done Claude calls -- contact and classifier results
are checkpointed separately (CHECKPOINT_PATH / CLASSIFIER_CHECKPOINT_PATH)
since they're independent teacher-student loops with their own trust state.

Usage:
  python batch_verify_all.py [--jobs 3,4] [--limit N]
"""
import argparse
import contextlib
import json
import os
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '03_swing_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '16_shot_verification'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '14_shot_classifier'))

from paths import DATA_DIR  # noqa: E402
from extract_poses import extract_poses  # noqa: E402
from detect_swings import compute_wrist_velocity, find_swing_peaks, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC  # noqa: E402
from verify_shot_contact import verify_swings  # noqa: E402
from verify_shot_contact_verified import get_verified_shot_contact  # noqa: E402
from classify_shot_verified import get_verified_shot_type  # noqa: E402

HIGHLIGHT_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'highlight_clips', '13')
RUNTIME_DIR = os.path.join(DATA_DIR, 'runtime', 'shot_verification_batch')
POSES_CACHE_DIR = os.path.join(RUNTIME_DIR, 'poses')
CHECKPOINT_PATH = os.path.join(RUNTIME_DIR, 'verified_swings.jsonl')
CLASSIFIER_CHECKPOINT_PATH = os.path.join(RUNTIME_DIR, 'verified_shot_types.jsonl')
LOG_PATH = os.path.join(RUNTIME_DIR, 'batch_log.txt')


def log(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(LOG_PATH, 'a') as f:
        f.write(line + '\n')


def checkpoint_key(job_id, rally_id, swing_index):
    return f'{job_id}:{rally_id}:{swing_index}'


def load_checkpoint(path):
    """Returns {key: result} (not just a set of keys) -- process_rally needs
    a prior run's actual is_real_shot value when a swing's contact check is
    already checkpointed but its classifier check isn't yet (e.g. jobs 3/4
    were contact-checkpointed before this script backfilled the classifier
    loop too), not just whether the key exists."""
    if not os.path.exists(path):
        return {}
    done = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                    done[record['key']] = record
                except (json.JSONDecodeError, KeyError):
                    continue  # tolerate a truncated last line from a crashed run
    return done


def append_checkpoint(path, key, result):
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(path, 'a') as f:
        f.write(json.dumps({'key': key, **result}) + '\n')


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


def process_rally(job_id, rally_id, clip_path, contact_done, classifier_done):
    pose_data = get_poses(job_id, rally_id, clip_path)
    fps = pose_data['fps']
    frames = pose_data['frames']
    velocities = compute_wrist_velocity(frames)
    swings = find_swing_peaks(velocities, frames, fps, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC)
    verify_swings(clip_path, swings, fps, frames=frames)

    for i, sw in enumerate(swings, 1):
        key = checkpoint_key(job_id, rally_id, i)

        if key in contact_done:
            # Already checkpointed in a prior run -- reuse its verdict rather
            # than treating "already done" as "not a real shot" (which would
            # silently skip the classifier step below for every swing a
            # pre-this-feature run already verified, e.g. jobs 3/4).
            is_real_shot = contact_done[key].get('is_real_shot')
        else:
            try:
                is_real_shot, meta = get_verified_shot_contact(clip_path, sw, fps)
                result = {
                    'job_id': job_id, 'rally_id': rally_id, 'swing_index': i,
                    'peak_frame': sw['peak_frame'], 'peak_time_sec': sw['peak_time'],
                    'is_real_shot': is_real_shot, **meta,
                }
                log(f'  job{job_id} rally{rally_id} swing{i}: is_real_shot={is_real_shot} '
                    f'shot_type={meta.get("shot_type")} source={meta.get("source")}')
            except Exception as e:
                is_real_shot = None
                result = {'job_id': job_id, 'rally_id': rally_id, 'swing_index': i, 'error': str(e)}
                log(f'  job{job_id} rally{rally_id} swing{i}: ERROR {e}')
            append_checkpoint(CHECKPOINT_PATH, key, result)
            contact_done[key] = result

        # Shot-classifier backfill: only for swings confirmed real -- same
        # sequencing detect_rallies.py already uses live (classify a swing
        # that isn't real is meaningless). Reuses this rally's already-
        # extracted frames/fps (frames_fps=) so this costs zero extra pose
        # extraction, only the extra Claude call itself.
        if key not in classifier_done and is_real_shot:
            try:
                shot_type, meta = get_verified_shot_type(clip_path, sw['peak_time'], frames_fps=(frames, fps))
                result = {
                    'job_id': job_id, 'rally_id': rally_id, 'swing_index': i,
                    'peak_frame': sw['peak_frame'], 'peak_time_sec': sw['peak_time'],
                    'shot_type': shot_type, **meta,
                }
                log(f'  job{job_id} rally{rally_id} swing{i}: shot_type={shot_type} source={meta.get("source")}')
            except Exception as e:
                result = {'job_id': job_id, 'rally_id': rally_id, 'swing_index': i, 'error': str(e)}
                log(f'  job{job_id} rally{rally_id} swing{i}: CLASSIFIER ERROR {e}')
            append_checkpoint(CLASSIFIER_CHECKPOINT_PATH, key, result)
            classifier_done[key] = result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', default='3,4')
    parser.add_argument('--limit', type=int, default=None, help='Only process the first N rally clips per job')
    args = parser.parse_args()

    job_ids = [j.strip() for j in args.jobs.split(',')]
    contact_done = load_checkpoint(CHECKPOINT_PATH)
    classifier_done = load_checkpoint(CLASSIFIER_CHECKPOINT_PATH)
    log(f'=== Starting batch verification for jobs {job_ids} -- '
        f'{len(contact_done)} contact + {len(classifier_done)} classifier swings already checkpointed ===')

    for job_id in job_ids:
        job_dir = os.path.join(HIGHLIGHT_CLIPS_DIR, job_id)
        if not os.path.isdir(job_dir):
            log(f'Job {job_id}: no clips dir found, skipping')
            continue
        clips = sorted(f for f in os.listdir(job_dir) if f.startswith('rally_') and f.endswith('.mp4'))
        if args.limit:
            clips = clips[:args.limit]
        log(f'Job {job_id}: {len(clips)} rally clips')
        for clip_name in clips:
            rally_id = int(clip_name.replace('rally_', '').replace('.mp4', ''))
            clip_path = os.path.join(job_dir, clip_name)
            try:
                process_rally(job_id, rally_id, clip_path, contact_done, classifier_done)
            except Exception as e:
                log(f'  job{job_id} rally{rally_id}: FAILED to process -- {e}')

    log('=== DONE ===')


if __name__ == '__main__':
    main()
