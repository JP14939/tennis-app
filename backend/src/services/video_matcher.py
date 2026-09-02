"""
1v1 video matcher — entry point for Node.js backend.

Called by the Express backend via child_process.spawn.
Writes progress/debug to stderr and a single JSON object to stdout.

Usage:
  python video_matcher.py <reference_video> <your_video> <shot_type> [--contact-a SEC] [--contact-b SEC]

Output (stdout): see compare_videos.compare_videos() docstring.
On error: { "error": "description" }
"""

import sys
import os
import json
import argparse

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scripts', '08_comparison_engine'))
sys.path.insert(0, SCRIPTS_DIR)

from compare_videos import compare_videos


def main():
    parser = argparse.ArgumentParser(description='Compare two swing videos directly (no pro database)')
    parser.add_argument('reference_video', help='Video you want to copy')
    parser.add_argument('your_video', help='Your swing video')
    parser.add_argument('shot_type', choices=['forehand', 'backhand', 'serve'])
    parser.add_argument('--contact-a', type=float, default=None, help='User-marked contact time in reference video (seconds)')
    parser.add_argument('--contact-b', type=float, default=None, help='User-marked contact time in your video (seconds)')
    args = parser.parse_args()

    for path, label in [(args.reference_video, 'reference'), (args.your_video, 'your')]:
        if not os.path.exists(path):
            print(json.dumps({'error': f'{label.capitalize()} video not found: {path}'}))
            sys.exit(1)

    try:
        result = compare_videos(args.reference_video, args.your_video, args.shot_type,
                                 contact_a=args.contact_a, contact_b=args.contact_b)
        print(json.dumps(result))
    except Exception as e:
        # Same reasoning as pro_matcher.py's except block: some underlying
        # failures echo this process's own argv (the full server-side upload
        # path for either video) straight into the message, which then flows
        # unmodified back to the authenticated caller of POST
        # /api/compare-videos. Redact both known argv paths to their
        # basenames before the message leaves this process.
        message = str(e).replace(args.reference_video, os.path.basename(args.reference_video))
        message = message.replace(args.your_video, os.path.basename(args.your_video))
        print(json.dumps({'error': message}))
        sys.exit(1)


if __name__ == '__main__':
    main()
