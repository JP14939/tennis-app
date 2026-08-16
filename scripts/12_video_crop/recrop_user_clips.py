"""
One-time re-crop of every already-saved user clip's cropped.mp4 using the
current crop_to_subject() parameters -- needed after the MARGIN change
(0.35 -> 1.6) that fixed racket/ball getting cut off the crop; this just
regenerates the cached cropped.mp4 next to each already-copied original.mp4
under data/runtime/user_clips/<id>/, it does not touch original.mp4 or any
DB rows (the URL scheme/filenames are unchanged, only the pixel content of
cropped.mp4).

Usage:
  python recrop_user_clips.py [--limit N]
"""
import argparse
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paths import DATA_DIR  # noqa: E402
from crop_to_subject import crop_to_subject  # noqa: E402

USER_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'user_clips')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None)
    args = parser.parse_args()

    # A couple of stray non-numeric dirs exist from old raw-upload temp names
    # that never got cleaned up -- sort digit dirs numerically, push anything
    # else to the end instead of crashing on an int/str comparison.
    dirs = sorted(
        (d for d in os.listdir(USER_CLIPS_DIR) if os.path.isdir(os.path.join(USER_CLIPS_DIR, d))),
        key=lambda d: (0, int(d)) if d.isdigit() else (1, d),
    )
    if args.limit:
        dirs = dirs[:args.limit]

    total = len(dirs)
    done = skipped = failed = 0
    for i, d in enumerate(dirs, 1):
        original = os.path.join(USER_CLIPS_DIR, d, 'original.mp4')
        cropped = os.path.join(USER_CLIPS_DIR, d, 'cropped.mp4')
        if not os.path.exists(original):
            skipped += 1
            continue
        try:
            result = crop_to_subject(original, cropped)
            if result.get('cropped'):
                done += 1
            else:
                print(f'  [{i}/{total}] FAILED {d}: {result.get("reason")}')
                failed += 1
        except Exception as e:
            print(f'  [{i}/{total}] ERROR {d}: {e}')
            failed += 1

        if i % 10 == 0 or i == total:
            print(f'  [{i}/{total}] done={done} skipped={skipped} failed={failed}')

    print(f'\nDone. done={done} skipped={skipped} failed={failed} total={total}')


if __name__ == '__main__':
    main()
