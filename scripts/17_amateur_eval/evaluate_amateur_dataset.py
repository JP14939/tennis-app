"""
Evaluates the shot-type classifier (scripts/14_shot_classifier/classify_shot.py)
and the shot-contact verifier (scripts/16_shot_verification/verify_shot_contact.py)
against data/08_coaching_ai/amateur_swing_labels.json -- 248 Claude-vision
labels (forehand/backhand/serve/skip) for real swing candidates from 9 real
amateur match videos, already run through pose extraction -> swing detection
-> clip extraction (data/04_clips/amateur/). This data existed already and
was never connected to either system's evaluation -- the classifier was
last checked against only 7 clips (see HANDOVER.md), and the verifier's own
training log has real logged examples but none from this dataset.

'skip' doubles as ground truth for "not a real shot" (the verifier's
question); forehand/backhand/serve double as ground truth for shot type
(the classifier's question) on the subset that IS a real shot.

Zero new Claude API calls -- these labels already exist. Every real
(student prediction, label) pair found here is also backfilled into the
production training logs (shot_classifier_training_log.jsonl /
shot_contact_training_log.jsonl) via each module's own log_example(),
tagged source='amateur_label_backfill' so it's traceable, exactly the same
mechanism 'user_flag' entries already use to feed the trust-gating math.

Checkpointed/resumable (mirrors scripts/16_shot_verification/batch_verify_all.py's
pattern) keyed by "{video_id}_{swing_id}" -- which is exactly the label
dict's own key format, so no separate key-building step is needed.

Usage:
  python evaluate_amateur_dataset.py                 # process + report
  python evaluate_amateur_dataset.py --limit 20       # smoke test
  python evaluate_amateur_dataset.py --report-only    # just re-print the report
  python evaluate_amateur_dataset.py --no-backfill    # process without touching the training logs
"""
import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '08_comparison_engine'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '14_shot_classifier'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '16_shot_verification'))

sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))

from paths import DATA_DIR  # noqa: E402
from compare_swing import extract_user_poses  # noqa: E402
from extract_poses import extract_poses  # noqa: E402
from classify_shot import classify  # noqa: E402
import shot_classifier_training_log as clf_log  # noqa: E402
from verify_shot_contact import verify_swings, filter_verified_swings  # noqa: E402
import shot_contact_training_log as contact_log  # noqa: E402

LABELS_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'amateur_swing_labels.json')
MANIFEST_PATH = os.path.join(DATA_DIR, '04_clips', 'amateur', 'manifest.json')
SWINGS_DIR = os.path.join(DATA_DIR, '03_swing_detection')
OUT_DIR = os.path.join(DATA_DIR, '17_amateur_eval')
RESULTS_PATH = os.path.join(OUT_DIR, 'results.jsonl')
POSES_CACHE_DIR = os.path.join(OUT_DIR, 'poses')

BACKFILL_SOURCE = 'amateur_label_backfill'


def get_verifier_poses(key, clip_path):
    """
    verify_shot_contact.py's cropping step (_frame_bbox in
    scripts/12_video_crop/crop_to_subject.py) expects extract_poses()'s
    landmark shape -- a LIST of {'name','x','y','z','visibility'} dicts --
    not compare_swing.extract_user_poses()'s shape, a dict keyed by
    landmark name. The two are not interchangeable (confirmed by a real
    TypeError during initial testing: iterating a dict yields its string
    keys, and `lm['visibility']` on a string key raises "string indices
    must be integers"). Production keeps these as two separate extractions
    too (scripts/15_batch_analysis/analyze_rallies_parallel.py calls
    extract_user_poses() for classify/compare and a separate
    extract_poses(..., sample_every=3) for verify_swings) -- mirrored here,
    same pattern as batch_verify_all.py's get_poses() cache-to-disk-then-
    read-back approach, since extract_poses() only writes to a file.
    """
    os.makedirs(POSES_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(POSES_CACHE_DIR, f'{key}.json')
    if not os.path.exists(cache_path):
        import contextlib
        with contextlib.redirect_stdout(sys.stderr):
            extract_poses(clip_path, cache_path, sample_every=3)
    with open(cache_path) as f:
        data = json.load(f)
    return data['frames'], data['fps']

_swings_cache = {}


def load_swings(video_id):
    """swing_id -> swing dict, for one video's swings JSON, cached per video_id."""
    if video_id not in _swings_cache:
        path = os.path.join(SWINGS_DIR, f'amateur_{video_id}_swings.json')
        with open(path) as f:
            data = json.load(f)
        _swings_cache[video_id] = {sw['swing_id']: sw for sw in data['swings']}
    return _swings_cache[video_id]


def load_checkpoint():
    if not os.path.exists(RESULTS_PATH):
        return {}
    done = {}
    with open(RESULTS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                done[rec['key']] = rec
            except (json.JSONDecodeError, KeyError):
                continue  # tolerate a truncated last line from a crashed run
    return done


def append_result(rec):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RESULTS_PATH, 'a') as f:
        f.write(json.dumps(rec) + '\n')


def process_example(key, video_id, swing_id, clip_path, peak_frame_source, label, backfill=True):
    """
    peak_frame_source: peak_frame from manifest.json, relative to the
    *source* video -- clips were cut with extract_clip(cap, start_frame,
    end_frame, ...) (scripts/04_clip_extraction/extract_clips.py), so frame
    0 of the clip == start_frame of the source. Clip-relative contact frame
    is therefore just peak_frame_source - start_frame (an integer frame
    count, not re-derived through a time conversion).
    """
    sw_meta = load_swings(video_id).get(swing_id)
    if sw_meta is None:
        return {'key': key, 'video_id': video_id, 'swing_id': swing_id, 'label': label,
                'error': f'swing {swing_id} not found in swings json for {video_id}'}
    start_frame = sw_meta['start_frame']

    frames, fps = extract_user_poses(clip_path)
    clip_peak_frame = peak_frame_source - start_frame
    contact_time_sec = clip_peak_frame / fps

    try:
        clf_result = classify(clip_path, contact_time_sec, frames_fps=(frames, fps))
        student_shot_type, scores, clf_error = clf_result['shot_type'], clf_result['scores'], None
    except Exception as e:
        student_shot_type, scores, clf_error = None, None, str(e)

    try:
        ver_frames, ver_fps = get_verifier_poses(key, clip_path)
        swing = {'peak_frame': clip_peak_frame}
        verify_swings(clip_path, [swing], ver_fps, frames=ver_frames)
        student_is_real = bool(filter_verified_swings([swing]))
        contact_method = swing.get('contact_method')
        contact_confidence = swing.get('contact_confidence')
        ver_error = None
    except Exception as e:
        student_is_real, contact_method, contact_confidence, ver_error = None, None, None, str(e)

    label_is_real = label != 'skip'

    result = {
        'key': key, 'video_id': video_id, 'swing_id': swing_id, 'clip_path': clip_path,
        'label': label, 'label_is_real': label_is_real,
        'student_is_real': student_is_real,
        'contact_method': contact_method, 'contact_confidence': contact_confidence,
        'verifier_error': ver_error,
        'student_shot_type': student_shot_type, 'shot_scores': scores,
        'classifier_error': clf_error,
    }

    if backfill:
        if ver_error is None:
            contact_log.log_example(
                student_pick=student_is_real, teacher_pick=label_is_real,
                agreed=(student_is_real == label_is_real), source=BACKFILL_SOURCE,
                student_meta={'contact_method': contact_method, 'contact_confidence': contact_confidence,
                              'video_id': video_id, 'swing_id': swing_id},
            )
        # Shot type is only meaningful ground truth on real shots -- 'skip'
        # has no true shot type, so it can't be paired evidence here.
        if clf_error is None and label_is_real:
            clf_log.log_example(scores, student_shot_type, label, student_shot_type == label)

    return result


def _wilson_lower_bound(successes, n, z=1.96):
    if n == 0:
        return 0.0
    p_hat = successes / n
    denom = 1 + z * z / n
    center = p_hat + z * z / (2 * n)
    adjustment = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n)
    return (center - adjustment) / denom


def print_report():
    from shot_contact_training_log import bucket_for  # noqa: E402 (local import, only needed for report)

    if not os.path.exists(RESULTS_PATH):
        print('No results yet -- run without --report-only first.')
        return
    with open(RESULTS_PATH) as f:
        records = [json.loads(line) for line in f if line.strip()]

    errored = [r for r in records if 'error' in r and r['error']]
    print(f'\n=== {len(records)} examples processed ({len(errored)} hard errors) ===')

    ver_records = [r for r in records if r.get('student_is_real') is not None]
    tp = sum(1 for r in ver_records if r['label_is_real'] and r['student_is_real'])
    tn = sum(1 for r in ver_records if not r['label_is_real'] and not r['student_is_real'])
    fp = sum(1 for r in ver_records if not r['label_is_real'] and r['student_is_real'])
    fn = sum(1 for r in ver_records if r['label_is_real'] and not r['student_is_real'])
    n = len(ver_records)
    print('\n--- Shot-contact verifier (real shot vs. skip) ---')
    if n:
        acc = (tp + tn) / n
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        print(f'N={n}  accuracy={acc:.1%}  precision={precision:.1%}  recall={recall:.1%}')
        print(f'  TP={tp} TN={tn} FP={fp} FN={fn}')
    else:
        print('N=0')

    by_bucket = defaultdict(list)
    for r in ver_records:
        by_bucket[bucket_for(r.get('contact_method'))].append(r)
    print('\nPer-bucket (mirrors shot_contact_training_log.py\'s own breakdown):')
    for bucket, recs in sorted(by_bucket.items(), key=lambda kv: str(kv[0])):
        correct = sum(1 for r in recs if r['student_is_real'] == r['label_is_real'])
        lb = _wilson_lower_bound(correct, len(recs))
        print(f'  {bucket}: N={len(recs)}  agreement={correct / len(recs):.1%}  (Wilson lower bound {lb:.1%})')

    clf_records = [r for r in records if r.get('label_is_real') and r.get('student_shot_type')]
    print('\n--- Shot-type classifier (only on labeled real shots) ---')
    if clf_records:
        correct = sum(1 for r in clf_records if r['student_shot_type'] == r['label'])
        print(f'N={len(clf_records)}  accuracy={correct / len(clf_records):.1%}')
        confusion = Counter((r['label'], r['student_shot_type']) for r in clf_records)
        for (true, pred), cnt in sorted(confusion.items()):
            flag = '' if true == pred else '  <-- MISCLASSIFIED'
            print(f'  true={true:10s} pred={pred:10s}  n={cnt}{flag}')
        per_class = Counter(r['label'] for r in clf_records)
        print(f'\n  Per-class sample sizes: {dict(per_class)} -- treat backhand (n={per_class.get("backhand", 0)}) as low-confidence')
    else:
        print('N=0')

    print(f'\n--- Trust-gate status after this backfill ---')
    print(f'  shot_classifier should_trust_student(): {clf_log.should_trust_student()}')
    from shot_contact_training_log import should_trust_bucket, ALL_BUCKETS  # noqa: E402
    for b in ALL_BUCKETS:
        print(f'  shot_contact should_trust_bucket({b}): {should_trust_bucket(b)}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None, help='Only process the first N labeled examples')
    parser.add_argument('--report-only', action='store_true', help='Skip processing, just print the report from existing results')
    parser.add_argument('--no-backfill', action='store_true', help='Process without writing to the production training logs')
    args = parser.parse_args()

    if args.report_only:
        print_report()
        return

    with open(LABELS_PATH) as f:
        labels = json.load(f)['labels']
    with open(MANIFEST_PATH) as f:
        manifest_by_key = {f"{m['video_id']}_{m['swing_id']}": m for m in json.load(f)}

    done = load_checkpoint()
    items = list(labels.items())
    if args.limit:
        items = items[:args.limit]

    for i, (key, label) in enumerate(items, 1):
        if key in done:
            continue
        m = manifest_by_key.get(key)
        if m is None:
            print(f'[{i}/{len(items)}] {key}: no manifest entry, skipping', file=sys.stderr)
            continue
        print(f'[{i}/{len(items)}] {key} (label={label})...', file=sys.stderr)
        try:
            result = process_example(
                key, m['video_id'], m['swing_id'], m['clip_path'], m['peak_frame'], label,
                backfill=not args.no_backfill,
            )
        except Exception as e:
            result = {'key': key, 'video_id': m['video_id'], 'swing_id': m['swing_id'], 'label': label, 'error': str(e)}
            print(f'  ERROR: {e}', file=sys.stderr)
        append_result(result)

    print_report()


if __name__ == '__main__':
    main()
