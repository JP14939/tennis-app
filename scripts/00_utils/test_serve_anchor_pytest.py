"""Tests for the serve overhead-apex contact anchor (serve_anchor.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve_anchor as sa  # noqa: E402
from serve_anchor import (  # noqa: E402
    find_serve_apex_frame, serve_contact_anchor_frame, pose_by_frame_from_frames_list,
)

FPS = 60.0
# torso: shoulders y=0.40, hips y=0.70 -> torso scale ~0.30; nose y=0.35
_BASE = {
    'right_shoulder': {'x': 0.55, 'y': 0.40, 'visibility': 0.99},
    'left_shoulder':  {'x': 0.45, 'y': 0.40, 'visibility': 0.99},
    'right_hip':      {'x': 0.54, 'y': 0.70, 'visibility': 0.99},
    'left_hip':       {'x': 0.46, 'y': 0.70, 'visibility': 0.99},
    'nose':           {'x': 0.50, 'y': 0.35, 'visibility': 0.99},
}


def _frame(rw_y=0.50, lw_y=0.50, rw_vis=0.9, lw_vis=0.9, **overrides):
    lm = {k: dict(v) for k, v in _BASE.items()}
    lm['right_wrist'] = {'x': 0.60, 'y': rw_y, 'visibility': rw_vis}
    lm['left_wrist'] = {'x': 0.40, 'y': lw_y, 'visibility': lw_vis}
    for k, v in overrides.items():
        lm[k] = v
    return lm


def _serve_rw_track():
    """Right wrist rises from below the shoulder (f0) to well above the head
    (f20), then comes back down. Left wrist stays low."""
    pbf = {}
    for f in range(0, 41):
        # triangular: min y (highest point) at frame 20
        rw_y = 0.50 - 0.011 * f if f <= 20 else 0.50 - 0.011 * (40 - f)
        pbf[f] = _frame(rw_y=rw_y, lw_y=0.55)
    return pbf


def test_apex_at_peak_overhead_frame():
    assert find_serve_apex_frame(_serve_rw_track(), FPS) == 20


def test_contact_anchor_is_apex_plus_forward_lead():
    lead = round(sa.APEX_TO_CONTACT_LEAD_SEC * FPS)
    assert serve_contact_anchor_frame(_serve_rw_track(), FPS) == 20 + lead


def test_plateau_returns_centre_frame():
    """A flat apex plateau: the pick should land in the plateau's centre, not
    on its early leading edge (that early edge is the bimodal-error mode this
    targets -- on distant poses the wrist y barely moves across the top of the
    arc while contact happens mid-plateau)."""
    pbf = _serve_rw_track()
    for f in (18, 19, 20, 21, 22):
        pbf[f] = _frame(rw_y=0.02, lw_y=0.55)  # identical max reach
    assert find_serve_apex_frame(pbf, FPS) == 20


def test_near_plateau_within_tolerance_recentred():
    """Frames close to (within APEX_PLATEAU_TOL of) the max also count as
    plateau -- not just exact ties."""
    pbf = _serve_rw_track()
    # nose y 0.35, torso ~0.30 -> reach = (0.35 - rw_y)/0.30. rw_y 0.02 -> ~1.1;
    # a 0.005 y bump is ~0.017 reach, well inside APEX_PLATEAU_TOL (0.04).
    for f, y in ((19, 0.025), (20, 0.020), (21, 0.023), (22, 0.021)):
        pbf[f] = _frame(rw_y=y, lw_y=0.55)
    apex = find_serve_apex_frame(pbf, FPS)
    assert 20 <= apex <= 21  # centre of the [19..22] plateau, not frame 19


def test_sharp_apex_unaffected_by_plateau_logic():
    """A well-resolved single-frame apex is returned unchanged."""
    assert find_serve_apex_frame(_serve_rw_track(), FPS) == 20


def test_uses_whichever_wrist_is_highest():
    """Toss (left) wrist highest early; racket (right) wrist highest at
    extension. Apex must track the true extension, not the toss."""
    pbf = {}
    for f in range(0, 31):
        lw_y = 0.20 if f == 6 else 0.55            # brief toss peak
        rw_y = 0.03 if f == 22 else 0.50           # racket extension
        pbf[f] = _frame(rw_y=rw_y, lw_y=lw_y)
    assert find_serve_apex_frame(pbf, FPS) == 22


def test_center_frame_restricts_search_to_a_radius():
    pbf = _serve_rw_track()
    pbf[300] = _frame(rw_y=-0.20, lw_y=0.55)  # higher, but far from the swing
    # center_frame + radius keeps the far frame out of the search
    assert find_serve_apex_frame(pbf, FPS, center_frame=20, radius_sec=0.6) == 20
    # with no center, the unbounded global argmax picks the highest frame
    assert find_serve_apex_frame(pbf, FPS) == 300


def test_falls_back_to_overhead_reach_when_nose_not_visible():
    pbf = _serve_rw_track()
    for f in pbf:
        pbf[f]['nose']['visibility'] = 0.0
    assert find_serve_apex_frame(pbf, FPS) == 20


def test_none_when_torso_not_measurable():
    pbf = {}
    for f in range(10):
        lm = _frame(rw_y=0.1)
        lm['right_shoulder']['visibility'] = 0.0
        lm['left_shoulder']['visibility'] = 0.0
        pbf[f] = lm
    assert find_serve_apex_frame(pbf, FPS) is None
    assert serve_contact_anchor_frame(pbf, FPS) is None


def test_low_visibility_wrist_jump_is_not_a_false_apex():
    pbf = _serve_rw_track()
    pbf[8] = _frame(rw_y=-0.30, rw_vis=0.05, lw_y=0.55)  # blurry garbage detection
    assert find_serve_apex_frame(pbf, FPS) == 20


def test_returns_a_frame_number_present_in_input():
    pbf = _serve_rw_track()
    apex = find_serve_apex_frame(pbf, FPS)
    assert apex in pbf


def test_pose_by_frame_adapter_skips_none_landmarks():
    frames = [
        {'frame': 0, 'landmarks': _frame(rw_y=0.5)},
        {'frame': 3, 'landmarks': None},
        {'frame': 6, 'landmarks': _frame(rw_y=0.1)},
    ]
    pbf = pose_by_frame_from_frames_list(frames)
    assert set(pbf) == {0, 6}


def test_empty_input_returns_none():
    assert find_serve_apex_frame({}, FPS) is None
    assert serve_contact_anchor_frame({}, FPS) is None
