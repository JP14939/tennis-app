"""
Pro swing matcher — entry point for Node.js backend.

Called by the Express backend via child_process.spawn.
Writes progress/debug to stderr and a single JSON object to stdout.

Usage:
  python pro_matcher.py <video_path> <shot_type> [--top N] [--angle-window N] [--contact-time SEC]

Output (stdout):
  {
    "user_video": "...",
    "shot_type": "forehand",
    "user_angle": 38.2,
    "angle_label": "Semi-front",
    "angle_conf": 0.87,
    "matches": [
      {
        "rank": 1,
        "pro_id": "forehand_0142",
        "similarity": 72.4,
        "clip_path": "...",
        "pro_angle": 35.1,
        "tips": ["..."]
      }
    ]
  }

On error:
  { "error": "description" }
"""

import sys
import os
import json
import argparse

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scripts', '08_comparison_engine'))
sys.path.insert(0, SCRIPTS_DIR)

from compare_swing import compare


def main():
    parser = argparse.ArgumentParser(description='Match a user swing video against the pro database')
    parser.add_argument('video', help='Path to user swing video')
    parser.add_argument('shot_type', choices=['forehand', 'backhand', 'serve'])
    parser.add_argument('--top', type=int, default=3, help='Number of pro matches to return')
    parser.add_argument('--angle-window', type=int, default=20, help='Angle filter window in degrees')
    parser.add_argument('--contact-time', type=float, default=None, help='User-marked contact time in seconds')
    parser.add_argument('--view-direction-hint', choices=['front', 'back'], default=None,
                         help='User-stated filming position, used only if server-side detection is inconclusive')
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(json.dumps({'error': f'Video not found: {args.video}'}))
        sys.exit(1)

    try:
        result = compare(args.video, args.shot_type, top_n=args.top, angle_window=args.angle_window,
                          contact_time_sec=args.contact_time, view_direction_hint=args.view_direction_hint)
        print(json.dumps(result))
    except Exception as e:
        # Some failures inside compare() (e.g. "Cannot open video: <path>")
        # echo this process's own argv -- the full server-side upload path --
        # straight into the exception message. That message flows unmodified
        # through runPythonJson.js's nonzero_exit branch back to any
        # authenticated caller of POST /api/analyse, so a deliberately
        # corrupted/unreadable upload could be used to probe the server's
        # internal directory layout. Redact the known argv path down to its
        # basename before it leaves this process; every other message (the
        # overwhelming majority, which never mention a path) is unaffected.
        message = str(e).replace(args.video, os.path.basename(args.video))
        print(json.dumps({'error': message}))
        sys.exit(1)


if __name__ == '__main__':
    main()
