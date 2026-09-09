"""
Queued orchestrator for the combined stride-1 + yaw (metric-3D depth) pro-database
rebuild -- the "Deferred" section of ~/.claude/plans/dreamy-exploring-eich.md.

It waits until the pro pose files carry world_landmarks (the overnight
02_pose_extraction/reextract_pro_poses.py has finished) AND the box is CPU-idle,
then runs the whole chain, teeing everything to
data/17_amateur_eval/metric3d_rebuild_<ts>.log:

  0. baseline   redesign_similarity.py eval                     (pre-rebuild separation, for comparison)
  1. reslice    06_database_build/reslice_all_trajectories.py    (stride-1 + yaw; rewrites pro_database.json + overlays, backs up first)
  2. reanchor   06_database_build/reanchor_pro_serves.py         (serve apex re-anchor on the new trajectories, backs up first)
  3. verify_db  backend `npm run verify:db`                      (98 invariants still hold)
  4. amateur    17_amateur_eval/evaluate_amateur_dataset.py --no-backfill   (classifier / trajectory-kNN regression gate)
  5. cache      redesign_similarity.py cache                     (v3: yaw-normalized user trajectories, ~30-45 min)
  6. axes       redesign_similarity.py axes                      (per-axis pro-vs-amateur separation, incl. the 5 new depth axes)
  7. rubric     redesign_similarity.py rubric                    (THE PAYOFF: forehand held-out-vs-amateur gap vs the +5.8 baseline)

STOPS after step 7. Re-curating CURATED_AXES from the step-6 table (keep new
depth axes with sep >= ~+7, weight proportional to sep) is a judgement call left
for a human / a follow-up session to review the log. Nothing here promotes
anything to production; steps 1 and 2 back up pro_database.json before writing.

Safe to launch NOW, before the re-extract: step 0 runs immediately, then it
polls and will not touch the DB until world_landmarks exist. If the re-extract
never lands it just times out (--max-wait-min, default 720) having only printed
the baseline.

Usage:
  python run_metric3d_rebuild.py                    # wait-for-ready, then run the chain
  python run_metric3d_rebuild.py --now              # skip the readiness wait (abort if pose files aren't ready)
  python run_metric3d_rebuild.py --skip-baseline    # don't run step 0
  python run_metric3d_rebuild.py --max-wait-min 300
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '10_net_detection'))

from paths import DATA_DIR  # noqa: E402

# reextract_pro_poses.py writes this on a clean full run (all 13 pose files,
# no --only, no failures). Primary readiness signal for the handoff.
REEXTRACT_SENTINEL = os.path.join(DATA_DIR, '02_pose_extraction', '.stride1_reextract_complete')
from source_footage_lookup import POSES_BY_SHOT_TYPE  # noqa: E402
from run_when_idle import busy_procs, DEFAULT_BUSY  # noqa: E402

PY = sys.executable
LOG_PATH = os.path.join(DATA_DIR, '17_amateur_eval',
                        f'metric3d_rebuild_{time.strftime("%Y%m%d_%H%M%S")}.log')
# don't count THIS orchestrator's own child steps as "someone else is busy"
# while we're waiting, the pose re-extract MUST count as "busy" (it's the thing
# we're waiting on); our own downstream steps must not.
IDLE_SUBSTRS = [s for s in DEFAULT_BUSY
                if s not in ('redesign_similarity', 'evaluate_amateur')] + ['reextract_pro_poses']

_log_fh = None


def log(msg=''):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}' if msg else ''
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + '\n')
        _log_fh.flush()


def pro_pose_files():
    files = [p for v in POSES_BY_SHOT_TYPE.values() for p in v]
    for n in ('01', '02', '03', '04'):
        files.append(os.path.join(DATA_DIR, '02_pose_extraction', f'practice_{n}_poses.json'))
    return [p for p in files if os.path.exists(p)]


def world_landmarks_ready():
    """True once reextract_pro_poses.py has written its completion sentinel AND
    a spot-check confirms world_landmarks are actually in the pose files. The
    sentinel (not per-file world_landmarks) is the primary signal -- the
    re-extract writes file-by-file in job order, so a partial world_landmarks
    count would mean it's still mid-run."""
    if not os.path.exists(REEXTRACT_SENTINEL):
        log('  waiting for reextract_pro_poses.py completion sentinel '
            f'({os.path.basename(REEXTRACT_SENTINEL)})')
        return False
    files = pro_pose_files()
    if len(files) < 13:
        log(f'  sentinel present but only {len(files)}/13 pose files found -- odd, holding')
        return False
    bad = []
    for p in files:
        try:
            with open(p) as f:
                frames = json.load(f)['frames']
        except Exception:
            bad.append(os.path.basename(p))
            continue
        det = [fr for fr in frames if fr.get('landmarks')]
        wl = [fr for fr in det if fr.get('world_landmarks')]
        if not det or len(wl) / len(det) < 0.8:
            bad.append(os.path.basename(p))
    if bad:
        log(f'  sentinel present but world_landmarks thin/absent in: {bad} -- holding')
        return False
    log(f'  sentinel present + world_landmarks confirmed in all {len(files)} pose files')
    return True


def wait_until_ready(max_wait_min, poll_sec=120):
    deadline = time.time() + max_wait_min * 60
    while time.time() < deadline:
        busy = busy_procs(IDLE_SUBSTRS)
        ready = world_landmarks_ready()
        if ready and not busy:
            log('  ready: world landmarks present and CPU idle.')
            return True
        why = []
        if not ready:
            why.append('waiting for reextract_pro_poses.py (no world_landmarks yet)')
        if busy:
            why.append(f'{len(busy)} heavy job(s) running: ' + ', '.join(c[:60] for _, c in busy))
        log('  not ready -- ' + '; '.join(why))
        time.sleep(poll_sec)
    log(f'  TIMED OUT after {max_wait_min} min waiting for readiness.')
    return False


def run(label, args, cwd=SCRIPTS_DIR, shell=False):
    printable = args if isinstance(args, str) else ' '.join(args)
    log(f'>>> STEP {label}: {printable}  (cwd={cwd})')
    t0 = time.time()
    proc = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1, shell=shell)
    for line in proc.stdout:
        line = line.rstrip('\n')
        print(line, flush=True)
        if _log_fh:
            _log_fh.write(line + '\n')
    proc.wait()
    dt = time.time() - t0
    if proc.returncode != 0:
        log(f'<<< STEP {label} FAILED (exit {proc.returncode}, {dt/60:.1f} min) -- stopping.')
        raise SystemExit(2)
    log(f'<<< STEP {label} ok ({dt/60:.1f} min)')


def main():
    global _log_fh
    ap = argparse.ArgumentParser()
    ap.add_argument('--now', action='store_true',
                    help='skip the wait-for-ready loop (abort if pose files lack world_landmarks)')
    ap.add_argument('--skip-baseline', action='store_true', help='skip step 0 (redesign_similarity eval)')
    ap.add_argument('--max-wait-min', type=int, default=720)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    _log_fh = open(LOG_PATH, 'w')
    log(f'metric-3D rebuild orchestrator -- log: {LOG_PATH}')

    if not args.skip_baseline:
        try:
            run('0 baseline (pre-rebuild similarity separation)',
                [PY, os.path.join(HERE, 'redesign_similarity.py'), 'eval'])
        except SystemExit:
            log('  baseline step failed (non-fatal) -- continuing to the readiness wait.')

    if args.now:
        if not world_landmarks_ready():
            log('--now: pro pose files still lack world_landmarks. Run '
                '02_pose_extraction/reextract_pro_poses.py first. Aborting.')
            raise SystemExit(1)
    else:
        if not wait_until_ready(args.max_wait_min):
            raise SystemExit(1)

    run('1 reslice (stride-1 + yaw -> pro_database.json)',
        [PY, os.path.join(SCRIPTS_DIR, '06_database_build', 'reslice_all_trajectories.py')])
    run('2 reanchor serves',
        [PY, os.path.join(SCRIPTS_DIR, '06_database_build', 'reanchor_pro_serves.py')])
    run('3 verify:db', 'npm run verify:db', cwd=os.path.join(REPO_DIR, 'backend'), shell=True)
    run('4 amateur-eval regression gate',
        [PY, os.path.join(HERE, 'evaluate_amateur_dataset.py'), '--no-backfill'])
    run('5 redesign_similarity cache (v3, ~30-45 min)',
        [PY, os.path.join(HERE, 'redesign_similarity.py'), 'cache'])
    run('6 redesign_similarity axes',
        [PY, os.path.join(HERE, 'redesign_similarity.py'), 'axes'])
    run('7 redesign_similarity rubric (payoff: forehand gap vs +5.8)',
        [PY, os.path.join(HERE, 'redesign_similarity.py'), 'rubric'])

    log('')
    log('DONE. Review the axes + rubric tables above (and in the log). Next, a human:')
    log('  - re-curate CURATED_AXES in redesign_similarity.py from the step-6 sep column')
    log('  - decide keep/revert on the rebuilt pro_database.json (backups are alongside it)')
    log(f'  full log: {LOG_PATH}')


if __name__ == '__main__':
    main()
