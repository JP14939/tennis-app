"""
One-off backfill: recovers the 29 real Claude shot-type verdicts from the
2026-08-19 IMG_5822.MOV detect_rallies.py run that never reached the
classifier training logs, because of the 'claude' vs 'claude_verified'
source-string bug in detect_rallies.py (now fixed).

Those verdicts are still known -- they were printed to stderr by
apply_serve_gate() at the time (timestamp + shot_type for every one of the
30 real swings except the single one that was silently 'kept' without a
print). This replays exactly what _log_classifiers_against_known_teacher_
pick() would have done at the time: extract poses once for the whole
video (free, local, no Claude call), then log the rule-based and ML
classifiers' local predictions against each already-known real verdict.

No Claude spend -- these are real answers Claude already gave and was
already paid for; this just finally records them.

Usage:
  python backfill_ig5822_classifier_log.py
"""
import os
import sys
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '02_pose_extraction'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '14_shot_classifier'))

from extract_poses import extract_poses  # noqa: E402
from detect_rallies import _as_classify_frames, _log_classifiers_against_known_teacher_pick  # noqa: E402

VIDEO_PATH = r'C:\Users\jackp\Downloads\IMG_5822.MOV'
FPS = 30.0

# (peak_time_sec, teacher_shot_type) -- read directly off apply_serve_gate()'s
# real stderr output from that run. The 248.7s forehand is deliberately
# excluded: it already made it into the training logs via a different path
# (the shot_type-was-None fallback to get_verified_shot_type(), which made
# its own separate, already-tracked Claude call) -- logging it again here
# would double-count that one example.
KNOWN_VERDICTS = [
    (155.9, 'forehand'),
    (212.5, 'serve'),
    (231.5, 'serve'),
    (239.9, 'serve'),
    (278.7, 'serve'),
    (301.9, 'serve'),
    (440.8, 'serve'),
    (449.4, 'serve'),
    (474.3, 'serve'),
    (498.1, 'serve'),
    (528.3, 'serve'),
    (537.1, 'serve'),
    (561.5, 'serve'),
    (567.7, 'serve'),
    (585.4, 'serve'),
    (618.1, 'serve'),
    (620.8, 'serve'),
    (643.4, 'serve'),
    (657.3, 'forehand'),
    (673.7, 'serve'),
    (701.7, 'serve'),
    (726.7, 'serve'),
    (759.6, 'serve'),
    (787.0, 'serve'),
    (808.4, 'serve'),
    (832.1, 'serve'),
    (857.2, 'serve'),
    (900.2, 'serve'),
]


def main():
    if not os.path.exists(VIDEO_PATH):
        print(f'Video not found: {VIDEO_PATH}', file=sys.stderr)
        sys.exit(1)

    print(f'Extracting poses for {VIDEO_PATH} (one-time, local, no Claude call)...')
    with tempfile.TemporaryDirectory() as tmp:
        pose_path = os.path.join(tmp, 'poses.json')
        extract_poses(VIDEO_PATH, pose_path, sample_every=3)
        with open(pose_path) as f:
            pose_data = json.load(f)

    frames = pose_data['frames']
    classify_frames = _as_classify_frames(frames)

    print(f'\nBackfilling {len(KNOWN_VERDICTS)} known real verdicts into the classifier training logs...')
    for peak_time, teacher_pick in KNOWN_VERDICTS:
        _log_classifiers_against_known_teacher_pick(
            VIDEO_PATH, peak_time, teacher_pick, classify_frames, FPS, log_lock=None)
        print(f'  logged {peak_time:.1f}s -> {teacher_pick}')

    print(f'\nDone. Backfilled {len(KNOWN_VERDICTS)} examples.')


if __name__ == '__main__':
    main()
