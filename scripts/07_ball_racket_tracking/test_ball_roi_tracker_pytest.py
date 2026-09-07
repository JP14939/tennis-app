"""
Tests for ball_roi_tracker.refine_ball_track (pass 2).

Fake ball detector (no YOLO): a synthetic video plants a small white marker at
a known pixel per frame; the fake detect_ball scans whatever crop it is handed
and returns a box only when the marker is actually inside it -- so the crop
geometry, the back-mapping to original-frame space and the Mahalanobis accept
gate are all genuinely exercised, not stubbed.
"""
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ball_roi_tracker  # noqa: E402
from ball_roi_tracker import refine_ball_track  # noqa: E402

W, H, FPS = 640, 360, 30.0


def _make_video(tmp_path, marker_by_frame, n_frames):
    path = str(tmp_path / 'roi_test.mp4')
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'mp4v'), FPS, (W, H))
    for f in range(n_frames):
        frame = np.zeros((H, W, 3), dtype='uint8')
        m = marker_by_frame.get(f)
        if m is not None:
            x, y = int(round(m[0])), int(round(m[1]))
            cv2.rectangle(frame, (x - 3, y - 3), (x + 3, y + 3), (255, 255, 255), -1)
        writer.write(frame)
    writer.release()
    return path


class _FakeDetectBall:
    """Stands in for racket_tracker.detect_ball. Finds the brightest blob in
    the crop it is given; returns its bounding box in crop-pixel space."""

    def __init__(self):
        self.calls = []

    def __call__(self, image, conf_threshold=0.15, imgsz=None):
        self.calls.append({'conf': conf_threshold, 'imgsz': imgsz, 'shape': image.shape[:2]})
        mask = image.max(axis=2) > 200
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return None, None
        return [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())], 0.9


def _det(frame, ball_center=None):
    d = {'frame': frame, 'racket_box': None, 'racket_conf': None,
         'ball_box': None, 'ball_conf': None}
    if ball_center is not None:
        x, y = ball_center
        d['ball_box'] = [x - 3, y - 3, x + 3, y + 3]
        d['ball_conf'] = 0.9
    return d


@pytest.fixture(autouse=True)
def _patch_detect_ball(monkeypatch):
    fake = _FakeDetectBall()
    monkeypatch.setattr(ball_roi_tracker, 'detect_ball', fake)
    return fake


# linear path: x = 100 + 8*f, y = 180 (constant)
def _true_pos(f):
    return (100 + 8 * f, 180)


def test_cold_start_returns_pass1_behaviour_unchanged(tmp_path):
    # only 2 ball detections -- below MIN_BOOTSTRAP
    dets = [_det(0, _true_pos(0)), _det(1, _true_pos(1))] + [_det(f) for f in range(2, 12)]
    video = _make_video(tmp_path, {}, 12)
    res = refine_ball_track(video, dets, FPS)
    assert res.bootstrapped is False
    assert res.redetect_log == []
    assert all(d.get('ball_source') in (None, 'pass1') for d in res.augmented_dets)


def test_recovers_a_missed_frame_via_roi(tmp_path, _patch_detect_ball):
    frames = list(range(16))
    dets = [_det(f, _true_pos(f)) if f != 8 else _det(f) for f in frames]
    markers = {f: _true_pos(f) for f in frames}  # the ball IS there on frame 8, pass 1 just missed it
    video = _make_video(tmp_path, markers, 16)

    res = refine_ball_track(video, dets, FPS)
    assert res.bootstrapped is True
    by_frame = {d['frame']: d for d in res.augmented_dets}
    assert by_frame[8]['ball_box'] is not None
    assert by_frame[8]['ball_source'] == 'roi_missed'
    # recovered centre lands near the true ball, not clutter
    from racket_tracker import _center_in_original_space
    cx, cy = _center_in_original_space(by_frame[8]['ball_box'], by_frame[8])
    assert abs(cx - _true_pos(8)[0]) < 12
    assert abs(cy - _true_pos(8)[1]) < 12


def test_hallucinated_roi_box_rejected_by_filter_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(ball_roi_tracker, 'ROI_MIN_HALF', 200.0)
    monkeypatch.setattr(ball_roi_tracker, 'ROI_MAX_HALF', 200.0)
    frames = list(range(16))
    dets = [_det(f, _true_pos(f)) if f != 8 else _det(f) for f in frames]
    # marker on frame 8 is 150px off where a constant-velocity ball would be
    markers = {f: _true_pos(f) for f in frames if f != 8}
    markers[8] = (_true_pos(8)[0] + 150, _true_pos(8)[1])
    video = _make_video(tmp_path, markers, 16)

    res = refine_ball_track(video, dets, FPS)
    by_frame = {d['frame']: d for d in res.augmented_dets}
    assert by_frame[8]['ball_box'] is None  # not added
    f8 = [e for e in res.redetect_log if e['frame'] == 8]
    assert f8 and f8[0]['result'] == 'rejected_filter_gate'


def test_gated_outlier_is_retried_and_replaced(tmp_path):
    frames = list(range(16))
    dets = []
    for f in frames:
        if f == 8:
            dets.append(_det(f, (_true_pos(f)[0] + 120, _true_pos(f)[1] + 60)))  # decoy pass-1 box
        else:
            dets.append(_det(f, _true_pos(f)))
    markers = {f: _true_pos(f) for f in frames}  # real ball is on the CV path
    video = _make_video(tmp_path, markers, 16)

    res = refine_ball_track(video, dets, FPS)
    by_frame = {d['frame']: d for d in res.augmented_dets}
    assert by_frame[8]['ball_source'] == 'roi_gated'
    from racket_tracker import _center_in_original_space
    cx, _ = _center_in_original_space(by_frame[8]['ball_box'], by_frame[8])
    assert abs(cx - _true_pos(8)[0]) < 12


def test_budget_caps_detector_calls(tmp_path, _patch_detect_ball):
    frames = list(range(30))
    missed = set(range(6, 26))
    dets = [_det(f) if f in missed else _det(f, _true_pos(f)) for f in frames]
    markers = {f: _true_pos(f) for f in frames}
    video = _make_video(tmp_path, markers, 30)

    refine_ball_track(video, dets, FPS, budget_redetections=5)
    assert len(_patch_detect_ball.calls) <= 5


def test_roi_imgsz_override_reaches_detect_ball(tmp_path, _patch_detect_ball):
    frames = list(range(16))
    dets = [_det(f, _true_pos(f)) if f != 8 else _det(f) for f in frames]
    video = _make_video(tmp_path, {f: _true_pos(f) for f in frames}, 16)

    refine_ball_track(video, dets, FPS, roi_imgsz=128)
    assert _patch_detect_ball.calls
    assert all(c['imgsz'] == 128 for c in _patch_detect_ball.calls)


def test_contact_safe_withholds_recoveries_in_guard_window(tmp_path):
    frames = list(range(20))
    # miss frames 9,10,11 around a contact at frame 10
    missed = {9, 10, 11}
    dets = [_det(f) if f in missed else _det(f, _true_pos(f)) for f in frames]
    video = _make_video(tmp_path, {f: _true_pos(f) for f in frames}, 20)

    res = refine_ball_track(video, dets, FPS, contact_frame=10)
    aug = {d['frame']: d for d in res.augmented_dets}
    safe = {d['frame']: d for d in res.contact_safe_dets}
    # at least one ROI recovery landed in the window and shows in augmented...
    assert any(aug[f]['ball_box'] is not None and str(aug[f].get('ball_source', '')).startswith('roi')
               for f in missed)
    # ...but is withheld from contact_safe
    for f in missed:
        if str(aug[f].get('ball_source', '')).startswith('roi'):
            assert safe[f]['ball_box'] is None
            assert safe[f]['ball_source'] == 'roi_withheld_contact'


def test_backward_pass_recovers_an_early_frame(tmp_path):
    frames = list(range(16))
    # ball missing on the approach (frames 0-3), locked from frame 4 on
    dets = [_det(f) if f < 4 else _det(f, _true_pos(f)) for f in frames]
    video = _make_video(tmp_path, {f: _true_pos(f) for f in frames}, 16)

    res = refine_ball_track(video, dets, FPS, backward_pass=True)
    by_frame = {d['frame']: d for d in res.augmented_dets}
    recovered_early = [f for f in (1, 2, 3)
                       if by_frame.get(f, {}).get('ball_box') is not None]
    assert recovered_early

    res_no_bwd = refine_ball_track(video, dets, FPS, backward_pass=False)
    bf2 = {d['frame']: d for d in res_no_bwd.augmented_dets}
    assert sum(bf2.get(f, {}).get('ball_box') is not None for f in (1, 2, 3)) <= len(recovered_early)
