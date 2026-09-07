"""
Best-effort hook for compare_swing.py: when a real user has manually marked
their own contact frame (via ContactMarkingScreen.js), also runs the
automatic detector (find_contact_frame(), via the same cropped racket/ball
tracking verify_shot_contact.py already uses) against the same window and
logs the comparison as free, ongoing training data (source='user_submitted')
-- see contact_frame_training_log.py's module docstring for why this matters
(the detector was previously completely untrained).

Deliberately isolated in its own module with everything wrapped in one
try/except: this must NEVER affect the actual analysis response even if the
racket/ball model fails to load, the video is unusual, or anything else
goes wrong -- a skipped training example costs nothing, a broken /api/analyse
response costs a real user their result.
"""
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '16_shot_verification'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking'))

SEARCH_WINDOW_SEC = 0.3


def log_if_possible(video_path, frames, fps, user_frame):
    """frames: the same per-frame pose list extract_user_poses() already
    produced for this request (reused, no extra pose extraction)."""
    try:
        from racket_tracker import find_contact_frame, contact_frame_meta
        from verify_shot_contact import track_racket_and_ball_cropped
        import contact_frame_training_log as frame_log

        frames_by_idx = {f['frame']: f for f in frames}
        window_frames = int(SEARCH_WINDOW_SEC * fps * 2)  # generous padding around the user's mark
        frame_range = (user_frame - window_frames, user_frame + window_frames)
        detections = track_racket_and_ball_cropped(video_path, frames_by_idx, frame_range)
        student_frame, confidence, method = find_contact_frame(
            detections, user_frame, fps, search_window_sec=SEARCH_WINDOW_SEC)

        # method='wrist_velocity_fallback' means find_contact_frame() found
        # no real racket/ball evidence and just returned the anchor we gave
        # it back unchanged (user_frame itself here) -- logging that would
        # record a fake zero-error "perfect agreement" with no independent
        # signal behind it at all, silently inflating the apparent accuracy.
        # Only log when there's genuine evidence to compare against.
        if method == 'wrist_velocity_fallback':
            print('  [contact-frame-training] skipped: no racket/ball evidence found', file=sys.stderr)
            return

        meta = contact_frame_meta(detections, user_frame, fps, search_window_sec=SEARCH_WINDOW_SEC)
        frame_log.log_example(
            student_frame, confidence, method, user_frame, fps, source='user_submitted',
            student_meta=meta,
        )

        # Ride along: if a trained contact-frame model exists, log its
        # corrected frame vs the same human mark so it earns trust
        # independently (contact_frame_ml_training_log). Zero extra cost.
        try:
            from train_contact_frame_model import predict_contact_offset
            import contact_frame_ml_training_log as ml_log

            offset, available = predict_contact_offset({
                'student_method': method, 'student_confidence': confidence,
                'fps': fps, 'student_meta': meta, 'source': 'user_submitted',
            })
            if available:
                ml_log.log_example(student_frame + offset, student_frame, user_frame, fps,
                                   source='user_submitted', clip_path=video_path)
        except Exception as e:
            print(f'  [contact-frame-ml] skipped: {e}', file=sys.stderr)
    except Exception as e:
        print(f'  [contact-frame-training] skipped: {e}', file=sys.stderr)
