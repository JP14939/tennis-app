"""
Shared ffmpeg trim helpers, split out of cut_pro_clip.py (2026-08-27) so
split_pro_clip.py can reuse the exact same trimming logic instead of
duplicating it -- two real call sites with identical needs, not a
speculative abstraction. No behavior change: same ffmpeg args as before.
"""
import os
import subprocess
import tempfile

import cv2
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


def get_duration_sec(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return frames / fps if fps else 0


def get_fps(path):
    """Playback fps of a cut clip file -- ffmpeg trims (trim_to_file/
    trim_in_place above) never pass -r, so a clip's fps always matches its
    source video's, confirmed by every clip on disk. Used by the Pro Clip
    Review tool's frame-accurate contact-time UI (DevProClipReviewScreen.js)
    to convert between seconds and frame numbers for display/stepping."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.release()
    return fps


def trim_to_file(src_path, dest_path, start_sec, end_sec):
    """Re-encodes [start_sec, end_sec] of src_path into a NEW file at
    dest_path -- used for the half of a split clip that becomes a brand-new
    database entry, as opposed to trim_in_place()'s "replace the original"."""
    subprocess.run(
        [FFMPEG_EXE, '-y', '-i', src_path, '-ss', str(start_sec), '-to', str(end_sec),
         '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', dest_path],
        check=True, capture_output=True, text=True,
    )


def trim_in_place(path, start_sec, end_sec):
    dir_ = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(suffix='.mp4', dir=dir_)
    os.close(fd)
    try:
        trim_to_file(path, tmp_path, start_sec, end_sec)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
