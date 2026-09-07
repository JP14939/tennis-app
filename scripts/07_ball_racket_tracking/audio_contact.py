"""
Audio-onset contact detection for inference -- picks the ball-strike moment
from a video's audio track using the trained onset_classifier.pkl.

Used by:
  - scripts/08_comparison_engine/compare_swing.py  (live upload, auto-detect path)
  - scripts/06_database_build/predict_pro_clip_contact_from_audio.py  (pro DB fill)

Everything degrades to None cleanly: no audio stream, ffmpeg missing, no
onsets, or no trained model -> caller keeps its existing contact estimate.

  from audio_contact import detect_contact
  r = detect_contact(video_path, anchor_time_sec=1.3, video_hints={...})
  # r == {'contact_time_sec', 'confidence', 'margin', 'onset_time_raw',
  #        'n_onsets', 'method'}  or  None
"""
import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '00_utils'))

from paths import DATA_DIR  # noqa: E402
from audio_onset import (  # noqa: E402
    HIGHPASS_HZ_DEFAULT, ONSET_BIAS_SEC, ONSET_FEATURE_NAMES,
    extract_audio_wav, has_audio_stream, onset_features,
)

_D = os.path.join(DATA_DIR, '07_ball_racket_tracking')
MODEL_PATH = os.path.join(_D, 'onset_classifier.pkl')                 # fusion (live default)
AUDIO_ONLY_MODEL_PATH = os.path.join(_D, 'onset_classifier_audioonly.pkl')  # Phase-C teacher

# proba / margin thresholds above which an audio pick is "confident" enough to
# use without a human check (tuned against train_onset_classifier.py's CV split).
CONFIDENT_PROBA = 0.60
CONFIDENT_MARGIN = 0.20

_models = {}          # path -> (pipeline, feature_names)
_missing_logged = set()


def _get_model(path):
    if path not in _models:
        if not os.path.exists(path):
            if path not in _missing_logged:
                print(f'[audio_contact] no model at {path} -- audio contact detection '
                      'disabled for this path (run train_onset_classifier.py)', file=sys.stderr)
                _missing_logged.add(path)
            _models[path] = (None, None)
        else:
            import joblib
            pipe = joblib.load(path)
            feats = ONSET_FEATURE_NAMES
            meta_p = path.replace('.pkl', '_meta.json')
            if os.path.exists(meta_p):
                try:
                    feats = json.load(open(meta_p))['feature_names']
                except Exception:
                    pass
            _models[path] = (pipe, feats)
    return _models[path]


def score_onsets(wav_path, video_hints=None, band=None, model_path=MODEL_PATH):
    """Returns [(onset_time_sec, proba, feat_dict), ...] sorted by proba desc,
    or [] if no model / no onsets. `band` = (lo_sec, hi_sec) restricts which
    onsets are considered (others still scored, just not returned)."""
    model, feat_names = _get_model(model_path)
    if model is None:
        return []
    feats = onset_features(wav_path, HIGHPASS_HZ_DEFAULT, video_hints)
    if not feats:
        return []
    X = np.array([[fd.get(n, np.nan) for n in feat_names] for _, _, fd in feats], float)
    proba = model.predict_proba(X)[:, 1]
    scored = [(t, float(p), fd) for (t, _, fd), p in zip(feats, proba)]
    if band is not None:
        lo, hi = band
        inb = [s for s in scored if lo <= s[0] <= hi]
        scored = inb or scored          # fall back to all if the band is empty
    return sorted(scored, key=lambda s: -s[1])


def detect_contact(video_path, anchor_time_sec=None, video_hints=None,
                   search_window_sec=None, audio_path=None,
                   model_path=MODEL_PATH, conf_proba=CONFIDENT_PROBA,
                   conf_margin=CONFIDENT_MARGIN):
    """Pick the contact moment from `video_path`'s audio. Returns a dict or None.

    anchor_time_sec + search_window_sec: only consider onsets within
      [anchor - w, anchor + w] (used when a rough contact estimate exists).
    video_hints: {wrist_peak_sec, pose_pred_sec, occlusion_gap_sec, n_ball}
      -- fed to the classifier as fusion features.
    audio_path: use this wav directly instead of extracting from the video.
    model_path: which classifier -- MODEL_PATH (fusion, live) or
      AUDIO_ONLY_MODEL_PATH (the Phase-C label-generation teacher).
    """
    tmp = None
    wav = audio_path
    try:
        if wav is None:
            if not has_audio_stream(video_path):
                return None
            fd, tmp = tempfile.mkstemp(suffix='.wav', prefix='contact_')
            os.close(fd)
            os.remove(tmp)   # extract_audio_wav skips work if the path exists
            if not extract_audio_wav(video_path, tmp):
                return None
            wav = tmp

        band = None
        if anchor_time_sec is not None and search_window_sec:
            band = (anchor_time_sec - search_window_sec, anchor_time_sec + search_window_sec)

        scored = score_onsets(wav, video_hints=video_hints, band=band, model_path=model_path)
        if not scored:
            return None

        top_t, top_p, _ = scored[0]
        margin = top_p - (scored[1][1] if len(scored) > 1 else 0.0)
        return {
            'contact_time_sec': max(0.0, top_t - ONSET_BIAS_SEC),
            'onset_time_raw': top_t,
            'confidence': top_p,
            'margin': margin,
            'confident': top_p >= conf_proba and margin >= conf_margin,
            'n_onsets': len(scored),
            'method': 'audio_onset',
        }
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
