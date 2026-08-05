"""
Rally detector -- entry point for Node.js backend.

Called by the Express backend via child_process.spawn, run in the
background (not awaited by the upload response) since pose extraction over
a full match video takes real time.

Usage:
  python rally_detector.py <video_path> <output_dir>

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
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(json.dumps({'error': f'Video not found: {args.video}'}))
        sys.exit(1)

    try:
        result = detect_rallies(args.video, args.output_dir)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
