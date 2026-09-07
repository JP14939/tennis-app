"""
Geometry tests for near_court_ball_tracker -- crop rect + fallback chain.
No YOLO / MediaPipe: _near_court_crop_rect is pure math, and the fallback
chain is exercised with detect_ball / the pose bbox monkeypatched.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import near_court_ball_tracker as nct  # noqa: E402
from near_court_ball_tracker import (  # noqa: E402
    _near_court_crop_rect, _crop_and_upscale_rect, _union_bbox,
)

W, H = 1920, 1080


def _player_bbox(cx=960, cy=800, w=300, h=450):
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def test_back_view_rect_reaches_net_and_keeps_the_feet():
    # short player near the net -> the crop reaches all the way to net_y
    bbox = _player_bbox(cy=850, h=260)
    net_y_px = 0.55 * H
    rect = _near_court_crop_rect(bbox, net_y_px, 0.2 * W, 0.8 * W, 'back', W, H)
    assert rect is not None
    x0, y0, x1, y1 = rect
    assert x0 <= bbox[0] and x1 >= bbox[2]      # contains the player bbox
    assert y1 >= bbox[3] - 1                    # bottom (feet) not trimmed
    assert y0 <= net_y_px - nct.NET_MARGIN_FRAC * H + 1   # top edge at the net
    assert max(x1 - x0, y1 - y0) <= nct.CROP_MAX_LONG_SIDE_PX


def test_tall_player_far_from_net_is_size_capped_but_still_extends_upward():
    bbox = _player_bbox(cy=800, h=450)      # feet at 1025, head at 575
    net_y_px = 0.35 * H                     # 378
    rect = _near_court_crop_rect(bbox, net_y_px, 0.2 * W, 0.8 * W, 'back', W, H)
    assert rect is not None
    _, y0, _, y1 = rect
    assert y0 < bbox[1]                     # extended net-ward past the player's head
    assert y1 >= bbox[3] - 1               # feet kept
    assert (y1 - y0) <= nct.CROP_MAX_LONG_SIDE_PX


def test_non_back_view_returns_none():
    bbox = _player_bbox()
    assert _near_court_crop_rect(bbox, 0.35 * H, 0, W, 'front', W, H) is None
    assert _near_court_crop_rect(bbox, 0.35 * H, 0, W, 'unknown', W, H) is None


def test_no_net_still_produces_a_rect_from_the_player_height():
    # detect_view_direction can return 'back' via its Hough fallback with no
    # keypoint net_y -- the crop then extends a fixed multiple of player height
    rect = _near_court_crop_rect(_player_bbox(cy=850, h=260), None, None, None, 'back', W, H)
    assert rect is not None
    _, y0, _, y1 = rect
    assert y0 < _player_bbox(cy=850, h=260)[1]      # extended upward
    assert (y1 - y0) <= nct.CROP_MAX_LONG_SIDE_PX


def test_oversized_extension_is_clamped_not_rejected():
    # a large but plausible player (600px tall, 320 wide) far from the net
    bbox = _player_bbox(cx=960, cy=740, w=320, h=600)   # head 440, feet 1040
    rect = _near_court_crop_rect(bbox, 0.05 * H, 0, W, 'back', W, H)
    assert rect is not None
    x0, y0, x1, y1 = rect
    assert (y1 - y0) <= nct.CROP_MAX_LONG_SIDE_PX + 1
    assert y0 < bbox[1]                                 # still extended net-ward


def test_crop_and_upscale_rect_roundtrips_a_point():
    frame = np.zeros((H, W, 3), dtype='uint8')
    rect = (800, 300, 1100, 800)  # 300x500 -> upscaled so long side hits 640
    crop, scale, x0, y0 = _crop_and_upscale_rect(frame, rect)
    assert (x0, y0) == (800, 300)
    assert abs(scale - 640 / 500) < 1e-6
    # a point at original (1000, 600) maps to crop-space and back
    cx_crop = (1000 - x0) * scale
    cy_crop = (600 - y0) * scale
    from racket_tracker import _center_in_original_space
    box = [cx_crop - 2, cy_crop - 2, cx_crop + 2, cy_crop + 2]
    ox, oy = _center_in_original_space(box, {'crop_scale': scale, 'crop_x0': x0, 'crop_y0': y0})
    assert abs(ox - 1000) < 1 and abs(oy - 600) < 1


def test_union_bbox():
    assert _union_bbox([None, (10, 20, 30, 40), (5, 25, 20, 50), None]) == (5, 20, 30, 50)
    assert _union_bbox([None, None]) is None


# ---- fallback chain ----
class _FakeCap:
    """Minimal cv2.VideoCapture stand-in over a list of frames."""
    def __init__(self, frames, fps=60.0):
        self._frames = frames
        self._i = 0
        self._fps = fps

    def isOpened(self):
        return True

    def get(self, prop):
        import cv2
        return {cv2.CAP_PROP_FPS: self._fps, cv2.CAP_PROP_FRAME_WIDTH: W,
                cv2.CAP_PROP_FRAME_HEIGHT: H}.get(prop, 0)

    def set(self, prop, val):
        import cv2
        if prop == cv2.CAP_PROP_POS_FRAMES:
            self._i = int(val)

    def read(self):
        if self._i >= len(self._frames):
            return False, None
        f = self._frames[self._i]
        self._i += 1
        return True, f

    def release(self):
        pass


@pytest.fixture
def _fake_video(monkeypatch):
    frames = [np.full((H, W, 3), i, dtype='uint8') for i in range(6)]
    monkeypatch.setattr(nct.cv2, 'VideoCapture', lambda *a, **k: _FakeCap(frames))
    return frames


def test_fallback_full_frame_when_no_pose(monkeypatch, _fake_video):
    monkeypatch.setattr(nct, '_pose_bbox_from_contact_frame', lambda *a, **k: None)
    called = {}
    monkeypatch.setattr(nct.rt, 'track_racket_and_ball',
                        lambda video_path, frame_range=None: (called.setdefault('hit', True), ([], 60.0))[1])
    nct.track_ball_near_court('v.mp4', (0, 5), static_bbox=None, net_line=None, view_direction='back')
    assert called.get('hit')


def test_fallback_pose_bbox_when_no_net(monkeypatch, _fake_video):
    monkeypatch.setattr(nct, 'detect_ball', lambda crop, imgsz=None: ([1.0, 1.0, 3.0, 3.0], 0.9))
    dets, fps = nct.track_ball_near_court('v.mp4', (0, 5), static_bbox=_player_bbox(),
                                          net_line=None, view_direction='back')
    assert fps == 60.0 and len(dets) == 5
    assert all('crop_scale' in d for d in dets if d['ball_box'])


def test_near_court_path_when_all_inputs_present(monkeypatch, _fake_video):
    seen = []
    monkeypatch.setattr(nct, 'detect_ball',
                        lambda crop, imgsz=None: (seen.append(crop.shape), ([1.0, 1.0, 3.0, 3.0], 0.9))[1])
    dets, _ = nct.track_ball_near_court('v.mp4', (0, 5), static_bbox=_player_bbox(),
                                        net_line=(0.2, 0.8, 0.35), view_direction='back')
    assert len(dets) == 5 and seen
    # crop offset is the near-court rect's top-left, consistent across frames
    offs = {(d['crop_x0'], d['crop_y0']) for d in dets if d['ball_box']}
    assert len(offs) == 1
