"""Coverage for refine_contact_times(): the audio-onset detector overrides
the wrist-velocity peak as the contact frame when it's confident, and every
path degrades cleanly to the wrist peak (no audio / no model / not
confident / an exception) so an audio-less match video behaves exactly as
before this existed."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detect_rallies  # noqa: E402


def _swings():
    return [
        {'peak_frame': 300, 'peak_time': 10.0, 'contact_frame_guess': 295},
        {'peak_frame': 600, 'peak_time': 20.0},  # no verify_swings guess
    ]


def test_confident_audio_pick_is_adopted(monkeypatch):
    def fake_detect_contact(video_path, anchor_time_sec=None, search_window_sec=None, video_hints=None):
        # land 12 frames before the wrist peak (~impact) at 30fps
        return {'contact_time_sec': anchor_time_sec - 0.4, 'confident': True,
                'confidence': 0.9, 'margin': 0.5, 'n_onsets': 4, 'method': 'audio_onset'}

    monkeypatch.setattr('audio_contact.detect_contact', fake_detect_contact)
    swings = _swings()
    detect_rallies.refine_contact_times('match.mp4', swings, fps=30.0)

    assert swings[0]['contact_time_sec'] == pytest.approx(9.6)
    assert swings[0]['contact_frame'] == 288
    assert swings[0]['contact_method_audio'] == 'audio_onset'
    assert swings[1]['contact_time_sec'] == pytest.approx(19.6)


def test_not_confident_falls_back_to_wrist_peak(monkeypatch):
    monkeypatch.setattr(
        'audio_contact.detect_contact',
        lambda *a, **k: {'contact_time_sec': 5.0, 'confident': False,
                         'confidence': 0.3, 'margin': 0.05, 'n_onsets': 2, 'method': 'audio_onset'},
    )
    swings = _swings()
    detect_rallies.refine_contact_times('match.mp4', swings, fps=30.0)

    assert swings[0]['contact_time_sec'] == 10.0  # unchanged
    assert 'contact_frame' not in swings[0]


def test_none_result_falls_back(monkeypatch):
    monkeypatch.setattr('audio_contact.detect_contact', lambda *a, **k: None)
    swings = _swings()
    detect_rallies.refine_contact_times('match.mp4', swings, fps=30.0)
    assert swings[0]['contact_time_sec'] == 10.0
    assert swings[1]['contact_time_sec'] == 20.0


def test_exception_is_swallowed(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('ffmpeg missing')

    monkeypatch.setattr('audio_contact.detect_contact', boom)
    swings = _swings()
    detect_rallies.refine_contact_times('match.mp4', swings, fps=30.0)  # must not raise
    assert swings[0]['contact_time_sec'] == 10.0


def test_build_shot_list_is_clip_relative_and_chronological():
    # start_sec mirrors the PRE_PAD_SEC subtraction detect_rallies() applies
    # before calling this -- contact_time_sec must come out relative to the
    # rally's own clip, not the source match video's absolute timeline.
    group = [
        {'peak_time': 12.0, 'contact_time_sec': 12.3, 'shot_type': 'forehand'},
        {'peak_time': 15.0, 'contact_time_sec': 15.6, 'shot_type': 'backhand'},
    ]
    shots = detect_rallies.build_shot_list(group, start_sec=10.0)
    assert shots == [
        {'shot_index': 0, 'shot_type': 'forehand', 'contact_time_sec': 2.3},
        {'shot_index': 1, 'shot_type': 'backhand', 'contact_time_sec': 5.6},
    ]


def test_build_shot_list_falls_back_to_peak_time_without_a_refined_contact_time():
    group = [{'peak_time': 11.0, 'shot_type': 'forehand'}]
    shots = detect_rallies.build_shot_list(group, start_sec=10.0)
    assert shots == [{'shot_index': 0, 'shot_type': 'forehand', 'contact_time_sec': 1.0}]


def test_serve_gate_uses_refined_contact_time_for_the_point_boundary():
    # In strict mode the "a serve opened this point" flag resets only after a
    # POINT_BOUNDARY_GAP_SEC gap. Here the wrist peaks sit ~6s apart (below the
    # boundary) but the refined contact times are >POINT_BOUNDARY_GAP_SEC apart,
    # so the third shot must be gated out -- proving the gate reads
    # contact_time_sec, not peak_time.
    boundary = detect_rallies.POINT_BOUNDARY_GAP_SEC
    swings = [
        {'peak_time': 1.0, 'contact_time_sec': 1.0, 'shot_type': 'serve'},
        {'peak_time': 2.0, 'contact_time_sec': 2.0, 'shot_type': 'forehand'},
        {'peak_time': 8.0, 'contact_time_sec': 2.0 + boundary + 1.0, 'shot_type': 'forehand'},
    ]
    kept = detect_rallies.apply_serve_gate(swings, rally_gap_sec=6.0, mode='strict')
    assert [s['contact_time_sec'] for s in kept] == [2.0]
