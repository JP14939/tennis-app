"""
Every clip-writing script in this codebase writes MP4s via
cv2.VideoWriter_fourcc(*'mp4v'). On this machine that maps (via OpenCV's
FFmpeg backend) to old MPEG-4 Part 2 video -- fourcc 'FMP4' when read back
-- which no browser's <video> element can decode. Confirmed directly with
cv2.CAP_PROP_FOURCC on real clips: every rally/crop/reel clip ever produced
by this pipeline reads 'FMP4'. cv2.VideoWriter can't produce real H.264
either on this machine (missing openh264-2.5.0-win64.dll -- avc1/H264/X264
fourccs all silently produce a corrupt "moov atom not found" file), and
there's no system ffmpeg on PATH.

reencode_to_h264() fixes an already-written clip in place using
imageio-ffmpeg's bundled static ffmpeg binary (pip-installed into this
venv, no system/admin install). Callers should write with cv2 exactly as
before, then call this once right after release().
"""
import os
import subprocess
import tempfile

import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


def is_real_h264(path):
    """True if `path` already reads back as h264/avc1 -- used to skip
    files that don't need (re-)encoding, e.g. during the one-off backfill."""
    import cv2
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return False
    fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc = ''.join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)]).lower()
    cap.release()
    return fourcc in ('h264', 'avc1')


def reencode_to_h264(path):
    """
    Re-encodes the video at `path` to real H.264 in place. Writes to a temp
    file in the same directory first and atomically os.replace()s over the
    original -- never leaves a half-written file at `path` if ffmpeg fails
    partway through, and no `.bak` copy is kept (disk space over keeping
    stale mpeg4 copies around, unlike the one-off manual fix this replaces).

    None of this pipeline's clips have an audio stream (verified directly
    with ffmpeg -i against a real clip), so no -c:a flag is needed -- ffmpeg
    just omits an audio stream when the source has none.

    Raises subprocess.CalledProcessError if ffmpeg fails; callers should let
    that propagate rather than silently leaving a broken clip in place.
    """
    dir_ = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(suffix='.mp4', dir=dir_)
    os.close(fd)
    try:
        subprocess.run(
            [FFMPEG_EXE, '-y', '-i', path, '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
             '-movflags', '+faststart', tmp_path],
            check=True, capture_output=True, text=True,
        )
        os.replace(tmp_path, path)
    except subprocess.CalledProcessError:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
