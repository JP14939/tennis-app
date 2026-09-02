"""
Rich pose-derived feature extraction for training a shot-type classifier.

Reuses the exact same landmark reads score_forehand/score_backhand/
score_serve already do (extract_clips.py's get_lm/visible/dist2d,
nearest_pose) -- but exposes the raw intermediate quantities as a feature
vector instead of collapsing them into one blended 0-1 score per shot
type. Same inputs those scorers see, more information kept: a model
trained on this can learn a smarter combination than the hand-picked
weights/thresholds in extract_clips.py, rather than being capped by
what those functions already threw away.

Source: the 116 real-shot-labeled (non-'skip') entries in the amateur eval
dataset --
  data/08_coaching_ai/amateur_swing_labels.json   Claude-vision ground truth
  data/04_clips/amateur/manifest.json             peak_frame per swing (SOURCE-video-relative)
  data/03_swing_detection/amateur_<id>_swings.json  start_frame per swing, to convert to clip-relative
  data/17_amateur_eval/poses/<video_id>_<swing_id>.json  cached extract_poses() output (raw
    list-format landmarks, clip-relative frame numbers) -- already computed for the shot-contact
    verifier in evaluate_amateur_dataset.py, reused here rather than re-extracting.
Same clip_peak_frame = peak_frame_source - start_frame conversion evaluate_amateur_dataset.py's
process_example() already uses, for the same reason (clips were cut with extract_clip(), so
clip frame 0 == source's start_frame).

Usage:
  python extract_training_features.py

Output: data/14_shot_classifier/training_features.json --
  [{video_id, swing_id, label, features: {...}}, ...]
"""
import json
import math
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '04_clip_extraction'))

from paths import DATA_DIR  # noqa: E402
from extract_clips import get_lm, visible, dist2d, nearest_pose  # noqa: E402

LABELS_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'amateur_swing_labels.json')
MANIFEST_PATH = os.path.join(DATA_DIR, '04_clips', 'amateur', 'manifest.json')
SWINGS_DIR = os.path.join(DATA_DIR, '03_swing_detection')
POSES_CACHE_DIR = os.path.join(DATA_DIR, '17_amateur_eval', 'poses')
OUTPUT_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'training_features.json')

# Same window shape classify_shot.py's classify() uses for the serve signal.
SERVE_WINDOW_PRE_SEC = 1.0
SERVE_WINDOW_POST_SEC = 0.5
SERVE_WINDOW_STEP_FRAMES = 3

# Bump whenever the SEMANTICS of any feature change (not just adding one) --
# train_shot_classifier_model.py writes this into the model meta and
# classify_shot._get_ml_model() refuses a model whose version doesn't match,
# falling back to the rule scorers instead of silently feeding it
# differently-scaled inputs.
#   v1        : raw MediaPipe image-space magnitudes (framing-dependent)
#   v2-bodynorm: magnitude features divided by torso length -> comparable
#               across phone-selfie vs. broadcast framing (2026-09-02)
FEATURE_VERSION = 'v2-bodynorm'

# Every feature this function can produce, in a fixed order -- callers
# (the trainer, the ML classify() at inference time) build their input
# vector by reading these keys in this order, so a mismatch would be
# caught immediately rather than silently misaligning columns.
FEATURE_NAMES = [
    'rw_y_rel_shoulder', 'lw_y_rel_shoulder', 'rw_x_rel_midline', 'lw_x_rel_midline',
    'wrist_separation', 'rw_velocity', 'lw_velocity', 'rh_y_rel_shoulder',
    'best_overhead_margin', 'elbow_elevated', 'wrist_above_nose',
]


def extract_features(peak_lm, prev_lm, window_lms):
    """
    Raw intermediate quantities score_forehand/score_backhand/score_serve
    already compute internally but never expose individually -- same
    landmark reads, no new pose data. Missing/insufficient landmarks ->
    None for that feature (not 0.0, which would be a real, misleading
    value) -- callers must handle Nones explicitly.
    """
    rw = get_lm(peak_lm, 'right_wrist')
    lw = get_lm(peak_lm, 'left_wrist')
    rs = get_lm(peak_lm, 'right_shoulder')
    ls = get_lm(peak_lm, 'left_shoulder')
    rh = get_lm(peak_lm, 'right_hip')
    lh = get_lm(peak_lm, 'left_hip')
    rw_prev = get_lm(prev_lm, 'right_wrist') if prev_lm else None
    lw_prev = get_lm(prev_lm, 'left_wrist') if prev_lm else None

    # body_scale = torso length (shoulder-mid -> hip-mid), fallback shoulder
    # width. Every magnitude feature below is divided by it so a phone selfie
    # (player fills the frame) and a broadcast clip (player small) produce
    # comparable numbers -- see train_shot_classifier_model.py's 2026-08-27
    # note on why raw magnitudes blocked the pro-review clips. None when the
    # torso isn't visible -> the magnitude features become None (imputed).
    body_scale = None
    if visible(rs) and visible(ls):
        sh_mid = ((rs['x'] + ls['x']) / 2, (rs['y'] + ls['y']) / 2)
        if visible(rh) and visible(lh):
            hip_mid = ((rh['x'] + lh['x']) / 2, (rh['y'] + lh['y']) / 2)
            body_scale = math.hypot(sh_mid[0] - hip_mid[0], sh_mid[1] - hip_mid[1])
        if not body_scale:
            body_scale = abs(rs['x'] - ls['x'])
    if body_scale is not None and body_scale < 1e-4:
        body_scale = None

    def _n(v):
        return round(v / body_scale, 4) if (v is not None and body_scale) else None

    features = {}

    features['rw_y_rel_shoulder'] = _n(rs['y'] - rw['y']) if visible(rw) and visible(rs) else None
    features['lw_y_rel_shoulder'] = _n(ls['y'] - lw['y']) if visible(lw) and visible(ls) else None

    mid_x = (rs['x'] + ls['x']) / 2 if visible(rs) and visible(ls) else None
    features['rw_x_rel_midline'] = _n(rw['x'] - mid_x) if visible(rw) and mid_x is not None else None
    features['lw_x_rel_midline'] = _n(lw['x'] - mid_x) if visible(lw) and mid_x is not None else None

    features['wrist_separation'] = _n(abs(rw['x'] - lw['x'])) if visible(rw) and visible(lw) else None
    features['rw_velocity'] = _n(dist2d(rw, rw_prev)) if visible(rw) and visible(rw_prev) else None
    features['lw_velocity'] = _n(dist2d(lw, lw_prev)) if visible(lw) and visible(lw_prev) else None
    features['rh_y_rel_shoulder'] = _n(rh['y'] - (rs['y'] + ls['y']) / 2) \
        if visible(rh) and visible(rs) and visible(ls) else None

    # Serve-window scan, matching score_serve()'s best-overhead search
    # across the whole window rather than just the peak frame.
    best_overhead = None
    elbow_elevated = False
    wrist_above_nose = False
    for lm in (window_lms or []) + [peak_lm]:
        f_rw, f_lw = get_lm(lm, 'right_wrist'), get_lm(lm, 'left_wrist')
        f_rs, f_ls = get_lm(lm, 'right_shoulder'), get_lm(lm, 'left_shoulder')
        f_re, f_nose = get_lm(lm, 'right_elbow'), get_lm(lm, 'nose')
        if not (visible(f_rs) and visible(f_ls)):
            continue
        if visible(f_rw):
            overhead = f_rs['y'] - f_rw['y']
            if best_overhead is None or overhead > best_overhead:
                best_overhead = overhead
        if visible(f_lw):
            overhead = f_ls['y'] - f_lw['y']
            if best_overhead is None or overhead > best_overhead:
                best_overhead = overhead
        if visible(f_re) and f_re['y'] < f_rs['y']:
            elbow_elevated = True
        nose_margin = 0.05 * body_scale if body_scale else 0.05
        if visible(f_nose) and visible(f_rw) and f_rw['y'] < f_nose['y'] - nose_margin:
            wrist_above_nose = True

    features['best_overhead_margin'] = _n(best_overhead) if best_overhead is not None else None
    features['elbow_elevated'] = elbow_elevated
    features['wrist_above_nose'] = wrist_above_nose

    return features


def build_window(pose_index, contact_frame, fps):
    lo = -int(SERVE_WINDOW_PRE_SEC * fps)
    hi = int(SERVE_WINDOW_POST_SEC * fps)
    window = []
    for offset in range(lo, hi, SERVE_WINDOW_STEP_FRAMES):
        lm = nearest_pose(pose_index, contact_frame + offset)
        if lm:
            window.append(lm)
    return window


def extract_for_clip(pose_path, clip_peak_frame, fps):
    """Shared by the offline dataset builder below and (later) inference --
    given a cached pose file and the clip-relative contact frame, returns
    the same shape extract_features() does."""
    with open(pose_path) as f:
        pose_data = json.load(f)
    pose_index = {fr['frame']: fr['landmarks'] for fr in pose_data['frames'] if fr['landmarks']}
    peak_lm = nearest_pose(pose_index, clip_peak_frame)
    if peak_lm is None:
        return None
    prev_lm = nearest_pose(pose_index, clip_peak_frame - 3)
    window_lms = build_window(pose_index, clip_peak_frame, fps)
    return extract_features(peak_lm, prev_lm, window_lms)


def main():
    with open(LABELS_PATH) as f:
        labels = json.load(f)['labels']
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    swings_cache = {}
    rows = []
    skipped = []

    for entry in manifest:
        video_id, swing_id = entry['video_id'], entry['swing_id']
        key = f'{video_id}_{swing_id}'
        label = labels.get(key)
        if label is None or label == 'skip':
            continue  # no ground truth, or not a real shot -- nothing to train shot-type on

        if video_id not in swings_cache:
            swings_path = os.path.join(SWINGS_DIR, f'amateur_{video_id}_swings.json')
            with open(swings_path) as f:
                swings_cache[video_id] = {sw['swing_id']: sw for sw in json.load(f)['swings']}
        sw_meta = swings_cache[video_id].get(swing_id)
        if sw_meta is None:
            skipped.append({'key': key, 'reason': 'swing not found in swings json'})
            continue

        pose_path = os.path.join(POSES_CACHE_DIR, f'{key}.json')
        if not os.path.exists(pose_path):
            skipped.append({'key': key, 'reason': 'no cached poses'})
            continue
        with open(pose_path) as f:
            fps = json.load(f)['fps']

        clip_peak_frame = entry['peak_frame'] - sw_meta['start_frame']
        features = extract_for_clip(pose_path, clip_peak_frame, fps)
        if features is None:
            skipped.append({'key': key, 'reason': 'no pose near contact frame'})
            continue

        rows.append({'video_id': video_id, 'swing_id': swing_id, 'label': label, 'features': features})

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(rows, f, indent=2)

    print(f'{len(rows)} feature rows written to {OUTPUT_PATH}')
    by_label = {}
    for r in rows:
        by_label[r['label']] = by_label.get(r['label'], 0) + 1
    print('by label:', by_label)
    if skipped:
        print(f'{len(skipped)} entries skipped:')
        for s in skipped[:20]:
            print(' ', s)


if __name__ == '__main__':
    main()
