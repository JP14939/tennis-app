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


TRAJ_MARGIN_MIN = 0.20   # trajectory-kNN vote decisiveness to trust its FH/BH call
GEOM_CONF_MIN = 0.35     # geom's own FH/BH confidence to fall back on (trajectory-on path)
# When trajectory is off (phone footage), geom is the ONLY FH/BH signal and the
# alternative to trusting it is dumping to Claude / 'uncertain'. A near-midline
# one-handed backhand gets geom confidence capped at 0.3 (< GEOM_CONF_MIN), so
# with the strict floor every 1HBH on phone footage was lost. Accept geom's best
# guess down to this floor when there's nothing else.
GEOM_CONF_MIN_NOTRAJ = 0.15
# On the phone path (trajectory off) the trained model is the primary FH/BH
# decider -- it learns backhand from the amateur set (CV recall ~0.60) where
# geom's near-midline side test only manages ~0.40. Gate on the winning class
# probability so its low backhand precision doesn't run away; geom stays the
# backstop. The model is amateur-trained so it is NOT used on the broadcast
# path (trajectory-kNN owns that domain).
ML_CONF_MIN = 0.55


def classify_ensemble(video_path, contact_time_sec, frames_fps=None, *,
                      handedness='right', use_trajectory=True, use_ml=None):
    """Serve is decided by classify_shot_geom's overhead gate (near-100% serve
    recall, view-invariant); forehand vs backhand by trajectory-kNN over the
    labelled pro swings (~85% in the broadcast/pipeline domain), with geom's
    dot-product side test as the fallback.

    `use_trajectory=False` for phone-upload footage -- the pro trajectory pool
    is broadcast, and matching a phone selfie swing against it mislabels every
    backhand as a forehand (measured). There the trained model (classify_ml)
    becomes the primary FH/BH decider, with geom's dot-product side test down
    to GEOM_CONF_MIN_NOTRAJ as the backstop. (The phone caller is
    detect_rallies.py --no-trajectory, wired from backend/src/routes/highlights.js.)

    `use_ml` defaults to `not use_trajectory` -- the model is the phone tool,
    trajectory-kNN is the broadcast tool, geom is shared (serve gate + fallback).

    Returns {shot_type, scores, source, confidence}. shot_type is 'uncertain'
    when nothing is confident (-> send to Claude) and None when there isn't
    enough pose to decide anything.
    """
    from classify_shot_geom import classify_geom  # noqa: PLC0415

    if use_ml is None:
        use_ml = not use_trajectory

    peak_lm, prev_lm, window_lms, fps = _build_swing_frames(video_path, contact_time_sec, frames_fps)
    g = classify_geom(peak_lm, prev_lm, window_lms, handedness)

    ml = None
    if use_ml:
        try:
            ml = classify_ml(video_path, contact_time_sec, frames_fps=frames_fps)
        except Exception as e:  # noqa: BLE001
            print(f'  [ensemble] ml step skipped: {e}', file=sys.stderr)

    traj = None
    if use_trajectory:
        try:
            from classify_shot_trajectory import classify_from_frames  # noqa: PLC0415
            frames, _fps = frames_fps if frames_fps is not None else extract_user_poses(video_path)
            traj = classify_from_frames(frames, fps, contact_time_sec, handedness=handedness)
        except Exception as e:  # noqa: BLE001
            print(f'  [ensemble] trajectory step skipped: {e}', file=sys.stderr)

    # ── serve ── geom's overhead-at-contact gate owns it. Trades ~0.5pt overall
    # accuracy for serve recall 15% -> 44% vs trajectory-kNN alone (measured);
    # worth it because a serve mislabelled as a groundstroke pollutes rally
    # grouping. Trajectory-kNN serve votes were tried as corroboration and made
    # it worse -- dropped.
    if g['shot_type'] == 'serve':
        return {'shot_type': 'serve', 'scores': g['scores'], 'source': 'geom_serve',
                'confidence': g['confidence']}

    # ── forehand vs backhand ──
    # broadcast: trajectory-kNN owns it (~85% pipeline domain).
    if traj and traj['shot_type'] in ('forehand', 'backhand') and traj.get('margin', 0) >= TRAJ_MARGIN_MIN:
        return {'shot_type': traj['shot_type'], 'scores': traj['scores'], 'source': 'trajectory',
                'confidence': round(min(1.0, 0.4 + traj['margin']), 3)}

    # phone: the trained model, when its winning-class probability clears the gate.
    if ml and ml['shot_type'] in ('forehand', 'backhand'):
        ml_conf = ml.get('scores', {}).get(ml['shot_type'], 0.0)
        if ml_conf >= ML_CONF_MIN:
            return {'shot_type': ml['shot_type'], 'scores': ml['scores'], 'source': 'ml',
                    'confidence': round(ml_conf, 3)}

    geom_floor = GEOM_CONF_MIN if use_trajectory else GEOM_CONF_MIN_NOTRAJ
    if g['shot_type'] in ('forehand', 'backhand') and g['confidence'] >= geom_floor:
        return {'shot_type': g['shot_type'], 'scores': g['scores'], 'source': 'geom',
                'confidence': g['confidence']}

    fallback = (traj or ml or g)
    return {'shot_type': 'uncertain', 'scores': fallback.get('scores', {}),
            'source': 'none', 'confidence': 0.0, 'best_guess': fallback.get('shot_type')}


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
