"""Coverage for ball_departure_confirmed(): independent evidence a swing
was a real strike -- after contact, does the ball's distance from the
racket's contact-frame position show a clear net-increasing trend?
Meant to rescue swings find_contact_frame() otherwise falls back to
'wrist_velocity_fallback' for (no racket/ball proximity or occlusion-gap
evidence). Must never invent a signal from data that isn't there."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from racket_tracker import ball_departure_confirmed  # noqa: E402

FPS = 30.0
RACKET_AT_CONTACT = (500.0, 300.0)


def _det(frame, ball_center=None, racket_box=RACKET_AT_CONTACT):
    return {
        'frame': frame,
        'racket_box': [racket_box[0] - 5, racket_box[1] - 5, racket_box[0] + 5, racket_box[1] + 5] if racket_box else None,
        'racket_conf': 0.9,
        'ball_box': [ball_center[0] - 3, ball_center[1] - 3, ball_center[0] + 3, ball_center[1] + 3] if ball_center else None,
        'ball_conf': 0.5 if ball_center else None,
    }


def test_clearly_receding_ball_confirms():
    contact_frame = 10
    detections = [_det(contact_frame, ball_center=RACKET_AT_CONTACT)]
    for i in range(1, 8):
        detections.append(_det(contact_frame + i, ball_center=(500.0 + i * 20, 300.0)))
    confirmed, confidence = ball_departure_confirmed(detections, contact_frame, FPS)
    assert confirmed is True
    assert confidence > 0.0


def test_stationary_ball_does_not_confirm():
    contact_frame = 10
    detections = [_det(contact_frame + i, ball_center=(510.0, 305.0)) for i in range(8)]
    confirmed, confidence = ball_departure_confirmed(detections, contact_frame, FPS)
    assert confirmed is False
    assert confidence == 0.0


def test_approaching_ball_does_not_confirm():
    contact_frame = 10
    detections = [_det(contact_frame, ball_center=(700.0, 300.0))]
    for i in range(1, 8):
        detections.append(_det(contact_frame + i, ball_center=(700.0 - i * 20, 300.0)))
    confirmed, confidence = ball_departure_confirmed(detections, contact_frame, FPS)
    assert confirmed is False
    assert confidence == 0.0


def test_no_racket_detection_at_contact_frame_never_confirms():
    contact_frame = 10
    detections = [_det(contact_frame, ball_center=RACKET_AT_CONTACT, racket_box=None)]
    for i in range(1, 8):
        detections.append(_det(contact_frame + i, ball_center=(500.0 + i * 20, 300.0)))
    confirmed, confidence = ball_departure_confirmed(detections, contact_frame, FPS)
    assert confirmed is False
    assert confidence == 0.0


def test_sparse_ball_data_does_not_false_confirm():
    contact_frame = 10
    # Only one real ball detection in the whole window -- nowhere near
    # enough to judge a trend from.
    detections = [_det(contact_frame, ball_center=RACKET_AT_CONTACT)]
    confirmed, confidence = ball_departure_confirmed(detections, contact_frame, FPS)
    assert confirmed is False
    assert confidence == 0.0


def test_short_occlusion_gap_at_contact_does_not_block_a_real_departure():
    contact_frame = 10
    # Ball missing for 2 frames right at contact (expected occlusion), then
    # clearly receding once it reappears.
    detections = [
        _det(contact_frame, ball_center=RACKET_AT_CONTACT),
        _det(contact_frame + 1, ball_center=None),
        _det(contact_frame + 2, ball_center=None),
    ]
    for i in range(3, 8):
        detections.append(_det(contact_frame + i, ball_center=(500.0 + i * 20, 300.0)))
    confirmed, confidence = ball_departure_confirmed(detections, contact_frame, FPS)
    assert confirmed is True
    assert confidence > 0.0


def test_stationary_ball_with_drifting_crop_does_not_falsely_confirm():
    # Same bug class _racket_velocity_profile already had to fix: the
    # cropped tracking path re-crops tight to the player's OWN pose bbox
    # every frame, so raw crop-pixel positions drift frame to frame even
    # when nothing in the real (original-frame) scene moved. A ball that's
    # genuinely stationary in original-frame space, with a drifting crop
    # origin/scale, must NOT read as "receding" just because its raw
    # crop-pixel coordinates happen to shift.
    contact_frame = 10
    orig_ball = (600.0, 300.0)
    orig_racket = RACKET_AT_CONTACT
    detections = []
    for i in range(8):
        crop_x0, crop_y0, crop_scale = 400 + i * 10, 200 + i * 5, 1.0 + i * 0.05
        bx = (orig_ball[0] - crop_x0) * crop_scale
        by = (orig_ball[1] - crop_y0) * crop_scale
        rx = (orig_racket[0] - crop_x0) * crop_scale
        ry = (orig_racket[1] - crop_y0) * crop_scale
        detections.append({
            'frame': contact_frame + i,
            'racket_box': [rx - 5, ry - 5, rx + 5, ry + 5],
            'racket_conf': 0.9,
            'ball_box': [bx - 3, by - 3, bx + 3, by + 3],
            'ball_conf': 0.5,
            'crop_x0': crop_x0, 'crop_y0': crop_y0, 'crop_scale': crop_scale,
        })
    confirmed, confidence = ball_departure_confirmed(detections, contact_frame, FPS)
    assert confirmed is False
    assert confidence == 0.0


def test_receding_ball_still_confirms_through_a_drifting_crop():
    # Mirror of the above, but the ball genuinely IS receding in
    # original-frame space -- the real trend must survive the crop
    # conversion, not get masked or distorted by it.
    contact_frame = 10
    orig_racket = RACKET_AT_CONTACT
    detections = []
    for i in range(8):
        crop_x0, crop_y0, crop_scale = 400 + i * 10, 200 + i * 5, 1.0 + i * 0.05
        orig_ball = (orig_racket[0] + i * 20.0, orig_racket[1])
        bx = (orig_ball[0] - crop_x0) * crop_scale
        by = (orig_ball[1] - crop_y0) * crop_scale
        rx = (orig_racket[0] - crop_x0) * crop_scale
        ry = (orig_racket[1] - crop_y0) * crop_scale
        detections.append({
            'frame': contact_frame + i,
            'racket_box': [rx - 5, ry - 5, rx + 5, ry + 5],
            'racket_conf': 0.9,
            'ball_box': [bx - 3, by - 3, bx + 3, by + 3],
            'ball_conf': 0.5,
            'crop_x0': crop_x0, 'crop_y0': crop_y0, 'crop_scale': crop_scale,
        })
    confirmed, confidence = ball_departure_confirmed(detections, contact_frame, FPS)
    assert confirmed is True
    assert confidence > 0.0
