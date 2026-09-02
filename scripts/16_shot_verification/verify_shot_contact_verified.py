"""
Orchestrator for the shot-contact teacher-student loop. Mirrors
scripts/14_shot_classifier/classify_shot_verified.py's pattern exactly.

While the student (verify_shot_contact.py's geometric wrist-velocity +
racket/ball detector) is still learning (agreement rate below threshold,
per shot_contact_training_log.py), every request also calls the Claude
vision teacher, logs the (student_pick, teacher_pick, agreed) example, and
returns Claude's verdict (the teacher is authoritative during learning).
Once the student is trusted, Claude is skipped and the student's verdict
is returned directly -- saving API cost.

Usage:
  python verify_shot_contact_verified.py <video_path> <peak_frame> <fps>
"""
import argparse
import json
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '02_pose_extraction'))
from verify_shot_contact import (  # noqa: E402
    SEARCH_WINDOW_SEC, EXTRA_PAD_SEC, filter_verified_swings, verify_swings,
)
from shot_contact_training_log import (  # noqa: E402
    log_example, bucket_for, should_trust_bucket,
)
from shot_contact_verifier import verify_shot_contact  # noqa: E402
import shot_contact_ml_training_log  # noqa: E402
from train_shot_contact_model import MODEL_PATH as ML_MODEL_PATH, FEATURE_NAMES as ML_FEATURE_NAMES, features_from_student_meta  # noqa: E402

_ml_model = None
_ml_model_missing_logged = False


def _get_ml_model():
    global _ml_model, _ml_model_missing_logged
    if _ml_model is None:
        if not os.path.exists(ML_MODEL_PATH):
            if not _ml_model_missing_logged:
                print(f'[verify_shot_contact_verified] no trained model at {ML_MODEL_PATH} -- '
                      'run train_shot_contact_model.py first', file=sys.stderr)
                _ml_model_missing_logged = True
            return None
        import joblib
        _ml_model = joblib.load(ML_MODEL_PATH)
    return _ml_model


def predict_contact_ml(student_meta):
    """Same rules-derived signals as the geometric student
    (features_from_student_meta(), shared with train_shot_contact_model.py),
    combined by learned weights instead of should_trust_bucket()'s hand-picked
    trust thresholds. Returns (is_real_shot, available) -- available=False
    (is_real_shot=None) when no trained model exists yet, same
    no-model-yet convention classify_shot.classify_ml() uses via its own
    RuntimeError, just returned instead of raised since this is checked on
    every call, not opt-in."""
    model = _get_ml_model()
    if model is None:
        return None, False

    import numpy as np
    feats = features_from_student_meta(student_meta)
    x = np.full((1, len(ML_FEATURE_NAMES)), np.nan, dtype=float)
    for j, name in enumerate(ML_FEATURE_NAMES):
        v = feats.get(name)
        if v is not None:
            x[0, j] = float(v)

    pred = bool(model.predict(x)[0])
    return pred, True


def _sample_frames(video_path, frame_range, n=7):
    """n frames evenly spaced across frame_range (inclusive), for the
    multi-frame Claude call -- enough to show real motion without sending
    every single frame (cost)."""
    start, end = frame_range
    start = max(0, start)
    if end <= start:
        end = start + 1
    idxs = sorted({round(start + i * (end - start) / (n - 1)) for i in range(n)})
    cap = cv2.VideoCapture(video_path)
    frames = []
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()
    return frames


def _student_meta(swing):
    # racket_speed_at_contact/racket_peak_speed/contact_frame_guess were
    # already being computed by verify_swings() and discarded before this
    # point -- added here (purely additive, existing consumers of
    # contact_confidence/contact_method are unaffected) so
    # train_shot_contact_model.py has real numeric signals to learn from,
    # not just the collapsed method label.
    return {
        'contact_confidence': swing.get('contact_confidence'),
        'contact_method': swing.get('contact_method'),
        'racket_speed_at_contact': swing.get('racket_speed_at_contact'),
        'racket_peak_speed': swing.get('racket_peak_speed'),
        'contact_frame_guess': swing.get('contact_frame_guess'),
    }


def get_verified_shot_contact(video_path, swing, fps, use_verifier=True, log_lock=None):
    """
    swing: one swing dict from detect_swings.find_swing_peaks(), already
    run through verify_shot_contact.verify_swings() (has 'contact_method'/
    'contact_confidence' set).

    Returns (is_real_shot, meta_dict). meta_dict includes 'shot_type' when
    the teacher was called and judged it a real shot (combined call --
    see shot_contact_verifier.py's module docstring for why).
    """
    student_is_shot = bool(filter_verified_swings([swing]))
    bucket = bucket_for(swing.get('contact_method'))
    student_meta = _student_meta(swing)

    ml_is_shot, ml_available = predict_contact_ml(student_meta)
    rule_trusted = should_trust_bucket(bucket)
    ml_trusted = ml_available and shot_contact_ml_training_log.should_trust_student()

    if not use_verifier or rule_trusted or ml_trusted:
        # Prefer whichever student actually earned trust for this case --
        # if only the ML model has (rule-based bucket hasn't), use its pick;
        # otherwise (rule trusted, or neither -- use_verifier=False) use the
        # rule-based one, same as before this model existed.
        picked_is_shot = ml_is_shot if (ml_trusted and not rule_trusted) else student_is_shot
        return picked_is_shot, {
            'source': 'student_ml' if (ml_trusted and not rule_trusted) else 'student',
            'verified': False, 'bucket': bucket, 'student_meta': student_meta,
        }

    try:
        window_frames = int((SEARCH_WINDOW_SEC + EXTRA_PAD_SEC) * fps)
        frame_range = (swing['peak_frame'] - window_frames, swing['peak_frame'] + window_frames)
        sampled = _sample_frames(video_path, frame_range)
        teacher_result = verify_shot_contact(sampled, student_is_shot)
    except Exception as e:
        print(f'  Contact verifier call failed ({e}) -- falling back to student pick', file=sys.stderr)
        return student_is_shot, {
            'source': 'student', 'verified': False,
            'student_meta': _student_meta(swing), 'verifier_error': str(e),
        }

    teacher_is_shot = bool(teacher_result['is_real_shot'])
    agreed = teacher_is_shot == student_is_shot
    log_example(student_is_shot, teacher_is_shot, agreed, source='claude',
                student_meta=student_meta, lock=log_lock,
                clip_path=video_path, contact_frame=swing.get('peak_frame'))

    if ml_available:
        # Rides along on the Claude call above -- zero extra cost, same
        # reasoning shot_classifier_ml_training_log.py's docstring gives.
        shot_contact_ml_training_log.log_example(
            ml_is_shot, teacher_is_shot, ml_is_shot == teacher_is_shot, lock=log_lock,
            clip_path=video_path, contact_frame=swing.get('peak_frame'))

    return teacher_is_shot, {
        'source': 'claude_verified', 'verified': True, 'agreed_with_student': agreed,
        'student_meta': student_meta, 'reasoning': teacher_result.get('reasoning'),
        'shot_type': teacher_result.get('shot_type'),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('peak_frame', type=int)
    parser.add_argument('fps', type=float)
    parser.add_argument('--no-verifier', action='store_true', help='Skip Claude, use the geometric student only')
    args = parser.parse_args()

    swing = {'peak_frame': args.peak_frame}
    try:
        verify_swings(args.video, [swing], args.fps, use_crop=False)  # no pose data available from bare CLI args
        is_real_shot, meta = get_verified_shot_contact(
            args.video, swing, args.fps, use_verifier=not args.no_verifier)
        print(json.dumps({'is_real_shot': is_real_shot, **meta}))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
