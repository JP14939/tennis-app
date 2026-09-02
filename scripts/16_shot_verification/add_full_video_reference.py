"""
Makes a highlight job's raw source video browsable in the Dev Page's Swing
Review tool for context, WITHOUT it ever being run through pose
extraction/swing detection (see list_swing_candidates.py's FULL_VIDEO_PREFIX
comment for why that matters -- a full match video through that per-frame
pipeline hung job 9 for 10+ minutes until the request timed out).

Hardlinks the source video into the job's clip directory under the
`full_video` prefix list_swing_candidates.py looks for -- a hardlink, not a
copy, so this costs no extra disk space and the source file is untouched by
anything done here or later (deleting the link never deletes the source).

Usage:
  python add_full_video_reference.py <job_id> <source_video_path>
"""
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
from paths import DATA_DIR  # noqa: E402

HIGHLIGHT_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'highlight_clips', '13')


def add_full_video_reference(job_id, source_video_path):
    if not os.path.isfile(source_video_path):
        raise FileNotFoundError(f'Source video not found: {source_video_path}')

    job_dir = os.path.join(HIGHLIGHT_CLIPS_DIR, str(job_id))
    os.makedirs(job_dir, exist_ok=True)

    # Always .mp4 regardless of the source's real extension (e.g. .MOV) --
    # list_swing_candidates.py's FULL_VIDEO_PREFIX glob only matches
    # '*.mp4', and PlatformVideo/express.static both key off the extension
    # for content-type, not the actual container -- same convention the
    # original ad-hoc version of this hack already relied on.
    dest_path = os.path.join(job_dir, 'full_video.mp4')
    if os.path.exists(dest_path):
        raise FileExistsError(f'{dest_path} already exists -- remove it first if you want to replace it')

    try:
        os.link(source_video_path, dest_path)
    except OSError as e:
        raise OSError(
            f"Couldn't hardlink {source_video_path} -> {dest_path} ({e}). "
            'This usually means the source and destination are on different '
            'drives/filesystems, which hardlinks cannot cross -- copy the '
            'file there manually instead (it will use real disk space).'
        ) from e

    print(f'Linked {source_video_path} -> {dest_path}')


def main():
    if len(sys.argv) != 3:
        print('usage: add_full_video_reference.py <job_id> <source_video_path>', file=sys.stderr)
        sys.exit(1)
    add_full_video_reference(sys.argv[1], sys.argv[2])


if __name__ == '__main__':
    main()
