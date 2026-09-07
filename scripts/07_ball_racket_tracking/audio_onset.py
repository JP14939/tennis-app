"""
Pure-DSP audio onset detection + per-onset feature extraction, shared by:
  - eval_audio_contact.py        (the pro-clip eval)
  - train_onset_classifier.py    (trains onset_classifier.pkl)
  - audio_contact.py             (live inference / DB prediction)

Zero heavy deps -- numpy + scipy + the bundled imageio_ffmpeg binary only.
The ball-on-strings impact is a sharp broadband transient; spectral flux
peak-picks it, and onset_features() describes each peak enough for a
classifier to tell the real strike from bounces / footwork / crowd / edits.
"""
import os
import subprocess

import numpy as np
from scipy import signal as sps
from scipy.io import wavfile

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

SR = 22050
HIGHPASS_HZ_DEFAULT = 1500.0
REPORT_FPS = 59.94              # pro clips are all ~59.94; frame conversions in the eval

# "Plausible contact" band inside a standard 3s pro clip (cut at peak-1s / +2s).
WINDOW_LO_SEC = 0.55
WINDOW_HI_SEC = 2.2

# The detected onset lands ~2.5 frames LATE vs. a human contact mark (STFT
# frame-centre latency + a mild tendency to mark the frame just before visible
# ball separation). Subtract this from any onset time before using it.
ONSET_BIAS_F = 2.5
ONSET_BIAS_SEC = ONSET_BIAS_F / REPORT_FPS   # ~0.042s -- the time-domain form

# Pure audio-shape features -- how the onset *sounds*, nothing about where the
# video thinks contact is and nothing about the clip's cut position. This is
# the feature set for the Phase-C label-generation teacher, which must stay
# independent of the visual student it trains.
AUDIO_ONLY_FEATURE_NAMES = [
    'strength', 'strength_rank', 'strength_ratio_to_max',
    'attack_slope', 'decay_ratio', 'pre_quiet_ratio', 'flux_width_f',
    'centroid_hz', 'rolloff85_hz', 'flatness', 'hf_ratio', 'lf_ratio',
    'broadband_frac', 'rms_db',
]

# Everything the fusion (live) onset classifier uses: audio shape + the
# clip-cut time prior + the video-agreement features.
ONSET_FEATURE_NAMES = AUDIO_ONLY_FEATURE_NAMES + [
    't_sec', 'dt_band_center', 'in_band',
    'dt_wrist_peak', 'abs_dt_wrist_peak',
    'dt_pose_pred', 'abs_dt_pose_pred',
    'dt_occlusion_gap', 'n_ball_in_window',
]


def has_audio_stream(path):
    """True if ffmpeg reports an audio stream in the file."""
    try:
        out = subprocess.run([FFMPEG, '-i', path], capture_output=True, text=True)
        return 'Audio:' in (out.stderr or '')
    except Exception:
        return False


def extract_audio_wav(src, out_wav, start_sec=None, dur_sec=None):
    """Extract mono `SR` wav from `src` (whole file, or [start_sec, +dur_sec]).
    Returns True on success, False if there's no audio stream / ffmpeg fails.
    Skips work if out_wav already exists (caller manages cache invalidation)."""
    if os.path.exists(out_wav):
        return True
    os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
    cmd = [FFMPEG, '-y', '-v', 'error']
    if start_sec is not None:
        cmd += ['-ss', f'{max(0.0, start_sec):.3f}']
    if dur_sec is not None:
        cmd += ['-t', f'{dur_sec:.3f}']
    cmd += ['-i', src, '-vn', '-ac', '1', '-ar', str(SR), '-f', 'wav', out_wav]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return os.path.exists(out_wav) and os.path.getsize(out_wav) > 44
    except subprocess.CalledProcessError:
        if os.path.exists(out_wav):
            os.remove(out_wav)
        return False


def _stft(wav_path, highpass_hz):
    sr, x = wavfile.read(wav_path)
    if x.ndim > 1:
        x = x.mean(axis=1)
    x = x.astype(np.float64)
    if np.max(np.abs(x)) > 0:
        x /= np.max(np.abs(x))
    if highpass_hz and highpass_hz > 0:
        sos = sps.butter(4, highpass_hz / (sr / 2), btype='high', output='sos')
        x = sps.sosfilt(sos, x)
    nper = int(0.010 * sr)          # ~10ms window
    hop = int(0.0025 * sr)          # ~2.5ms hop
    f, t, Z = sps.stft(x, fs=sr, nperseg=nper, noverlap=nper - hop, boundary=None)
    return f, t, np.abs(Z)


def onset_envelope(wav_path, highpass_hz=HIGHPASS_HZ_DEFAULT):
    f, t, mag = _stft(wav_path, highpass_hz)
    flux = np.sum(np.clip(np.diff(mag, axis=1), 0, None), axis=0)
    flux_t = t[1:]
    if len(flux) and flux.max() > 0:
        flux = flux / flux.max()
    return flux_t, flux


def find_onsets(flux_t, flux):
    if len(flux) == 0:
        return []
    min_dist = max(1, int(0.050 / (flux_t[1] - flux_t[0]))) if len(flux_t) > 1 else 1
    peaks, _ = sps.find_peaks(flux, height=0.12, distance=min_dist, prominence=0.08)
    return sorted(((float(flux_t[p]), float(flux[p])) for p in peaks), key=lambda o: -o[1])


def onset_features(wav_path, highpass_hz=HIGHPASS_HZ_DEFAULT, video_hints=None):
    """Per-onset feature dicts for every detected onset in the clip. video_hints
    (optional): {wrist_peak_sec, pose_pred_sec, occlusion_gap_sec, n_ball}.
    Returns [(onset_time_sec, strength, {feature: value}), ...] strongest-first."""
    vh = video_hints or {}
    f, t, mag = _stft(wav_path, highpass_hz)
    flux = np.sum(np.clip(np.diff(mag, axis=1), 0, None), axis=0)
    flux_t = t[1:]
    fmax = flux.max() if len(flux) else 0.0
    flux_n = flux / fmax if fmax > 0 else flux
    dt = float(flux_t[1] - flux_t[0]) if len(flux_t) > 1 else 0.0025

    onsets = find_onsets(flux_t, flux_n)
    hf_mask = f >= 3000.0
    lf_mask = f <= 800.0
    band_center = (WINDOW_LO_SEC + WINDOW_HI_SEC) / 2

    out = []
    for rank, (ot, ostr) in enumerate(onsets):
        j = int(np.argmin(np.abs(flux_t - ot)))
        k = min(j + 1, mag.shape[1] - 1)
        spec = mag[:, k]
        spec_sum = float(spec.sum()) or 1e-9
        centroid = float((f * spec).sum() / spec_sum)
        csum = np.cumsum(spec)
        rolloff = float(f[np.searchsorted(csum, 0.85 * csum[-1])]) if csum[-1] > 0 else 0.0
        gmean = float(np.exp(np.mean(np.log(spec + 1e-12))))
        amean = float(spec.mean() + 1e-12)
        flatness = gmean / amean
        hf_ratio = float(spec[hf_mask].sum() / spec_sum)
        lf_ratio = float(spec[lf_mask].sum() / spec_sum)
        broadband = float((spec > 0.25 * spec.max()).mean()) if spec.max() > 0 else 0.0
        rms_db = 20.0 * np.log10(np.sqrt(float((spec ** 2).mean())) + 1e-9)

        pre = flux_n[max(0, j - 4):j]
        post = flux_n[j + 1:j + 13]
        attack_slope = float(flux_n[j] - (pre.mean() if len(pre) else 0.0))
        decay_ratio = float((post.mean() if len(post) else 0.0) / (flux_n[j] + 1e-9))
        pre_quiet_ratio = float((pre.mean() if len(pre) else 0.0) / (flux_n[j] + 1e-9))
        lo = j
        while lo > 0 and flux_n[lo - 1] > 0.5 * flux_n[j]:
            lo -= 1
        hi = j
        while hi < len(flux_n) - 1 and flux_n[hi + 1] > 0.5 * flux_n[j]:
            hi += 1
        width_f = (hi - lo) * dt * REPORT_FPS

        def _dt(key):
            return float(ot - vh[key]) if vh.get(key) is not None else np.nan

        out.append((float(ot), float(ostr), {
            'strength': float(ostr),
            'strength_rank': float(rank),
            'strength_ratio_to_max': float(ostr / (onsets[0][1] + 1e-9)),
            'attack_slope': attack_slope,
            'decay_ratio': decay_ratio,
            'pre_quiet_ratio': pre_quiet_ratio,
            'flux_width_f': float(width_f),
            'centroid_hz': centroid,
            'rolloff85_hz': rolloff,
            'flatness': flatness,
            'hf_ratio': hf_ratio,
            'lf_ratio': lf_ratio,
            'broadband_frac': broadband,
            'rms_db': float(rms_db),
            't_sec': float(ot),
            'dt_band_center': float(ot - band_center),
            'in_band': 1.0 if WINDOW_LO_SEC <= ot <= WINDOW_HI_SEC else 0.0,
            'dt_wrist_peak': _dt('wrist_peak_sec'),
            'abs_dt_wrist_peak': abs(_dt('wrist_peak_sec')),
            'dt_pose_pred': _dt('pose_pred_sec'),
            'abs_dt_pose_pred': abs(_dt('pose_pred_sec')),
            'dt_occlusion_gap': _dt('occlusion_gap_sec'),
            'n_ball_in_window': float(vh['n_ball']) if vh.get('n_ball') is not None else np.nan,
        }))
    return out
