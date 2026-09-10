"""
Wait until the machine is free of other heavy Python jobs, then run a command.
CPU-only box -- running two YOLO trainings (or a training + the similarity
cache job) at once makes both crawl, so queue instead.

Usage
  python run_when_idle.py -- python 10_net_detection/train_yolo_pose_net_v10.py
  python run_when_idle.py --busy-substr redesign_similarity,train_ball,train_yolo -- <cmd...>
  python run_when_idle.py --max-wait-min 480 -- <cmd...>

Polls every 60 s. "Heavy" = any OTHER python process whose command line contains
one of --busy-substr (default: training / eval / cache jobs). Ignores itself,
jupyter, language servers, and the command it's about to launch.
"""
import argparse
import os
import subprocess
import sys
import time

DEFAULT_BUSY = ['train_yolo', 'train_ball', 'train_net', 'redesign_similarity',
                'evaluate_amateur', 'evaluate_shot', 'build_contact_student',
                'analyze_rallies', 'ingest_practice']


def busy_procs(substrs):
    me = os.getpid()
    try:
        out = subprocess.check_output(
            ['powershell', '-NoProfile', '-Command',
             "Get-CimInstance Win32_Process -Filter \"name like 'python%'\" | "
             "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"],
            text=True, stderr=subprocess.DEVNULL, timeout=30)
    except Exception:
        return []
    hits = []
    for line in out.splitlines():
        if '|' not in line:
            continue
        pid_s, _, cmd = line.partition('|')
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        if pid == me or 'run_when_idle' in cmd:
            continue
        if any(s and s in cmd for s in substrs):
            hits.append((pid, cmd.strip()[:110]))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--busy-substr', default=None,
                    help='comma-separated substrings that mark a heavy job (default: common training/eval jobs)')
    ap.add_argument('--poll-sec', type=int, default=60)
    ap.add_argument('--max-wait-min', type=int, default=720)
    ap.add_argument('--quiet-checks', type=int, default=2,
                    help='consecutive idle polls required before launching')
    ap.add_argument('cmd', nargs=argparse.REMAINDER)
    args = ap.parse_args()

    cmd = args.cmd
    if cmd and cmd[0] == '--':
        cmd = cmd[1:]
    if not cmd:
        sys.exit('give a command after --')

    substrs = ([s.strip() for s in args.busy_substr.split(',')] if args.busy_substr
               else DEFAULT_BUSY)
    deadline = time.time() + args.max_wait_min * 60
    clear_streak = 0
    while time.time() < deadline:
        hits = busy_procs(substrs)
        if hits:
            clear_streak = 0
            print(f'[{time.strftime("%H:%M:%S")}] waiting -- {len(hits)} heavy job(s):', file=sys.stderr)
            for pid, c in hits:
                print(f'    {pid}  {c}', file=sys.stderr)
        else:
            clear_streak += 1
            print(f'[{time.strftime("%H:%M:%S")}] idle ({clear_streak}/{args.quiet_checks})', file=sys.stderr)
            if clear_streak >= args.quiet_checks:
                print(f'[{time.strftime("%H:%M:%S")}] launching: {" ".join(cmd)}', file=sys.stderr)
                return subprocess.call(cmd)
        time.sleep(args.poll_sec)
    sys.exit(f'gave up after {args.max_wait_min} min still busy')


if __name__ == '__main__':
    main()
