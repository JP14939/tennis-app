"""
Batch-analyze every swing across one or more already-processed highlight
jobs (see backend/src/routes/highlights.js): find swing peaks within each
detected rally, classify shot type, compare against the pro database, and
save each result into the owning user's history -- same end state as if
they'd uploaded and analysed each swing by hand, just automated over a
full match video.

Processes swings across a worker pool (real OS processes -- this is
CPU-bound, the GIL rules out threads) instead of one at a time, and is
checkpointed/resumable so a crash or restart never re-processes (and
duplicate-saves) work already done.

Usage:
  python analyze_rallies_parallel.py <job_id> [<job_id> ...]

Env vars:
  RALLYMAX_AUTH_TOKEN   -- JWT to authenticate as (required unless
                           RALLYMAX_TOKEN_FILE is set instead)
  RALLYMAX_TOKEN_FILE   -- path to a file containing just the JWT
  RALLYMAX_API_BASE     -- defaults to http://localhost:5000
  RALLYMAX_MAX_WORKERS  -- hard cap on worker count, defaults to 6

Worker count auto-sizes from real CPU/RAM headroom (see pick_worker_count())
-- on a small host (e.g. a 1 OCPU / 6GB VM) this naturally resolves to 1-2
workers rather than needing a separate low-resource code path; it speeds
back up automatically on a bigger box.
"""
import contextlib
import json
import multiprocessing
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

import cv2
import psutil
import requests

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
from paths import DATA_DIR  # noqa: E402
from clip_urls import attach_clip_urls  # noqa: E402

for sub in ['02_pose_extraction', '03_swing_detection', '04_clip_extraction',
            '08_comparison_engine', '14_shot_classifier', '16_shot_verification']:
    sys.path.insert(0, os.path.join(SCRIPTS_DIR, sub))

VERIFIED_SWINGS_PATH = os.path.join(DATA_DIR, 'runtime', 'shot_verification_batch', 'verified_swings.jsonl')

API_BASE = os.environ.get('RALLYMAX_API_BASE', 'http://localhost:5000')
MAX_WORKERS = int(os.environ.get('RALLYMAX_MAX_WORKERS', '6'))
# Opt-out for the final shot-type classification saved to History -- unlike
# shot-contact verification (no undo if a real shot gets silently dropped),
# a wrong shot_type here is trivially correctable later via History's own
# flag/confirm/correct-type buttons, so this is safe to skip when the
# caller doesn't need it right (e.g. a large batch run where a human will
# review every row anyway). Defaults to off so normal runs are unaffected.
SKIP_CLASSIFIER_VERIFIER = os.environ.get('RALLYMAX_SKIP_CLASSIFIER_VERIFIER') == '1'
# Opt-out for shot-contact ("is this actually a shot") verification too --
# unlike the classifier flag above, skipping this one does risk silently
# dropping/keeping the wrong candidates with no way to recover a missed
# shot. Off by default; only set when that trade-off has been explicitly
# accepted (e.g. no Claude API credits available to verify against).
SKIP_CONTACT_VERIFIER = os.environ.get('RALLYMAX_SKIP_CONTACT_VERIFIER') == '1'
RAM_PER_WORKER_GB = 1.5  # rough MediaPipe + YOLO footprint per worker process

RUNTIME_DIR = os.path.join(DATA_DIR, 'runtime', 'batch_analysis')
SWING_CLIPS_DIR = os.path.join(RUNTIME_DIR, 'swing_clips')
LOG_PATH = os.path.join(RUNTIME_DIR, 'analysis_log.txt')
CHECKPOINT_PATH = os.path.join(RUNTIME_DIR, 'completed_swings.jsonl')

PRE_PAD_SEC = 1.5
POST_PAD_SEC = 2.0


def _load_token():
    token = os.environ.get('RALLYMAX_AUTH_TOKEN')
    if token:
        return token.strip()
    token_file = os.environ.get('RALLYMAX_TOKEN_FILE')
    if token_file and os.path.exists(token_file):
        return open(token_file).read().strip()
    raise RuntimeError('Set RALLYMAX_AUTH_TOKEN or RALLYMAX_TOKEN_FILE before running this script.')


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


def append_checkpoint(key, result_summary):
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(CHECKPOINT_PATH, 'a') as f:
        f.write(json.dumps({'key': key, **result_summary}) + '\n')


# ── Worker-side globals, set once per worker process via the pool initializer ──
_worker_lock = None
_worker_token = None


def _init_worker(lock, token):
    global _worker_lock, _worker_token
    _worker_lock = lock
    _worker_token = token


def process_swing(task):
    """
    Runs in a worker process. task: dict with job_id, rally_id, swing_index,
    swing_clip_path, contact_rel_sec. Returns a small JSON-safe result dict
    -- never raises, so one bad swing can't take down the pool.
    """
    from compare_swing import compare, extract_user_poses
    from classify_shot_verified import get_verified_shot_type

    job_id, rally_id, swing_index = task['job_id'], task['rally_id'], task['swing_index']
    swing_clip = task['swing_clip_path']
    contact_rel_sec = task['contact_rel_sec']
    verify_source = task.get('verify_source')
    key = checkpoint_key(job_id, rally_id, swing_index)

    try:
        frames_fps = extract_user_poses(swing_clip)
    except Exception as e:
        return {'key': key, 'ok': False, 'stage': 'pose_extraction', 'error': str(e)}

    try:
        shot_type, class_meta = get_verified_shot_type(
            swing_clip, contact_rel_sec, use_verifier=not SKIP_CLASSIFIER_VERIFIER,
            frames_fps=frames_fps, log_lock=_worker_lock)
    except Exception as e:
        return {'key': key, 'ok': False, 'stage': 'classification', 'error': str(e)}

    try:
        result = compare(swing_clip, shot_type, top_n=3, contact_time_sec=contact_rel_sec, frames_fps=frames_fps)
    except Exception as e:
        return {'key': key, 'ok': False, 'stage': 'comparison', 'error': f'{e}\n{traceback.format_exc()}'}

    if 'error' in result:
        return {'key': key, 'ok': False, 'stage': 'comparison', 'error': result['error']}

    result['shotType'] = shot_type
    result['_batch_source'] = {
        'job_id': job_id, 'rally_id': rally_id, 'swing_index': swing_index,
        'classifier_source': class_meta.get('source'),
        'shot_verified_source': verify_source,
    }

    # Live single-swing uploads get user_clip_url/pro_clip_url attached in
    # analyse.js (persistAndCrop/croppedProClipPath) -- batch-saved swings
    # never went through that route, so ResultsScreen's "Watch & compare"
    # never had clip data to show. Attach the same fields here so every
    # batch-saved analysis has them from the start (non-fatal: a failure
    # here just means no clip URLs on this one result, not a lost swing).
    try:
        attach_clip_urls(result, swing_clip, dest_key=key.replace(':', '_'))
    except Exception as e:
        log(f'  [warn] {key}: clip-url attach failed: {e}')

    try:
        resp = requests.post(
            f'{API_BASE}/api/history',
            headers={'Authorization': f'Bearer {_worker_token}', 'Content-Type': 'application/json'},
            data=json.dumps(result), timeout=60,
        )
        if resp.status_code >= 300:
            return {'key': key, 'ok': False, 'stage': 'save', 'error': f'{resp.status_code}: {resp.text[:200]}'}
    except Exception as e:
        return {'key': key, 'ok': False, 'stage': 'save', 'error': str(e)}

    top = result.get('matches', [{}])[0]
    return {
        'key': key, 'ok': True, 'shot_type': shot_type,
        'similarity': top.get('similarity'), 'source': class_meta.get('source'),
    }


# ── Coordinator ──────────────────────────────────────────────────────────────

def find_swings_in_clip(clip_path):
    from extract_poses import extract_poses
    from detect_swings import compute_wrist_velocity, find_swing_peaks, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        pose_path = os.path.join(tmp, 'poses.json')
        with contextlib.redirect_stdout(sys.stderr):
            extract_poses(clip_path, pose_path, sample_every=3)
        with open(pose_path) as f:
            pose_data = json.load(f)
    fps = pose_data['fps']
    frames = pose_data['frames']
    velocities = compute_wrist_velocity(frames)
    swings = find_swing_peaks(velocities, frames, fps, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC)
    return swings, fps, frames


def load_verified_swings():
    """
    {(job_id_str, rally_id, swing_index): record} from
    scripts/16_shot_verification/batch_verify_all.py's checkpoint --
    already-paid-for Claude verification for this exact dataset (same
    rally clips, same deterministic swing-detection constants), reused
    here instead of calling Claude a second time for the same candidates.
    Empty dict (not an error) if that batch was never run -- callers fall
    back to live verification per swing in that case.
    """
    verified = {}
    if not os.path.exists(VERIFIED_SWINGS_PATH):
        return verified
    with open(VERIFIED_SWINGS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if 'error' in rec:
                continue
            verified[(str(rec['job_id']), rec['rally_id'], rec['swing_index'])] = rec
    return verified


def build_worklist(job_ids, token, already_done):
    from extract_clips import extract_clip
    from verify_shot_contact import verify_swings
    from verify_shot_contact_verified import get_verified_shot_contact

    verified_cache = load_verified_swings()
    log(f'Loaded {len(verified_cache)} cached shot verifications '
        f'({"none -- will verify live per swing" if not verified_cache else "reused, no duplicate Claude calls"})')

    skipped_not_shot = 0
    worklist = []
    for job_id in job_ids:
        r = requests.get(f'{API_BASE}/api/highlights/jobs/{job_id}',
                          headers={'Authorization': f'Bearer {token}'}, timeout=30)
        r.raise_for_status()
        job = r.json()
        if job.get('status') != 'done':
            log(f'Job {job_id} is not done (status={job.get("status")}) -- skipping')
            continue

        rallies = job.get('rallies', [])
        log(f'Job {job_id}: {len(rallies)} rallies')
        out_dir = os.path.join(SWING_CLIPS_DIR, str(job_id))
        os.makedirs(out_dir, exist_ok=True)

        for rally in rallies:
            clip_path = rally['clip_path']
            if not os.path.exists(clip_path):
                log(f'  rally {rally["id"]}: clip missing on disk, skipping')
                continue
            try:
                swings, fps, frames = find_swings_in_clip(clip_path)
            except Exception as e:
                log(f'  rally {rally["id"]}: swing detection failed, skipping: {e}')
                continue

            cap = cv2.VideoCapture(clip_path)
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps

            for i, sw in enumerate(swings, 1):
                key = checkpoint_key(job_id, rally['id'], i)
                if key in already_done:
                    continue

                # Gate on verified-shot ground truth *before* spending any
                # extraction/classification/comparison work on a candidate
                # that isn't a real shot -- this is the whole point of the
                # "retrain everything" pass. Reuses batch_verify_all.py's
                # already-paid-for Claude verdicts for this exact rally
                # clip when available (deterministic detection means the
                # same swing_index lines up); falls back to a live call
                # only for anything that batch run didn't cover.
                cache_key = (str(job_id), rally['id'], i)
                verify_rec = verified_cache.get(cache_key)
                if verify_rec is not None:
                    is_real_shot, verify_meta = verify_rec['is_real_shot'], verify_rec
                else:
                    verify_swings(clip_path, [sw], fps, frames=frames)
                    is_real_shot, verify_meta = get_verified_shot_contact(
                        clip_path, sw, fps, use_verifier=not SKIP_CONTACT_VERIFIER, log_lock=None)
                if not is_real_shot:
                    skipped_not_shot += 1
                    log(f'  rally {rally["id"]} swing {i}: not a real shot, skipping '
                        f'({str(verify_meta.get("reasoning", ""))[:80]})')
                    continue

                peak_time = sw['peak_time']
                start_sec = max(0.0, peak_time - PRE_PAD_SEC)
                end_sec = min(duration, peak_time + POST_PAD_SEC)
                start_frame = int(start_sec * fps)
                end_frame = min(total_frames - 1, int(end_sec * fps))
                contact_rel_sec = peak_time - start_sec

                swing_clip = os.path.join(out_dir, f'rally{rally["id"]:03d}_swing{i:02d}.mp4')
                try:
                    extract_clip(cap, start_frame, end_frame, swing_clip, fps, fourcc)
                except Exception as e:
                    log(f'  rally {rally["id"]} swing {i}: clip extraction failed, skipping: {e}')
                    continue

                worklist.append({
                    'job_id': job_id, 'rally_id': rally['id'], 'swing_index': i,
                    'swing_clip_path': swing_clip, 'contact_rel_sec': contact_rel_sec,
                    'verify_source': verify_meta.get('source'),
                })
            cap.release()

    log(f'Worklist built: {len(worklist)} verified real shots to process, '
        f'{skipped_not_shot} candidates skipped as not real shots')
    return worklist


def prefetch_shared_model_weights():
    """
    ultralytics lazily downloads yolo11n.pt/yolo11n-pose.pt into the
    current working directory on first use (same weights the Dockerfile
    pre-downloads at build time -- see repo-root Dockerfile). If that first
    use happens to be two worker processes at once, they race to write the
    same file (observed directly: a WinError 32 file-lock collision when
    two workers both hit a cold cache). Downloading once here, before the
    pool starts, means no worker ever hits a cold cache.
    """
    log('Pre-fetching shared model weights (avoids workers racing to download the same file)...')
    from ultralytics import YOLO
    YOLO('yolo11n.pt')
    YOLO('yolo11n-pose.pt')


def pick_worker_count():
    cpu_based = max(1, (os.cpu_count() or 2) - 2)
    ram_gb = psutil.virtual_memory().available / (1024 ** 3)
    ram_based = max(1, int(ram_gb // RAM_PER_WORKER_GB))
    n = min(cpu_based, ram_based, MAX_WORKERS)
    log(f'Worker sizing: cpu_based={cpu_based}, ram_based={ram_based} ({ram_gb:.1f}GB available), '
        f'cap={MAX_WORKERS} -> using {n} workers')
    return n


def main():
    job_ids = sys.argv[1:]
    if not job_ids:
        print('Usage: python analyze_rallies_parallel.py <job_id> [<job_id> ...]')
        sys.exit(1)

    token = _load_token()
    already_done = load_checkpoint()
    log(f'=== Starting parallel batch analysis for jobs {job_ids} '
        f'({len(already_done)} swings already checkpointed as done) ===')

    worklist = build_worklist(job_ids, token, already_done)
    if not worklist:
        log('Nothing to do.')
        return

    prefetch_shared_model_weights()
    n_workers = pick_worker_count()
    lock = multiprocessing.Manager().Lock()

    stats = {'saved': 0, 'failed': 0}
    with ProcessPoolExecutor(max_workers=n_workers, initializer=_init_worker, initargs=(lock, token)) as pool:
        futures = {pool.submit(process_swing, task): task for task in worklist}
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result()
            except Exception as e:
                result = {'key': checkpoint_key(task['job_id'], task['rally_id'], task['swing_index']),
                           'ok': False, 'stage': 'worker_crash', 'error': str(e)}

            append_checkpoint(result['key'], result)
            if result['ok']:
                stats['saved'] += 1
                log(f'  {result["key"]}: saved -- {result["shot_type"]}, '
                    f'similarity={result["similarity"]}, source={result["source"]}')
            else:
                stats['failed'] += 1
                log(f'  {result["key"]}: FAILED at {result.get("stage")}: {result.get("error")}')

    log(f'=== DONE === {stats}')


if __name__ == '__main__':
    main()
