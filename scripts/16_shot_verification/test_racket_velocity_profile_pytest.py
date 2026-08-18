"""Regression test: _racket_velocity_profile() used to fit a trajectory
across multiple frames' raw crop-pixel coordinates, but each frame from the
cropped tracking path is cropped tight to THAT frame's own pose bbox, so
raw crop-pixel positions aren't comparable across frames -- a player's bbox
moving between frames shifts the crop's origin/scale independently of any
real racket motion. Detections now carry crop_scale/crop_x0/crop_y0 and are
converted back to a shared original-frame coordinate space before fitting.

This test constructs a racket that is STATIONARY in original-frame space
but whose crop origin/scale changes every frame (as if the player's bbox
were drifting/zooming) -- with the bug, the fitted speed would be large
(spurious motion from the crop drifting, not the racket); with the fix, the
fitted speed should be ~0 (the racket never actually moved)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_shot_contact import _racket_velocity_profile, _racket_speed_at  # noqa: E402

STATIONARY_ORIGINAL_X, STATIONARY_ORIGINAL_Y = 500.0, 300.0


def _detection_for_stationary_racket(frame_idx, crop_x0, crop_y0, crop_scale):
    """A racket_box centered on a point that maps to the SAME original-frame
    position (STATIONARY_ORIGINAL_X, STATIONARY_ORIGINAL_Y) regardless of
    this frame's crop origin/scale -- i.e. a racket that truly never moved."""
    crop_x = (STATIONARY_ORIGINAL_X - crop_x0) * crop_scale
    crop_y = (STATIONARY_ORIGINAL_Y - crop_y0) * crop_scale
    return {
        'frame': frame_idx,
        'racket_box': [crop_x - 5, crop_y - 5, crop_x + 5, crop_y + 5],
        'racket_conf': 0.9,
        'ball_box': None, 'ball_conf': None,
        'crop_x0': crop_x0, 'crop_y0': crop_y0, 'crop_scale': crop_scale,
    }


def test_stationary_racket_with_drifting_crop_reads_near_zero_speed():
    detections = [
        _detection_for_stationary_racket(i, crop_x0=400 + i * 10, crop_y0=200 + i * 5, crop_scale=1.0 + i * 0.05)
        for i in range(-8, 9)
    ]
    speed_at_contact, peak_speed = _racket_speed_at(detections, contact_frame=0)
    assert speed_at_contact is not None
    # A truly stationary racket should fit to ~0 speed; a generous bound
    # (not exactly 0.0) since polyfit isn't a perfect interpolator, but this
    # must be far below what the drifting-crop bug would have produced
    # (crop_x0 alone drifts 160px over the window, crop_scale drifts 0.8 --
    # the buggy raw-crop-pixel fit would read many pixels/frame of "motion").
    assert speed_at_contact < 1.0, f'expected near-zero speed for a stationary racket, got {speed_at_contact}'
    assert peak_speed < 1.0


def test_moving_racket_in_original_space_is_still_detected_through_a_drifting_crop():
    # Racket genuinely moves 100px/frame in original-frame space; crop also
    # drifts independently. The fitted speed should reflect the real ~100
    # px/frame motion, not be swamped or masked by the crop's own drift.
    detections = []
    for i in range(-8, 9):
        crop_x0, crop_y0, crop_scale = 400 + i * 3, 200 + i * 2, 1.0
        orig_x = STATIONARY_ORIGINAL_X + i * 100.0
        orig_y = STATIONARY_ORIGINAL_Y
        crop_x = (orig_x - crop_x0) * crop_scale
        crop_y = (orig_y - crop_y0) * crop_scale
        detections.append({
            'frame': i, 'racket_box': [crop_x - 5, crop_y - 5, crop_x + 5, crop_y + 5],
            'racket_conf': 0.9, 'ball_box': None, 'ball_conf': None,
            'crop_x0': crop_x0, 'crop_y0': crop_y0, 'crop_scale': crop_scale,
        })
    speed_at_contact, _ = _racket_speed_at(detections, contact_frame=0)
    assert speed_at_contact is not None
    assert 90 < speed_at_contact < 110, f'expected ~100 px/frame, got {speed_at_contact}'


def test_detections_without_crop_metadata_default_to_original_space():
    # The non-cropped track_racket_and_ball() path produces detections with
    # no crop_scale/crop_x0/crop_y0 keys at all -- already in original-frame
    # space, so the conversion must default to scale=1, offset=0 (identity).
    detections = [
        {'frame': i, 'racket_box': [500 + i * 2 - 5, 300 - 5, 500 + i * 2 + 5, 300 + 5],
         'racket_conf': 0.9, 'ball_box': None, 'ball_conf': None}
        for i in range(-8, 9)
    ]
    speed_at_contact, _ = _racket_speed_at(detections, contact_frame=0)
    assert speed_at_contact is not None
    assert 1.5 < speed_at_contact < 2.5, f'expected ~2 px/frame, got {speed_at_contact}'
