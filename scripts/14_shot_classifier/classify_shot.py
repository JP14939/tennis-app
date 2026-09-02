"""
Automatic shot-type classifier: forehand / backhand / serve.

Reuses extract_clips.py's existing rule-based confidence scorers
(score_forehand/score_backhand/score_serve) -- today they only validate an
ALREADY-ASSIGNED shot type's confidence; a classifier is just running all
three against an unknown swing and taking the highest score. No ML model,
consistent with this codebase's existing rule-based-first pattern
(tip_selector.py, phase_breakdown.py).

Usage:
  python classify_shot.py <video_path> <contact_time_sec>
"""
import argparse
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '08_comparison_engine'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '04_clip_extraction'))
from paths import DATA_DIR  # noqa: E402
from compare_swing import extract_user_poses  # noqa: E402
from extract_clips import SCORERS, nearest_pose  # noqa: E402
from extract_training_features import extract_features, FEATURE_NAMES, FEATURE_VERSION  # noqa: E402

# Same window shape extract_clips.py's process_job() already uses for serve:
# -1s to +0.5s around contact, sampled every 3 frames.
SERVE_WINDOW_PRE_SEC = 1.0
SERVE_WINDOW_POST_SEC = 0.5
SERVE_WINDOW_STEP_FRAMES = 3

ML_MODEL_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_model.pkl')
ML_META_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_model_meta.json')
_ml_model = None
_ml_model_missing_logged = False
_ml_version_warned = False


def _build_swing_frames(video_path, contact_time_sec, frames_fps):
    """
    Shared by classify() and classify_ml() -- both need the same
    peak/prev/window landmark lists around a contact time, just feed them
    to different scoring logic afterward (hand-tuned rule scorers vs. the
    trained model). Returns (peak_lm, prev_lm, window_lms, fps).
    """
    frames, fps = frames_fps if frames_fps is not None else extract_user_poses(video_path)
    pose_index = {f['frame']: list(f['landmarks'].values()) for f in frames if f['landmarks']}
    if not pose_index:
        raise RuntimeError('No pose detected anywhere in this video')

    contact_frame = round(contact_time_sec * fps)
    peak_lm = nearest_pose(pose_index, contact_frame)
    prev_lm = nearest_pose(pose_index, contact_frame - 3)
    if peak_lm is None:
        raise RuntimeError('No pose detected near the given contact time')

    window_lms = []
    lo = -int(SERVE_WINDOW_PRE_SEC * fps)
    hi = int(SERVE_WINDOW_POST_SEC * fps)
    for offset in range(lo, hi, SERVE_WINDOW_STEP_FRAMES):
        lm = nearest_pose(pose_index, contact_frame + offset)
        if lm:
            window_lms.append(lm)

    return peak_lm, prev_lm, window_lms, fps


def classify(video_path, contact_time_sec, frames_fps=None):
    """
    frames_fps: optional pre-extracted (frames, fps) tuple (same shape
    extract_user_poses returns) to avoid re-running pose extraction when the
    caller already has it for this exact video -- e.g. classify_shot_verified.py
    reuses the same extraction compare_swing.compare() would otherwise redo.
    Defaults to None so every existing caller behaves exactly as before.
    """
    peak_lm, prev_lm, window_lms, _fps = _build_swing_frames(video_path, contact_time_sec, frames_fps)

    scores = {}
    for shot_type, scorer in SCORERS.items():
        if shot_type == 'serve':
            score, _ = scorer(peak_lm, prev_lm, window_lms)
        else:
            score, _ = scorer(peak_lm, prev_lm)
        scores[shot_type] = round(score, 3)

    best_shot = max(scores, key=scores.get)
    return {'shot_type': best_shot, 'scores': scores}


def _get_ml_model():
    global _ml_model, _ml_model_missing_logged, _ml_version_warned
    if _ml_model is None:
        if not os.path.exists(ML_MODEL_PATH):
            if not _ml_model_missing_logged:
                print(f'[classify_shot] no trained model at {ML_MODEL_PATH} -- '
                      'run train_shot_classifier_model.py first', file=sys.stderr)
                _ml_model_missing_logged = True
            return None
        # Refuse a model trained on a different feature version -- feeding it
        # differently-scaled inputs would corrupt predictions silently. Caller
        # falls back to the rule scorers.
        try:
            with open(ML_META_PATH) as f:
                mv = json.load(f).get('feature_version', 'v1')
        except FileNotFoundError:
            mv = 'v1'
        if mv != FEATURE_VERSION:
            if not _ml_version_warned:
                print(f'[classify_shot] model feature_version {mv!r} != code '
                      f'{FEATURE_VERSION!r} -- using rule scorers until retrained', file=sys.stderr)
                _ml_version_warned = True
            return None
        import joblib
        _ml_model = joblib.load(ML_MODEL_PATH)
    return _ml_model


def classify_ml(video_path, contact_time_sec, frames_fps=None):
    """
    Same inputs/output shape as classify(), but scored by the trained
    model (train_shot_classifier_model.py) instead of the hand-tuned rule
    scorers -- same underlying landmark reads (extract_training_features.
    extract_features()), just combined by learned weights instead of
    hand-picked ones. Raises RuntimeError if no trained model exists yet
    (mirrors classify()'s own "no pose detected" failure style, so callers
    already handling classify() exceptions don't need new handling).
    """
    model = _get_ml_model()
    if model is None:
        raise RuntimeError('No trained shot-classifier model available')

    peak_lm, prev_lm, window_lms, _fps = _build_swing_frames(video_path, contact_time_sec, frames_fps)
    features = extract_features(peak_lm, prev_lm, window_lms)

    import numpy as np
    x = np.full((1, len(FEATURE_NAMES)), np.nan, dtype=float)
    for j, name in enumerate(FEATURE_NAMES):
        v = features.get(name)
        if v is not None:
            x[0, j] = float(v)

    proba = model.predict_proba(x)[0]
    scores = {str(cls): round(float(p), 3) for cls, p in zip(model.classes_, proba)}
    best_shot = max(scores, key=scores.get)
    return {'shot_type': best_shot, 'scores': scores}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('contact_time_sec', type=float)
    args = parser.parse_args()

    try:
        result = classify(args.video, args.contact_time_sec)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
