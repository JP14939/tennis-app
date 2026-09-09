"""
Phase 0a driver: re-extract every pro-database source video's pose file at
sample_every=1 (was 3), WITH world_landmarks.

Why: the pro-DB trajectories (and the live phone-upload query path) were built
at a 1-in-3 frame stride -- a measured ceiling on contact-frame precision and on
the DTW similarity metric's ability to separate a pro from a decent amateur.
This regenerates the raw pose data at full frame rate so trajectories/overlays
can be re-sliced denser (see 06_database_build/reslice_all_trajectories.py), and
captures MediaPipe world landmarks so the pro side of viewpoint (yaw)
normalization can finally be wired.

This is the long job (~60-90 min, dominated by the three ~1GB+ compilations).
It ONLY rewrites data/02_pose_extraction/*.json. Nothing in pro_database.json
changes until the re-slice step runs.

Sources (13):
  - the 9 broadcast compilations, from source_footage_lookup's canonical
    (source video, pose file) mapping -- the same mirror of build_pro_database
    .JOBS that split_pro_clip.py / rebuild_helpers.py already rely on. Imported
    from there rather than from build_pro_database directly to avoid that
    module's top-level mediapipe (infer_angle) import.
  - the 4 practice_0N videos (ingest_practice_footage.py's source).

Each existing pose JSON is copied to
data/02_pose_extraction/_backup_pre_stride1_<ts>/ before being overwritten.

Resumable: a job whose output JSON is newer than this run's start time is
assumed already done and skipped, so a crash / laptop-sleep part-way through
doesn't restart the finished big files. Use --force to re-extract everything.

Usage:
  python reextract_pro_poses.py [--force] [--only forehand_compilation_1 ...]
"""
import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '06_database_build'))

from extract_poses import extract_poses  # noqa: E402
from paths import DATA_DIR  # noqa: E402
from source_footage_lookup import SOURCE_VIDEOS_BY_SHOT_TYPE, POSES_BY_SHOT_TYPE  # noqa: E402

POSES_DIR = os.path.join(DATA_DIR, '02_pose_extraction')
PRACTICE_DIR = os.path.join(DATA_DIR, '01_source_videos', 'practice')


def _jobs():
    """(label, video_path, poses_path) for all 13 sources, in extraction order
    (broadcast compilations first, practice last)."""
    jobs = []
    for shot_type, videos in SOURCE_VIDEOS_BY_SHOT_TYPE.items():
        poses = POSES_BY_SHOT_TYPE[shot_type]
        assert len(videos) == len(poses), f'{shot_type}: video/pose count mismatch'
        for video, pose_path in zip(videos, poses):
            jobs.append((os.path.splitext(os.path.basename(video))[0], video, pose_path))
    for n in ('01', '02', '03', '04'):
        jobs.append((f'practice_{n}',
                     os.path.join(PRACTICE_DIR, f'practice_{n}.mp4'),
                     os.path.join(POSES_DIR, f'practice_{n}_poses.json')))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true',
                    help='re-extract every job even if its pose file already looks fresh')
    ap.add_argument('--only', nargs='+', metavar='LABEL',
                    help='restrict to these job labels (e.g. forehand_compilation_1)')
    args = ap.parse_args()

    started = time.time()
    ts = time.strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(POSES_DIR, f'_backup_pre_stride1_{ts}')

    jobs = _jobs()
    if args.only:
        want = set(args.only)
        jobs = [j for j in jobs if j[0] in want]
        missing = want - {j[0] for j in jobs}
        if missing:
            sys.exit(f'unknown --only label(s): {sorted(missing)}')

    print(f'{len(jobs)} job(s). backups -> {backup_dir}\n')
    done, skipped, failed = [], [], []

    for i, (label, video, pose_path) in enumerate(jobs, 1):
        head = f'[{i}/{len(jobs)}] {label}'
        if not os.path.exists(video):
            print(f'{head}: MISSING video {video} -- skipping')
            failed.append(label)
            continue
        if not args.force and os.path.exists(pose_path) and os.path.getmtime(pose_path) >= started:
            print(f'{head}: pose file already fresh this run -- skipping')
            skipped.append(label)
            continue

        if os.path.exists(pose_path):
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(pose_path, os.path.join(backup_dir, os.path.basename(pose_path)))

        t0 = time.time()
        print(f'{head}: extracting (sample_every=1) {os.path.basename(video)} ...')
        try:
            extract_poses(video, pose_path, sample_every=1)
        except Exception as e:  # noqa: BLE001 -- report and continue to the next job
            print(f'{head}: FAILED -- {e}')
            failed.append(label)
            continue
        size_mb = os.path.getsize(pose_path) / 1e6
        print(f'{head}: done in {time.time() - t0:.0f}s -> {size_mb:.0f} MB\n')
        done.append(label)

    print('\n' + '=' * 50)
    print(f'extracted : {len(done)}  {done}')
    print(f'skipped   : {len(skipped)}  {skipped}')
    print(f'failed    : {len(failed)}  {failed}')
    print(f'total elapsed: {(time.time() - started) / 60:.1f} min')
    if os.path.isdir(backup_dir):
        print(f'backups   : {backup_dir}')

    # Completion sentinel -- the downstream orchestrator
    # (17_amateur_eval/run_metric3d_rebuild.py) keys off THIS, not off
    # world_landmarks appearing in individual pose files (which happens
    # file-by-file across the ~90min run -- watching for partial presence
    # would fire the re-slice against a half-stride-3 DB).
    all_present = all(os.path.exists(p) for _, _, p in _jobs())
    if not failed and not args.only and all_present:
        sentinel = os.path.join(POSES_DIR, '.stride1_reextract_complete')
        with open(sentinel, 'w') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S') + '\n')
        print(f'sentinel  : {sentinel}')

    print('\nNext (owned by 17_amateur_eval/run_metric3d_rebuild.py): '
          'reslice_all_trajectories -> reanchor_pro_serves -> verify:db -> '
          'evaluate_amateur_dataset -> redesign_similarity')
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
