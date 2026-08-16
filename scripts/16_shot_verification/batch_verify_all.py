"""
Runs the full shot-contact + shot-type teacher-student verification across
every real rally clip already extracted for Jack's two match videos
(data/runtime/highlight_clips/13/{3,4}/rally_*.mp4) -- plan doc step 2.
For each rally clip: extract poses, find wrist-velocity swing candidates,
run the geometric student (verify_shot_contact.verify_swings), then the
Claude teacher (verify_shot_contact_verified.get_verified_shot_contact) on
every candidate -- building real training data and a genuine ground-truth
set of which candidates are real shots (with correct type).

Checkpointed/resumable (same pattern as
scripts/15_batch_analysis/analyze_rallies_parallel.py) so a crash/restart
never re-pays already-done Claude calls.

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

from paths import DATA_DIR  # noqa: E402
from extract_poses import extract_poses  # noqa: E402
from detect_swings import compute_wrist_velocity, find_swing_peaks, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC  # noqa: E402
from verify_shot_contact import verify_swings  # noqa: E402
from verify_shot_contact_verified import get_verified_shot_contact  # noqa: E402

HIGHLIGHT_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'highlight_clips', '13')
RUNTIME_DIR = os.path.join(DATA_DIR, 'runtime', 'shot_verification_batch')
POSES_CACHE_DIR = os.path.join(RUNTIME_DIR, 'poses')
CHECKPOINT_PATH = os.path.join(RUNTIME_DIR, 'verified_swings.jsonl')
LOG_PATH = os.path.join(RUNTIME_DIR, 'batch_log.txt')


def log(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(LOG_PATH, 'a') as f:
        f.write(line + '\n')


def checkpoint_key(job_id, rally_id, swing_index):
    return f'{job_id}:{rally_id}:{swing_index}'


def load_checkpoint():
    if not os.path.exists(CHECKPOINT_PATH):
        return set()
    done = set()
    with open(CHECKPOINT_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    done.add(json.loads(line)['key'])
                except (json.JSONDecodeError, KeyError):
                    continue  # tolerate a truncated last line from a crashed run
    return done


def append_checkpoint(key, result):
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(CHECKPOINT_PATH, 'a') as f:
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


def process_rally(job_id, rally_id, clip_path, already_done):
    pose_data = get_poses(job_id, rally_id, clip_path)
    fps = pose_data['fps']
    frames = pose_data['frames']
    velocities = compute_wrist_velocity(frames)
    swings = find_swing_peaks(velocities, frames, fps, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC)
    verify_swings(clip_path, swings, fps, frames=frames)

    for i, sw in enumerate(swings, 1):
        key = checkpoint_key(job_id, rally_id, i)
        if key in already_done:
            continue
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
            result = {'job_id': job_id, 'rally_id': rally_id, 'swing_index': i, 'error': str(e)}
            log(f'  job{job_id} rally{rally_id} swing{i}: ERROR {e}')
        append_checkpoint(key, result)
        already_done.add(key)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', default='3,4')
    parser.add_argument('--limit', type=int, default=None, help='Only process the first N rally clips per job')
    args = parser.parse_args()

    job_ids = [j.strip() for j in args.jobs.split(',')]
    already_done = load_checkpoint()
    log(f'=== Starting batch verification for jobs {job_ids} -- '
        f'{len(already_done)} swings already checkpointed ===')

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
                process_rally(job_id, rally_id, clip_path, already_done)
            except Exception as e:
                log(f'  job{job_id} rally{rally_id}: FAILED to process -- {e}')

    log('=== DONE ===')


if __name__ == '__main__':
    main()
