"""
Orchestrator for the shot-classifier teacher-student loop. Mirrors
scripts/09_coaching_ai/select_coaching_tips.py's pattern exactly.

Two students now, checked in order:
  1. The trained ML model (classify_shot.classify_ml(), see
     train_shot_classifier_model.py) -- its OWN trust gate
     (shot_classifier_ml_training_log.py), checked first. Once it clears
     50+ examples at >=90% agreement with Claude, its pick is returned
     directly and Claude is skipped entirely for shot classification.
  2. The original rule-based student (classify_shot.classify(),
     shot_classifier_training_log.py) -- kept as the fallback while the ML
     model doesn't have a trained model file yet or hasn't earned trust,
     same behavior this function always had.

While NEITHER student is trusted, every request calls the Claude vision
verifier once and logs BOTH the ML model's and the rule-based student's
picks against that same verdict -- one Claude call, two training log
entries, no extra API cost for having two candidate students in flight.

Usage:
  python classify_shot_verified.py <video_path> <contact_time_sec>
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '05_angle_detection'))
from classify_shot import classify, classify_ml, classify_ensemble  # noqa: E402
from shot_classifier_training_log import log_example as log_rule_example  # noqa: E402
from shot_classifier_training_log import should_trust_student as should_trust_rule_student  # noqa: E402
import shot_classifier_ml_training_log as ml_log  # noqa: E402
import shot_classifier_ensemble_training_log as ens_log  # noqa: E402
from shot_classifier_verifier import verify_shot  # noqa: E402
from infer_angle import extract_frame  # noqa: E402

# The rally pipeline (detect_rallies / analyze_rallies_parallel) runs on
# broadcast-ish footage where the trajectory-kNN step is reliable; a future
# phone-upload caller should set RALLYMAX_ENSEMBLE_NO_TRAJECTORY=1.
_ENSEMBLE_USE_TRAJECTORY = os.environ.get('RALLYMAX_ENSEMBLE_NO_TRAJECTORY') != '1'


def get_verified_shot_type(video_path, contact_time_sec, use_verifier=True, frames_fps=None,
                           log_lock=None, handedness='right', use_trajectory=None):
    """
    frames_fps: optional pre-extracted (frames, fps) tuple, passed straight
    through to classify()/classify_ml() to skip re-running pose extraction
    when the caller (analyze_rallies.py) already has it for this exact
    video. Defaults to None so existing behavior (extract internally) is
    unchanged.

    log_lock: optional lock passed straight through to both training logs'
    log_example() -- see shot_classifier_training_log.py's docstring.
    Defaults to None (no locking), safe for single-process callers.

    use_trajectory: override the ensemble's trajectory-kNN step. None (default)
    = fall back to the _ENSEMBLE_USE_TRAJECTORY env default (on). Phone-footage
    callers (detect_rallies.py --no-trajectory) pass False -- the pro trajectory
    pool is broadcast and mislabels every phone selfie backhand as a forehand.
    """
    if use_trajectory is None:
        use_trajectory = _ENSEMBLE_USE_TRAJECTORY
    # ── ensemble student (geom serve gate + trajectory-kNN FH/BH) ──
    ens_result = None
    try:
        ens_result = classify_ensemble(video_path, contact_time_sec, frames_fps=frames_fps,
                                       handedness=handedness, use_trajectory=use_trajectory)
    except Exception as e:  # noqa: BLE001
        print(f'  [ensemble] skipped: {e}', file=sys.stderr)

    ens_definite = ens_result is not None and ens_result['shot_type'] in ('forehand', 'backhand', 'serve')
    # Same rule as the other students: `not use_verifier` ("don't pay for
    # Claude") returns the student; otherwise it must earn trust first.
    if ens_definite and (not use_verifier or ens_log.should_trust_student()):
        return ens_result['shot_type'], {'source': f'student_ensemble:{ens_result["source"]}',
                                         'verified': False, 'scores': ens_result['scores'],
                                         'confidence': ens_result['confidence']}

    ml_result = None
    try:
        ml_result = classify_ml(video_path, contact_time_sec, frames_fps=frames_fps)
    except Exception:
        pass  # no trained model yet, or it failed on this swing -- fall back to the rule-based student below

    # Deliberately NOT gated on `not use_verifier` -- that flag means
    # "skip paying for Claude," not "trust an unproven model." Callers
    # that opt out of verification (e.g. RALLYMAX_SKIP_CLASSIFIER_VERIFIER)
    # should keep getting the already-characterized rule-based fallback
    # below until the ML model has actually earned trust via its own
    # 50-example gate, same as it would with verification left on.
    if ml_result is not None and ml_log.should_trust_student():
        return ml_result['shot_type'], {'source': 'student_ml', 'verified': False, 'scores': ml_result['scores']}

    student_result = classify(video_path, contact_time_sec, frames_fps=frames_fps)
    student_pick = student_result['shot_type']
    scores = student_result['scores']

    if not use_verifier or should_trust_rule_student():
        return student_pick, {'source': 'student', 'verified': False, 'scores': scores}

    try:
        if frames_fps is not None:
            _, fps = frames_fps
        else:
            # extract_frame expects a frame number; classify() already knows
            # fps internally but doesn't expose it, so re-derive via cv2
            # quickly here rather than changing classify()'s return shape.
            import cv2
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            cap.release()
        contact_frame = round(contact_time_sec * fps)
        frame = extract_frame(video_path, contact_frame)

        claude_result = verify_shot(frame, scores, student_pick)
    except Exception as e:
        print(f'  Verifier call failed ({e}) -- falling back to student pick', file=sys.stderr)
        return student_pick, {'source': 'student', 'verified': False, 'scores': scores, 'verifier_error': str(e)}

    claude_pick = claude_result['shot_type']
    agreed = claude_pick == student_pick
    log_rule_example(scores, student_pick, claude_pick, agreed, lock=log_lock,
                      clip_path=video_path, contact_frame=contact_frame)

    # Log the ML model's pick against this same Claude verdict too, if it
    # produced one -- zero extra Claude calls, just an extra comparison
    # against the call that already happened.
    if ml_result is not None:
        ml_agreed = claude_pick == ml_result['shot_type']
        ml_log.log_example(ml_result['scores'], ml_result['shot_type'], claude_pick, ml_agreed, lock=log_lock,
                            clip_path=video_path, contact_frame=contact_frame)

    # Same for the ensemble -- shadow-mode logging so it earns trust on real
    # pipeline data. An 'uncertain'/None pick is logged with agreed=None so it
    # doesn't count toward the trust rate (those are exactly the cases that
    # SHOULD reach Claude).
    if ens_result is not None:
        ens_pick = ens_result['shot_type'] if ens_definite else None
        ens_log.log_example(ens_result.get('scores', {}), ens_pick, claude_pick,
                            (claude_pick == ens_pick) if ens_pick else None, lock=log_lock,
                            clip_path=video_path, contact_frame=contact_frame,
                            source=ens_result.get('source'))

    return claude_pick, {
        'source': 'claude_verified', 'verified': True, 'agreed_with_student': agreed,
        'scores': scores, 'reasoning': claude_result.get('reasoning'),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('contact_time_sec', type=float)
    parser.add_argument('--no-verifier', action='store_true', help='Skip Claude, use the rule-based student only')
    args = parser.parse_args()

    try:
        shot_type, meta = get_verified_shot_type(args.video, args.contact_time_sec, use_verifier=not args.no_verifier)
        print(json.dumps({'shot_type': shot_type, **meta}))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
