"""
Offline, zero-API-cost tuning harness for extract_clips.py's score_forehand/
score_backhand/score_serve -- the rule-based scorers classify_shot.py runs
head-to-head (argmax) to pick a shot type. The amateur-dataset evaluation
(evaluate_amateur_dataset.py) found only 37.1% classifier accuracy against
116 real labeled swings; visual inspection of real misclassifications traced
it to score_backhand's `wrist_sep < 0.15` (two-handed) and
`lw_vel >= rw_vel * 0.7` (left-wrist-active) signals firing on genuine
one-handed forehand footage, likely because MediaPipe landmarks are noisier
on real, distant amateur video than the curated pro clips these thresholds
were tuned against.

Zero video decoding, zero MediaPipe, zero Claude API calls -- reuses the
pose landmarks already cached to data/17_amateur_eval/poses/*.json by
yesterday's evaluate_amateur_dataset.py run (extract_poses()'s list-shaped
format, exactly what extract_clips.py's get_lm() already expects), so every
candidate scorer variant can be tested in a fraction of a second.

Usage:
  python tune_shot_scorers.py
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '04_clip_extraction'))

from paths import DATA_DIR  # noqa: E402
from extract_clips import get_lm, visible, dist2d, build_pose_index, nearest_pose  # noqa: E402

LABELS_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'amateur_swing_labels.json')
MANIFEST_PATH = os.path.join(DATA_DIR, '04_clips', 'amateur', 'manifest.json')
SWINGS_DIR = os.path.join(DATA_DIR, '03_swing_detection')
POSES_CACHE_DIR = os.path.join(DATA_DIR, '17_amateur_eval', 'poses')

_swings_cache = {}


def load_swings(video_id):
    if video_id not in _swings_cache:
        with open(os.path.join(SWINGS_DIR, f'amateur_{video_id}_swings.json')) as f:
            data = json.load(f)
        _swings_cache[video_id] = {sw['swing_id']: sw for sw in data['swings']}
    return _swings_cache[video_id]


def load_examples():
    """
    Returns a list of (key, label, peak_lm, prev_lm, window_lms, fps) --
    everything every scorer variant needs, precomputed once so tuning
    iterations only re-run the scoring math, not pose lookup.
    """
    with open(LABELS_PATH) as f:
        labels = json.load(f)['labels']
    with open(MANIFEST_PATH) as f:
        manifest_by_key = {f"{m['video_id']}_{m['swing_id']}": m for m in json.load(f)}

    examples = []
    for key, label in labels.items():
        if label == 'skip':
            continue  # no true shot type to score against
        m = manifest_by_key.get(key)
        if m is None:
            continue
        cache_path = os.path.join(POSES_CACHE_DIR, f'{key}.json')
        if not os.path.exists(cache_path):
            continue
        with open(cache_path) as f:
            pose_data = json.load(f)
        fps = pose_data['fps']
        pose_index = build_pose_index(pose_data['frames'])

        sw = load_swings(m['video_id']).get(m['swing_id'])
        if sw is None:
            continue
        clip_peak_frame = m['peak_frame'] - sw['start_frame']

        peak_lm = nearest_pose(pose_index, clip_peak_frame)
        prev_lm = nearest_pose(pose_index, clip_peak_frame - 3)
        if peak_lm is None:
            continue

        window_lms = []
        for offset in range(-int(fps), int(fps * 0.5), 3):
            lm = nearest_pose(pose_index, clip_peak_frame + offset)
            if lm:
                window_lms.append(lm)

        examples.append({'key': key, 'label': label, 'peak_lm': peak_lm, 'prev_lm': prev_lm,
                          'window_lms': window_lms})
    return examples


def evaluate(scorers, examples):
    """scorers: {'forehand': fn, 'backhand': fn, 'serve': fn} -- same shape as
    extract_clips.SCORERS. Returns (accuracy, confusion_counter, n)."""
    from collections import Counter
    confusion = Counter()
    correct = 0
    for ex in examples:
        scores = {}
        for shot_type, scorer in scorers.items():
            if shot_type == 'serve':
                score, _ = scorer(ex['peak_lm'], ex['prev_lm'], ex['window_lms'])
            else:
                score, _ = scorer(ex['peak_lm'], ex['prev_lm'])
            scores[shot_type] = score
        pred = max(scores, key=scores.get)
        confusion[(ex['label'], pred)] += 1
        if pred == ex['label']:
            correct += 1
    n = len(examples)
    return (correct / n if n else 0.0), confusion, n


def print_confusion(confusion):
    for (true, pred), cnt in sorted(confusion.items()):
        flag = '' if true == pred else '  <-- MISCLASSIFIED'
        print(f'    true={true:10s} pred={pred:10s}  n={cnt}{flag}')


# ── Baseline (current extract_clips.py logic, unmodified) ──────────────────

def baseline_scorers():
    from extract_clips import score_forehand, score_backhand, score_serve
    return {'forehand': score_forehand, 'backhand': score_backhand, 'serve': score_serve}


# ── Candidate variants ──────────────────────────────────────────────────────
# Each variant only overrides score_backhand (the confirmed culprit) unless
# noted -- score_forehand/score_serve are re-tested unmodified each time so
# any accuracy change is attributable to the one thing that changed.

def variant_stricter_two_handed(peak_lm, prev_lm):
    """
    Candidate 1: raise the two-handed wrist-separation threshold's bar --
    require the wrists to be genuinely close (a real two-handed grip), not
    just "close enough" at 0.15 normalized units, which real testing found
    firing on one-handed forehands where MediaPipe's wrist estimates were
    noisy. Tightened 0.15 -> 0.09 (empirically the real two-handed backhand
    examples in this dataset cluster well under that; see tuning output).
    """
    rw = get_lm(peak_lm, 'right_wrist')
    lw = get_lm(peak_lm, 'left_wrist')
    rs = get_lm(peak_lm, 'right_shoulder')
    ls = get_lm(peak_lm, 'left_shoulder')
    rh = get_lm(peak_lm, 'right_hip')

    if not all(visible(x) for x in [rw, lw, rs, ls]):
        return 0.3, ['insufficient landmarks']

    score = 0.0
    reasons = []
    mid_x = (rs['x'] + ls['x']) / 2

    if rw['y'] > (rs['y'] - 0.05):
        score += 0.2
        reasons.append('wrist not overhead')

    wrist_sep = abs(rw['x'] - lw['x'])
    if wrist_sep < 0.09:
        score += 0.35
        reasons.append(f'wrists close together (sep={wrist_sep:.3f}) = two-handed')

    rw_prev = get_lm(prev_lm, 'right_wrist') if prev_lm else None
    lw_prev = get_lm(prev_lm, 'left_wrist') if prev_lm else None
    rw_vel = dist2d(rw, rw_prev) if rw_prev else 0
    lw_vel = dist2d(lw, lw_prev) if lw_prev else 0

    if lw_vel >= rw_vel * 0.7:
        score += 0.25
        reasons.append('left wrist active')

    avg_wrist_x = (rw['x'] + lw['x']) / 2
    if avg_wrist_x > mid_x:
        score += 0.2
        reasons.append('wrists right of midline')

    if visible(rh) and rh['y'] > 0.4:
        score += 0.1
        reasons.append('standing posture')

    return min(score, 1.0), reasons


def variant_require_both_hand_signals(peak_lm, prev_lm):
    """
    Candidate 2: same tightened wrist_sep as candidate 1, but ALSO require
    lw_vel to be genuinely close to rw_vel (>= 0.85x, not 0.7x) before
    crediting 'left wrist active' -- on a real one-handed forehand the
    off-hand still moves for balance, so 0.7x was too easy to clear by
    chance. Two independent, both-tightened two-handed signals should be
    much harder for a one-handed swing to trigger simultaneously.
    """
    rw = get_lm(peak_lm, 'right_wrist')
    lw = get_lm(peak_lm, 'left_wrist')
    rs = get_lm(peak_lm, 'right_shoulder')
    ls = get_lm(peak_lm, 'left_shoulder')
    rh = get_lm(peak_lm, 'right_hip')

    if not all(visible(x) for x in [rw, lw, rs, ls]):
        return 0.3, ['insufficient landmarks']

    score = 0.0
    reasons = []
    mid_x = (rs['x'] + ls['x']) / 2

    if rw['y'] > (rs['y'] - 0.05):
        score += 0.2
        reasons.append('wrist not overhead')

    wrist_sep = abs(rw['x'] - lw['x'])
    if wrist_sep < 0.09:
        score += 0.35
        reasons.append(f'wrists close together (sep={wrist_sep:.3f}) = two-handed')

    rw_prev = get_lm(prev_lm, 'right_wrist') if prev_lm else None
    lw_prev = get_lm(prev_lm, 'left_wrist') if prev_lm else None
    rw_vel = dist2d(rw, rw_prev) if rw_prev else 0
    lw_vel = dist2d(lw, lw_prev) if lw_prev else 0

    if lw_vel >= rw_vel * 0.85:
        score += 0.25
        reasons.append('left wrist active')

    avg_wrist_x = (rw['x'] + lw['x']) / 2
    if avg_wrist_x > mid_x:
        score += 0.2
        reasons.append('wrists right of midline')

    if visible(rh) and rh['y'] > 0.4:
        score += 0.1
        reasons.append('standing posture')

    return min(score, 1.0), reasons


def variant_serve_boosted_overhead(peak_lm, prev_lm, window_lms=None):
    """
    Candidate 3: score_serve's overhead credit (min(0.55, best_overhead*2.5))
    barely rewards the overhead margins real amateur serves actually show
    (~0.11-0.13 y-units, per diagnostic output -- nowhere near what would be
    needed to hit the 0.55 cap). Meanwhile score_forehand/score_backhand's
    peak-FRAME-only "wrist not overhead" check doesn't exclude serves at all,
    since a serve's peak-wrist-VELOCITY frame is the downswing (wrist
    already back down by then), not the toss/contact moment -- so serves
    get undeserved fh/bh credit while serve's own score stays capped low.
    Raised the multiplier 2.5 -> 4.5 and added a flat baseline credit for
    ANY positive overhead detection, tuned against the real data below.
    """
    frames_to_check = [peak_lm]
    if window_lms:
        frames_to_check = window_lms + [peak_lm]

    best_overhead = -999
    elbow_elevated = False
    wrist_above_nose = False

    for lm in frames_to_check:
        rw = get_lm(lm, 'right_wrist')
        lw = get_lm(lm, 'left_wrist')
        rs = get_lm(lm, 'right_shoulder')
        ls = get_lm(lm, 'left_shoulder')
        re = get_lm(lm, 'right_elbow')
        nose = get_lm(lm, 'nose')

        if not all(visible(x) for x in [rs, ls]):
            continue

        if visible(rw):
            overhead = rs['y'] - rw['y']
            if overhead > best_overhead:
                best_overhead = overhead
        if visible(lw):
            overhead = ls['y'] - lw['y']
            if overhead > best_overhead:
                best_overhead = overhead

        if visible(re) and re['y'] < rs['y']:
            elbow_elevated = True
        if visible(nose) and visible(rw) and rw['y'] < nose['y'] - 0.05:
            wrist_above_nose = True

    rw_peak = get_lm(peak_lm, 'right_wrist')
    rs_peak = get_lm(peak_lm, 'right_shoulder')
    if not visible(rw_peak) or not visible(rs_peak):
        return 0.3, ['insufficient landmarks at peak']

    score = 0.0
    reasons = []
    if best_overhead > 0:
        score += min(0.7, 0.25 + best_overhead * 4.5)
        reasons.append(f'wrist overhead by {best_overhead:.3f} in window')
    elif best_overhead > -0.05:
        score += 0.2
        reasons.append('wrist near shoulder height')

    if elbow_elevated:
        score += 0.2
        reasons.append('elbow above shoulder')
    if wrist_above_nose:
        score += 0.2
        reasons.append('wrist above nose (full extension)')
    if visible(rw_peak) and visible(rs_peak) and rw_peak['y'] > rs_peak['y']:
        score += 0.1
        reasons.append('wrist below shoulder at peak = downswing contact')

    return min(score, 1.0), reasons


def variant_serve_boosted_overhead_v2(peak_lm, prev_lm, window_lms=None):
    """Candidate 5: same as candidate 3 but with a smaller multiplier/baseline
    (3.2x + 0.12, vs 4.5x + 0.25) -- candidate 3 fixed most serve/fh-bh
    confusion but leaked some genuine forehands into 'serve' as a side
    effect of raising serve's ceiling globally; testing a smaller boost to
    see if it keeps most of the gain with less of that new leak."""
    frames_to_check = [peak_lm]
    if window_lms:
        frames_to_check = window_lms + [peak_lm]

    best_overhead = -999
    elbow_elevated = False
    wrist_above_nose = False
    for lm in frames_to_check:
        rw = get_lm(lm, 'right_wrist')
        lw = get_lm(lm, 'left_wrist')
        rs = get_lm(lm, 'right_shoulder')
        ls = get_lm(lm, 'left_shoulder')
        re = get_lm(lm, 'right_elbow')
        nose = get_lm(lm, 'nose')
        if not all(visible(x) for x in [rs, ls]):
            continue
        if visible(rw):
            overhead = rs['y'] - rw['y']
            if overhead > best_overhead:
                best_overhead = overhead
        if visible(lw):
            overhead = ls['y'] - lw['y']
            if overhead > best_overhead:
                best_overhead = overhead
        if visible(re) and re['y'] < rs['y']:
            elbow_elevated = True
        if visible(nose) and visible(rw) and rw['y'] < nose['y'] - 0.05:
            wrist_above_nose = True

    rw_peak = get_lm(peak_lm, 'right_wrist')
    rs_peak = get_lm(peak_lm, 'right_shoulder')
    if not visible(rw_peak) or not visible(rs_peak):
        return 0.3, ['insufficient landmarks at peak']

    score = 0.0
    reasons = []
    if best_overhead > 0:
        score += min(0.65, 0.12 + best_overhead * 3.2)
        reasons.append(f'wrist overhead by {best_overhead:.3f} in window')
    elif best_overhead > -0.05:
        score += 0.2
        reasons.append('wrist near shoulder height')
    if elbow_elevated:
        score += 0.2
        reasons.append('elbow above shoulder')
    if wrist_above_nose:
        score += 0.2
        reasons.append('wrist above nose (full extension)')
    if visible(rw_peak) and visible(rs_peak) and rw_peak['y'] > rs_peak['y']:
        score += 0.1
        reasons.append('wrist below shoulder at peak = downswing contact')
    return min(score, 1.0), reasons


def main():
    print('Loading cached poses for true-shot amateur examples...')
    examples = load_examples()
    print(f'{len(examples)} examples loaded (forehand/backhand/serve only, skip excluded)\n')

    from extract_clips import score_forehand, score_backhand, score_serve

    print('=== Baseline (current extract_clips.py) ===')
    acc, confusion, n = evaluate(baseline_scorers(), examples)
    print(f'N={n}  accuracy={acc:.1%}')
    print_confusion(confusion)

    print('\n=== Candidate 1: stricter two-handed threshold (0.15 -> 0.09) ===')
    scorers1 = {'forehand': score_forehand, 'backhand': variant_stricter_two_handed, 'serve': score_serve}
    acc1, confusion1, _ = evaluate(scorers1, examples)
    print(f'N={n}  accuracy={acc1:.1%}  (baseline was {acc:.1%})')
    print_confusion(confusion1)

    print('\n=== Candidate 2: + stricter left-wrist-active margin (0.7x -> 0.85x) ===')
    scorers2 = {'forehand': score_forehand, 'backhand': variant_require_both_hand_signals, 'serve': score_serve}
    acc2, confusion2, _ = evaluate(scorers2, examples)
    print(f'N={n}  accuracy={acc2:.1%}  (baseline was {acc:.1%})')
    print_confusion(confusion2)

    print('\n=== Candidate 3: boosted serve overhead credit (2.5x -> 4.5x + baseline) ===')
    scorers3 = {'forehand': score_forehand, 'backhand': score_backhand, 'serve': variant_serve_boosted_overhead}
    acc3, confusion3, _ = evaluate(scorers3, examples)
    print(f'N={n}  accuracy={acc3:.1%}  (baseline was {acc:.1%})')
    print_confusion(confusion3)

    print('\n=== Candidate 4: candidate 1 (backhand) + candidate 3 (serve) combined ===')
    scorers4 = {'forehand': score_forehand, 'backhand': variant_stricter_two_handed, 'serve': variant_serve_boosted_overhead}
    acc4, confusion4, _ = evaluate(scorers4, examples)
    print(f'N={n}  accuracy={acc4:.1%}  (baseline was {acc:.1%})')
    print_confusion(confusion4)

    print('\n=== Candidate 5: candidate 1 (backhand) + smaller serve boost (3.2x + 0.12) ===')
    scorers5 = {'forehand': score_forehand, 'backhand': variant_stricter_two_handed, 'serve': variant_serve_boosted_overhead_v2}
    acc5, confusion5, _ = evaluate(scorers5, examples)
    print(f'N={n}  accuracy={acc5:.1%}  (baseline was {acc:.1%})')
    print_confusion(confusion5)

    print('\n=== Wrist-separation distribution, by true label (diagnostic) ===')
    from extract_clips import get_lm as _get_lm
    for label in ('forehand', 'backhand', 'serve'):
        seps = []
        for ex in examples:
            if ex['label'] != label:
                continue
            rw = _get_lm(ex['peak_lm'], 'right_wrist')
            lw = _get_lm(ex['peak_lm'], 'left_wrist')
            if rw and lw and visible(rw) and visible(lw):
                seps.append(abs(rw['x'] - lw['x']))
        if seps:
            seps.sort()
            print(f'  {label}: n={len(seps)}  min={seps[0]:.3f}  median={seps[len(seps)//2]:.3f}  max={seps[-1]:.3f}')


if __name__ == '__main__':
    main()
