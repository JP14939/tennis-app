"""Guard rails for audio_contact.detect_contact -- mostly that it degrades to
None cleanly (no audio stream / no model / junk input) so compare_swing's
auto-detect path is never broken by it."""
import os
import subprocess
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '00_utils'))

import audio_contact  # noqa: E402
from audio_onset import FFMPEG, extract_audio_wav  # noqa: E402


def _tone_wav(path, sr=22050, dur=2.0):
    """A pure sine -- has energy but no sharp broadband onset."""
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    x = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    from scipy.io import wavfile
    wavfile.write(path, sr, x)


def _silent_mp4(path, sr=22050, dur=1.0):
    subprocess.run([FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i',
                    f'color=c=black:s=64x64:d={dur}', '-an', path],
                   check=True, capture_output=True)


def test_no_audio_stream_returns_none(tmp_path):
    mp4 = str(tmp_path / 'silent.mp4')
    _silent_mp4(mp4)
    assert audio_contact.detect_contact(mp4) is None


def test_missing_model_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_contact, '_models', {})
    monkeypatch.setattr(audio_contact, '_missing_logged', set())
    wav = str(tmp_path / 'tone.wav')
    _tone_wav(wav)
    assert audio_contact.detect_contact(
        'unused.mp4', audio_path=wav, model_path=str(tmp_path / 'nope.pkl')) is None


def test_junk_path_returns_none():
    assert audio_contact.detect_contact('/no/such/file.mp4') is None


@pytest.mark.skipif(not os.path.exists(audio_contact.MODEL_PATH),
                    reason='onset_classifier.pkl not trained on this machine')
def test_real_model_shape(tmp_path):
    """With the model present and a tone-only wav, we still get a well-formed
    dict or None -- never an exception."""
    wav = str(tmp_path / 'tone.wav')
    _tone_wav(wav)
    r = audio_contact.detect_contact('unused.mp4', audio_path=wav)
    if r is not None:
        assert set(r) >= {'contact_time_sec', 'confidence', 'confident', 'method'}
        assert r['contact_time_sec'] >= 0.0
