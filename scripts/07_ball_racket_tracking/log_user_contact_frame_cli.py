"""
CLI entry point for the free, ongoing contact-frame training hook --
spawned as a DETACHED background process by backend/src/routes/analyse.js,
AFTER the user's actual /api/analyse response has already been sent. See
log_user_contact_frame.py's module docstring for why this exists and
contact_frame_training_log.py's for what it's training.

Deliberately a separate process rather than something run inline inside
compare_swing.py: measured this session at ~5s of racket/ball tracking work
regardless of outcome -- real, noticeable latency on a synchronous
user-facing response for a step that adds zero value to the user. Running
detached means that cost is fully decoupled from response time; the user
never waits on it.

Does its own pose extraction via extract_poses.py (NOT compare_swing.py's
own extract_user_poses() -- confirmed this session those two use different
landmark shapes: extract_poses.py's landmarks is a LIST of per-landmark
dicts, matching what track_racket_and_ball_cropped()/_frame_bbox() expect,
while compare_swing.py's is a dict keyed by landmark name, for its own
internal use only. Using the wrong one throws "string indices must be
integers" deep inside _frame_bbox.).

Usage:
  python log_user_contact_frame_cli.py <video_path> <contact_time_sec>
"""
import json
import os
import sys
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking'))


def main():
    if len(sys.argv) < 3:
        print('usage: log_user_contact_frame_cli.py <video_path> <contact_time_sec>', file=sys.stderr)
        sys.exit(1)
    video_path = sys.argv[1]
    contact_time_sec = float(sys.argv[2])

    from extract_poses import extract_poses  # noqa: E402
    from log_user_contact_frame import log_if_possible  # noqa: E402

    fd, tmp_path = tempfile.mkstemp(suffix='.json', prefix='contact_frame_poses_')
    os.close(fd)
    try:
        extract_poses(video_path, tmp_path, sample_every=1)
        with open(tmp_path) as f:
            pose_data = json.load(f)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    frames = pose_data.get('frames', [])
    fps = pose_data.get('fps')
    if not frames or not fps:
        print('  [contact-frame-training] skipped: no pose frames decoded', file=sys.stderr)
        return

    user_frame = round(contact_time_sec * fps)
    log_if_possible(video_path, frames, fps, user_frame)


if __name__ == '__main__':
    main()
