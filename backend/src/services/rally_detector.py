"""
Rally detector -- entry point for Node.js backend.

Called by the Express backend via child_process.spawn, run in the
background (not awaited by the upload response) since pose extraction over
a full match video takes real time.

Usage:
  python rally_detector.py <video_path> <output_dir> [--no-trajectory] [--handedness left|right]

Output (stdout): see detect_rallies.detect_rallies() docstring.
On error: { "error": "description" }
"""

import sys
import os
import json
import argparse

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scripts', '11_highlight_clipping'))
sys.path.insert(0, SCRIPTS_DIR)

from detect_rallies import detect_rallies


def main():
    parser = argparse.ArgumentParser(description='Detect rally boundaries in a match video and clip each one out')
    parser.add_argument('video', help='Path to full match/practice video')
    parser.add_argument('output_dir', help='Directory to write rally clips into')
    parser.add_argument('--no-trajectory', action='store_true',
                        help='Disable trajectory-kNN FH/BH (phone footage -- broadcast pool mislabels it)')
    parser.add_argument('--handedness', choices=['right', 'left'], default='right')
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(json.dumps({'error': f'Video not found: {args.video}'}))
        sys.exit(1)

    try:
        result = detect_rallies(args.video, args.output_dir,
                                use_trajectory=not args.no_trajectory,
                                handedness=args.handedness)
        print(json.dumps(result))
    except Exception as e:
        # Same reasoning as pro_matcher.py's except block: some underlying
        # failures echo this process's own argv (the server-side upload path
        # or the runtime output directory) straight into the message, which
        # then flows unmodified into highlight_jobs.error and back to the
        # authenticated job owner via GET /api/highlights/jobs. Redact both
        # known argv paths to their basenames before the message leaves this
        # process.
        message = str(e).replace(args.video, os.path.basename(args.video))
        message = message.replace(args.output_dir, os.path.basename(args.output_dir))
        print(json.dumps({'error': message}))
        sys.exit(1)


if __name__ == '__main__':
    main()
