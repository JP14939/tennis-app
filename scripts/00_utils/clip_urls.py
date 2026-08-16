"""
Shared helper for attaching servable clip URLs (user_clip_url/pro_clip_url
+ cropped variants) onto a compare_swing.compare() result, mirroring what
backend/src/routes/analyse.js does for the live upload path (via
persistAndCrop()/croppedProClipPath() in backend/src/utils/videoCrop.js).
Node and Python can't share code, so this is the Python-side equivalent --
used by both scripts/15_batch_analysis/analyze_rallies_parallel.py (so
future batch-saved analyses get clip URLs from the start) and
scripts/15_batch_analysis/backfill_clip_urls.py (the one-off backfill for
analyses that were already saved without them).
"""
import os
import shutil
import sys

_UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_UTILS_DIR)
sys.path.insert(0, os.path.join(_SCRIPTS_DIR, '12_video_crop'))

from paths import DATA_DIR  # noqa: E402
from crop_to_subject import crop_to_subject  # noqa: E402

USER_CLIPS_DIR = os.path.join(DATA_DIR, 'runtime', 'user_clips')
PRO_CLIPS_DIR = os.path.join(DATA_DIR, '04_clips')
PRO_CLIPS_CROPPED_DIR = os.path.join(DATA_DIR, '04_clips_cropped')


def to_url(mount, root, abs_path):
    if not abs_path:
        return None
    rel = os.path.relpath(abs_path, root).replace(os.sep, '/')
    return f'{mount}/{rel}'


def attach_clip_urls(result, source_clip_path, dest_key):
    """
    Mutates `result` in place: copies source_clip_path into
    data/runtime/user_clips/<dest_key>/, crops it, and sets
    user_clip_url/user_clip_cropped_url on `result` plus
    pro_clip_url/pro_clip_cropped_url on result['matches'][0] from its
    already-known clip_path. Pro clips are pre-cropped for the whole
    database already (data/04_clips_cropped/, confirmed populated) -- this
    only looks the cropped path up, it never crops the pro side itself.

    `dest_key` just needs to be unique per swing (e.g. an analysis id, or
    a job/rally/swing composite) -- it's only used as a directory name.
    """
    dest_dir = os.path.join(USER_CLIPS_DIR, str(dest_key))
    dest_original = os.path.join(dest_dir, 'original.mp4')
    dest_cropped = os.path.join(dest_dir, 'cropped.mp4')
    os.makedirs(dest_dir, exist_ok=True)
    shutil.copyfile(source_clip_path, dest_original)

    cropped_ok = False
    try:
        cropped_ok = bool(crop_to_subject(dest_original, dest_cropped).get('cropped'))
    except Exception:
        cropped_ok = False

    result['user_clip_url'] = to_url('/user-clips', USER_CLIPS_DIR, dest_original)
    result['user_clip_cropped_url'] = to_url('/user-clips', USER_CLIPS_DIR, dest_cropped) if cropped_ok else None

    top = (result.get('matches') or [None])[0]
    if top and top.get('clip_path'):
        top['pro_clip_url'] = to_url('/pro-clips', PRO_CLIPS_DIR, top['clip_path'])
        shot_type = top.get('shot_type') or result.get('shot_type') or result.get('shotType')
        pro_cropped_path = os.path.join(PRO_CLIPS_CROPPED_DIR, shot_type, os.path.basename(top['clip_path']))
        if os.path.exists(pro_cropped_path):
            top['pro_clip_cropped_url'] = to_url('/pro-clips-cropped', PRO_CLIPS_CROPPED_DIR, pro_cropped_path)
