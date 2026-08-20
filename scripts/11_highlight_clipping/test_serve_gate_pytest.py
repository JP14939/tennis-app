"""Coverage for apply_serve_gate(): no groundstroke should be confirmed as
a real rally shot until a serve has opened its point. Doesn't need to know
which player served or whether a serve was "first" or "second" -- a later
serve just re-opens the gate before anything real could slip through
between two serves in a fault-then-retake sequence."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_rallies import apply_serve_gate  # noqa: E402

RALLY_GAP_SEC = 6.0


def _shot(peak_time, shot_type):
    return {'peak_time': peak_time, 'shot_type': shot_type}


def test_shot_before_any_serve_is_dropped():
    swings = [_shot(1.0, 'forehand'), _shot(2.0, 'backhand')]
    assert apply_serve_gate(swings, RALLY_GAP_SEC) == []


def test_shots_after_a_serve_are_kept():
    serve = _shot(0.0, 'serve')
    fh = _shot(1.5, 'forehand')
    bh = _shot(3.0, 'backhand')
    kept = apply_serve_gate([serve, fh, bh], RALLY_GAP_SEC)
    assert kept == [fh, bh]


def test_serve_itself_is_excluded_from_output():
    serve = _shot(0.0, 'serve')
    fh = _shot(1.5, 'forehand')
    kept = apply_serve_gate([serve, fh], RALLY_GAP_SEC)
    assert serve not in kept


def test_second_serve_before_any_shot_does_not_leak_a_false_confirm():
    first_serve = _shot(0.0, 'serve')
    second_serve = _shot(1.0, 'serve')
    fh = _shot(2.5, 'forehand')
    kept = apply_serve_gate([first_serve, second_serve, fh], RALLY_GAP_SEC)
    assert kept == [fh]


def test_large_gap_closes_the_gate_for_the_next_point():
    serve = _shot(0.0, 'serve')
    fh = _shot(1.5, 'forehand')
    # Next point starts well past RALLY_GAP_SEC later with no new serve.
    stray = _shot(1.5 + RALLY_GAP_SEC + 1.0, 'backhand')
    kept = apply_serve_gate([serve, fh, stray], RALLY_GAP_SEC)
    assert kept == [fh]


def test_new_point_can_open_again_with_its_own_serve():
    serve1 = _shot(0.0, 'serve')
    fh1 = _shot(1.5, 'forehand')
    gap_start = 1.5 + RALLY_GAP_SEC + 1.0
    serve2 = _shot(gap_start, 'serve')
    fh2 = _shot(gap_start + 1.5, 'forehand')
    kept = apply_serve_gate([serve1, fh1, serve2, fh2], RALLY_GAP_SEC)
    assert kept == [fh1, fh2]


def test_empty_input():
    assert apply_serve_gate([], RALLY_GAP_SEC) == []
