"""Geometric shot classifier: the FH/BH side test must be view-invariant, the
serve gate handedness-independent, two-handed grip -> backhand."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify_shot_geom import classify_geom, _side_projection  # noqa: E402

V = 1.0


def _lm(name, x, y):
    return {'name': name, 'x': x, 'y': y, 'z': 0.0, 'visibility': V}


def pose(rw, lw, *, rs=(0.55, 0.30), ls=(0.45, 0.30), rh=(0.55, 0.60),
         lh=(0.45, 0.60), re=(0.58, 0.32), nose=(0.50, 0.20)):
    """torso_scale ~= 0.30 (shoulder-mid y 0.30 -> hip-mid y 0.60)."""
    return [
        _lm('right_wrist', *rw), _lm('left_wrist', *lw),
        _lm('right_shoulder', *rs), _lm('left_shoulder', *ls),
        _lm('right_hip', *rh), _lm('left_hip', *lh),
        _lm('right_elbow', *re), _lm('nose', *nose),
    ]


def _mirror(p):
    return [{**d, 'x': 1.0 - d['x']} for d in p]


def test_right_handed_forehand():
    # dominant (right) wrist extended out to the right, shoulder height
    p = pose(rw=(0.78, 0.34), lw=(0.46, 0.40))
    assert classify_geom(p, None, [p], 'right')['shot_type'] == 'forehand'


def test_forehand_is_view_invariant():
    p = pose(rw=(0.78, 0.34), lw=(0.46, 0.40))
    assert classify_geom(_mirror(p), None, [_mirror(p)], 'right')['shot_type'] == 'forehand'
    # side projection sign is preserved under the mirror
    assert (_side_projection(p, 'right') > 0) == (_side_projection(_mirror(p), 'right') > 0)


def test_one_handed_backhand():
    # right wrist crossed over to the left side of the torso
    p = pose(rw=(0.28, 0.34), lw=(0.40, 0.45))
    assert classify_geom(p, None, [p], 'right')['shot_type'] == 'backhand'


def test_two_handed_backhand_overrides_ambiguous_side():
    # wrists together near the midline -> two-handed grip -> backhand
    p = pose(rw=(0.46, 0.40), lw=(0.49, 0.40))
    r = classify_geom(p, None, [p], 'right')
    assert r['shot_type'] == 'backhand'
    assert 'two-handed' in r['reason']


def test_serve_gate_fires_on_overhead():
    p = pose(rw=(0.52, 0.03), lw=(0.44, 0.30), re=(0.55, 0.10))
    assert classify_geom(p, None, [p], 'right')['shot_type'] == 'serve'


def test_serve_gate_handedness_independent():
    p = pose(rw=(0.52, 0.03), lw=(0.44, 0.30), re=(0.55, 0.10))
    assert classify_geom(p, None, [p], 'left')['shot_type'] == 'serve'


def test_serve_recognised_when_contact_frame_is_the_downswing():
    """The marked contact frame sits at max wrist velocity -- on a serve that's
    the downswing, wrist already back at shoulder height. The sustained
    overhead run through the toss/hit plus the wrist reaching well above the
    head still has to classify it as a serve."""
    # contact frame: wrist at shoulder height, no overhead reach here
    contact = pose(rw=(0.55, 0.30), lw=(0.45, 0.34))
    # window: many frames with the wrist high above the head (toss + hit up),
    # nose at y=0.20, torso ~0.30 -> wrist at y=0.00 is ~0.67 torso above head
    up = pose(rw=(0.53, 0.00), lw=(0.46, 0.10), re=(0.55, 0.06))
    window = [up] * 8 + [contact] * 2
    assert classify_geom(contact, None, window, 'right')['shot_type'] == 'serve'


def test_strong_serve_evidence_hard_wins_over_lateral_wrist_at_contact():
    """Regression for serve_0180: a real serve's marked (downswing) contact
    frame can still have the wrist swung out laterally enough that
    fh_logit = side*3.0 exceeds serve_logit's 4.0 floor -- the old softmax let
    that outvote a correctly-detected serve. Strong sustained-overhead
    evidence must hard-win before the FH/BH side test even runs."""
    # contact frame: wrist held far to the dominant side (side ~= 1.5, so
    # fh_logit = 4.5 -- would have beaten the old serve_logit=4.0 in the
    # softmax), no overhead reach at this specific frame.
    contact = pose(rw=(0.95, 0.30), lw=(0.45, 0.34))
    # window: same strong sustained-overhead evidence as the downswing test above.
    up = pose(rw=(0.53, 0.00), lw=(0.46, 0.10), re=(0.55, 0.06))
    window = [up] * 8 + [contact] * 2
    r = classify_geom(contact, None, window, 'right')
    assert r['shot_type'] == 'serve'
    assert r['confidence'] >= 0.7


def test_groundstroke_followthrough_does_not_read_as_serve():
    """A forehand whose follow-through briefly lifts the wrist to chin height
    must NOT trip the sustained serve gate -- the wrist never gets well above
    the head."""
    contact = pose(rw=(0.78, 0.34), lw=(0.46, 0.40))
    # follow-through: wrist up around nose/chin height only (y ~0.18, nose 0.20)
    follow = pose(rw=(0.40, 0.18), lw=(0.44, 0.22))
    window = [contact] * 3 + [follow] * 5
    assert classify_geom(contact, None, window, 'right')['shot_type'] == 'forehand'


def test_left_handed_forehand_uses_left_wrist():
    # lefty forehand: left wrist extended out to the left
    p = pose(rw=(0.54, 0.40), lw=(0.22, 0.34))
    assert classify_geom(p, None, [p], 'left')['shot_type'] == 'forehand'


def test_insufficient_landmarks_returns_none():
    p = [_lm('nose', 0.5, 0.2)]
    assert classify_geom(p, None, [p], 'right')['shot_type'] is None


def test_near_midline_1hbh_uses_followthrough_and_stays_usable():
    """A one-handed backhand contacts near the body midline -> weak side test.
    When the follow-through sweeps out to the dominant side (backhand), geom
    should call backhand AND keep confidence above the trajectory-off floor
    (GEOM_CONF_MIN_NOTRAJ = 0.15) so the phone path can use it."""
    contact = pose(rw=(0.47, 0.34), lw=(0.28, 0.42))          # hitting wrist just left of centre, off-hand well away (one-handed)
    follow = pose(rw=(0.62, 0.32), lw=(0.30, 0.42))            # sweeps out to the right (dominant) side
    r = classify_geom(contact, None, [contact, contact, follow], 'right')
    assert r['shot_type'] == 'backhand'
    assert r['confidence'] >= 0.15
    assert 'follow-through-backed' in r['reason']


def test_near_midline_coinflip_damped_below_floor():
    """Near midline with no usable follow-through -> genuine coin flip -> geom
    confidence must fall below the trajectory-off floor so it reaches Claude."""
    contact = pose(rw=(0.48, 0.34), lw=(0.28, 0.42))
    r = classify_geom(contact, None, [contact], 'right')
    assert r['confidence'] < 0.15
