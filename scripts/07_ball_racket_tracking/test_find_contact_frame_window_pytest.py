"""Window / method-precedence logic of racket_tracker.find_contact_frame.

Pure geometry over synthetic detection lists -- no cv2, no YOLO, no video.
(HANDOVER.md once claimed a test of this name existed; it was lost. This
restores direct coverage of the window clipping + the gap-vs-proximity-vs-
fallback precedence.)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from racket_tracker import (  # noqa: E402
    find_contact_frame, contact_frame_meta, _window_dets, _find_gap_contact,
)

FPS = 30.0


def _det(frame, racket=None, ball=None):
    return {
        'frame': frame,
        'racket_box': racket, 'racket_conf': 0.8 if racket else None,
        'ball_box': ball, 'ball_conf': 0.7 if ball else None,
    }


def _box(cx, cy, s=10):
    return [cx - s, cy - s, cx + s, cy + s]


def test_window_dets_clips_to_search_window():
    dets = [_det(f) for f in range(0, 100)]
    # 0.3s * 30fps = 9 frames either side of frame 50
    w = _window_dets(dets, 50, FPS, 0.3)
    assert [d['frame'] for d in w] == list(range(41, 60))


def test_serve_wider_search_window_admits_further_frames():
    dets = [_det(f) for f in range(0, 100)]
    narrow = _window_dets(dets, 50, FPS, 0.3)
    wide = _window_dets(dets, 50, FPS, 0.45)
    assert len(wide) > len(narrow)
    assert min(d['frame'] for d in wide) < min(d['frame'] for d in narrow)


def test_occlusion_gap_midpoint_wins_over_proximity():
    # Ball tracked approaching, vanishes frames 49-52, reappears departing.
    # Racket sits at (100,100) throughout; nearest ball detection is frame 48.
    dets = []
    for f in range(40, 60):
        ball = None if 49 <= f <= 52 else _box(100 + (f - 50) * 4, 100)
        dets.append(_det(f, racket=_box(100, 100), ball=ball))
    frame, conf, method = find_contact_frame(dets, 50, FPS)
    assert method.startswith('ball_occlusion_gap')
    assert frame == 50  # round((48 + 53) / 2)
    assert 0.3 <= conf <= 1.0


def test_proximity_used_when_no_gap():
    # Ball present every frame (no vanish) -> no occlusion gap; pick the frame
    # where ball is closest to the racket.
    dets = []
    for f in range(45, 56):
        offset = abs(f - 51) * 5
        dets.append(_det(f, racket=_box(100, 100), ball=_box(100 + offset, 100)))
    frame, conf, method = find_contact_frame(dets, 50, FPS)
    assert method == 'ball_racket_proximity'
    assert frame == 51


def test_falls_back_to_wrist_velocity_when_no_evidence():
    dets = [_det(f) for f in range(45, 56)]  # no racket, no ball anywhere
    frame, conf, method = find_contact_frame(dets, 50, FPS)
    assert (frame, conf, method) == (50, 0.3, 'wrist_velocity_fallback')


def test_gap_outside_window_is_ignored():
    # The only gap is far from the anchor -> not seen inside the 0.3s window.
    dets = [_det(f, racket=_box(100, 100), ball=_box(100, 100)) for f in range(45, 56)]
    dets += [_det(f) for f in (70, 71)]  # nothing near frame 80
    dets.append(_det(80, ball=_box(0, 0)))
    frame, _, method = find_contact_frame(dets, 50, FPS)
    assert method == 'ball_racket_proximity'


def test_find_gap_contact_requires_real_vanish():
    # Ball detected on consecutive frames -> gap size 1 -> not an occlusion.
    dets = [_det(f, ball=_box(f, f)) for f in range(45, 56)]
    assert _find_gap_contact(dets) is None


def test_contact_frame_meta_counts_track_search_window():
    dets = [_det(f, racket=_box(1, 1), ball=_box(2, 2)) for f in range(0, 100)]
    narrow = contact_frame_meta(dets, 50, FPS, search_window_sec=0.3)
    wide = contact_frame_meta(dets, 50, FPS, search_window_sec=0.45)
    assert wide['window_dets_total'] > narrow['window_dets_total']
    assert narrow['n_both_present'] == narrow['window_dets_total']
