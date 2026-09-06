"""Coverage for apply_serve_gate().

Since 2026-09 the gate is ADVISORY by default: it removes serves from the
rally-content list and tags every other shot with `after_serve` (was a
serve seen since the last > POINT_BOUNDARY_GAP_SEC gap), but does NOT drop
non-serve shots -- the swing detector misses too many real rally shots for
"no serve seen yet" to reliably mean "not in a point". `mode='strict'`
restores the old drop-until-a-serve behaviour for genuine match footage.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_rallies import apply_serve_gate, POINT_BOUNDARY_GAP_SEC  # noqa: E402

RALLY_GAP_SEC = 6.0


def _shot(peak_time, shot_type):
    return {'peak_time': peak_time, 'shot_type': shot_type}


# ── advisory mode (default) ───────────────────────────────────────────────────

def test_advisory_keeps_shots_before_any_serve_tagged_not_after_serve():
    kept = apply_serve_gate([_shot(1.0, 'forehand'), _shot(2.0, 'backhand')], RALLY_GAP_SEC)
    assert [s['shot_type'] for s in kept] == ['forehand', 'backhand']
    assert all(s['after_serve'] is False for s in kept)


def test_advisory_tags_after_serve_true_once_a_serve_is_seen():
    kept = apply_serve_gate(
        [_shot(0.0, 'serve'), _shot(1.5, 'forehand'), _shot(3.0, 'backhand')], RALLY_GAP_SEC)
    assert [s['shot_type'] for s in kept] == ['forehand', 'backhand']
    assert all(s['after_serve'] is True for s in kept)


def test_serve_itself_is_always_excluded_from_output():
    for mode in ('advisory', 'strict', 'off'):
        kept = apply_serve_gate([_shot(0.0, 'serve'), _shot(1.5, 'forehand')], RALLY_GAP_SEC, mode=mode)
        assert [s['shot_type'] for s in kept] == ['forehand']


def test_rally_gap_sized_gap_does_NOT_reset_after_serve():
    # a RALLY_GAP_SEC+ gap is usually just a detection gap mid-rally -- the
    # serve context must survive it (this is the bug the redesign fixes).
    gap = RALLY_GAP_SEC + 1.0
    kept = apply_serve_gate(
        [_shot(0.0, 'serve'), _shot(1.0, 'forehand'), _shot(1.0 + gap, 'backhand')], RALLY_GAP_SEC)
    assert [s['after_serve'] for s in kept] == [True, True]


def test_point_boundary_gap_resets_after_serve():
    gap = POINT_BOUNDARY_GAP_SEC + 1.0
    kept = apply_serve_gate(
        [_shot(0.0, 'serve'), _shot(1.0, 'forehand'), _shot(1.0 + gap, 'backhand')], RALLY_GAP_SEC)
    assert [s['after_serve'] for s in kept] == [True, False]


def test_a_new_serve_reopens_after_the_boundary():
    gap = POINT_BOUNDARY_GAP_SEC + 1.0
    kept = apply_serve_gate([
        _shot(0.0, 'serve'), _shot(1.0, 'forehand'),
        _shot(1.0 + gap, 'serve'), _shot(2.0 + gap, 'forehand'),
    ], RALLY_GAP_SEC)
    assert [s['after_serve'] for s in kept] == [True, True]


def test_gate_uses_refined_contact_time_for_the_boundary():
    # peak_times 5s apart (no reset), contact_time_sec 13s apart (reset).
    kept = apply_serve_gate([
        {'peak_time': 0.0, 'contact_time_sec': 0.0, 'shot_type': 'serve'},
        {'peak_time': 1.0, 'contact_time_sec': 1.0, 'shot_type': 'forehand'},
        {'peak_time': 6.0, 'contact_time_sec': 14.0, 'shot_type': 'backhand'},
    ], RALLY_GAP_SEC)
    assert [s['after_serve'] for s in kept] == [True, False]


# ── strict mode ──────────────────────────────────────────────────────────────

def test_strict_drops_shots_before_any_serve():
    kept = apply_serve_gate(
        [_shot(1.0, 'forehand'), _shot(2.0, 'backhand')], RALLY_GAP_SEC, mode='strict')
    assert kept == []


def test_strict_keeps_shots_after_a_serve():
    kept = apply_serve_gate(
        [_shot(0.0, 'serve'), _shot(1.5, 'forehand'), _shot(3.0, 'backhand')],
        RALLY_GAP_SEC, mode='strict')
    assert [s['shot_type'] for s in kept] == ['forehand', 'backhand']


def test_strict_second_serve_before_any_shot_does_not_leak_a_false_confirm():
    kept = apply_serve_gate(
        [_shot(0.0, 'serve'), _shot(1.0, 'serve'), _shot(2.5, 'forehand')],
        RALLY_GAP_SEC, mode='strict')
    assert [s['shot_type'] for s in kept] == ['forehand']


def test_strict_point_boundary_gap_recloses_the_gate():
    stray = _shot(1.5 + POINT_BOUNDARY_GAP_SEC + 1.0, 'backhand')
    kept = apply_serve_gate(
        [_shot(0.0, 'serve'), _shot(1.5, 'forehand'), stray], RALLY_GAP_SEC, mode='strict')
    assert [s['shot_type'] for s in kept] == ['forehand']


# ── off mode ─────────────────────────────────────────────────────────────────

def test_off_keeps_everything_non_serve_and_does_not_annotate():
    kept = apply_serve_gate(
        [_shot(1.0, 'forehand'), _shot(0.0, 'serve'), _shot(2.0, 'backhand')],
        RALLY_GAP_SEC, mode='off')
    assert [s['shot_type'] for s in kept] == ['forehand', 'backhand']
    assert all('after_serve' not in s for s in kept)


def test_empty_input():
    for mode in ('advisory', 'strict', 'off'):
        assert apply_serve_gate([], RALLY_GAP_SEC, mode=mode) == []
