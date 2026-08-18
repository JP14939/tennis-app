"""Regression test: extract_clip() used to read end_frame - start_frame
frames (excluding end_frame itself) even though every caller treats
end_frame as INCLUSIVE (e.g. detect_rallies.py's
`end_frame = min(total_frames - 1, int(end_sec * fps))`), silently
truncating every extracted clip by exactly one frame."""
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_clips import extract_clip  # noqa: E402

FRAME_SIZE = (64, 48)  # w, h -- tiny, just needs to be a valid video
TOTAL_SOURCE_FRAMES = 20
FPS = 10


@pytest.fixture
def synthetic_video(tmp_path):
    """A short synthetic video where frame i is filled with pixel value i,
    so which frames actually got read back out is directly verifiable."""
    path = str(tmp_path / 'source.mp4')
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(path, fourcc, FPS, FRAME_SIZE)
    for i in range(TOTAL_SOURCE_FRAMES):
        frame = np.full((FRAME_SIZE[1], FRAME_SIZE[0], 3), i, dtype='uint8')
        writer.write(frame)
    writer.release()
    return path


def count_frames(video_path):
    cap = cv2.VideoCapture(video_path)
    n = 0
    while True:
        ret, _ = cap.read()
        if not ret:
            break
        n += 1
    cap.release()
    return n


@pytest.mark.parametrize('start_frame,end_frame,expected_count', [
    (0, 0, 1),    # a single-frame clip: 1 read, not 0
    (5, 5, 1),
    (2, 7, 6),    # inclusive range of 6 frames (2,3,4,5,6,7)
    (0, 19, 20),  # the whole source video
])
def test_extract_clip_frame_count_is_inclusive(tmp_path, synthetic_video, start_frame, end_frame, expected_count):
    cap = cv2.VideoCapture(synthetic_video)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_path = str(tmp_path / f'clip_{start_frame}_{end_frame}.mp4')

    extract_clip(cap, start_frame, end_frame, out_path, FPS, fourcc)
    cap.release()

    assert count_frames(out_path) == expected_count
