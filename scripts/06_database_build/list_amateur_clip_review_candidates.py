"""
Lists amateur swing-label candidates for the Dev Page's Amateur Clip Review
tool -- a manual re-review pass over data/08_coaching_ai/amateur_swing_labels.json
(the shot-type ground truth for the amateur eval set: calibrate_similarity.py,
redesign_similarity.py, evaluate_amateur_dataset.py). Same free, no-Claude-cost,
one-at-a-time pattern as Pro Clip Review, but simpler -- amateur candidate
clips never need cutting/splitting/contact-time correction, only a shot-type
relabel (data/04_clips/amateur/manifest.json's peak_frame is fixed at ingest
time by extract_amateur_clips.py).

Prompted by roadmap 1b (technique-score rubric): the whole 9-video source set
is fully labeled (248/248) but backhand is a hard ceiling at only 10 real
examples -- Jack wants to re-review the full set by eye in case any were
mislabeled (e.g. a backhand that got called 'skip' or 'forehand').

Usage:
  python list_amateur_clip_review_candidates.py [limit]

Output (stdout): {"candidates": [{id, video_id, swing_id, clip_url, label,
  peak_time_sec}, ...], "progress": {total, reviewed, by_label: {label: count}}}

Reviewed candidates are excluded from `candidates` (same "server-side
filtering means already-reviewed clips don't come back" convention as
list_pro_clip_review_candidates.py) -- 2026-09-11 fix: the tool originally
only persisted the LABEL on each tap, not whether the candidate had been
looked at, so navigating back into the screen re-fetched the same full,
unfiltered 329 and restarted the on-screen counter at 1, even though nothing
was actually lost. amateur_eval reviewed ids live in amateur_swing_labels.json's
top-level `reviewed` list (correct_amateur_clip_label.py adds to it on every
POST, even a same-label confirm); raw_ingest entries use their own per-entry
`manually_reviewed` flag (unchanged, already excluded here too).
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))

from paths import DATA_DIR  # noqa: E402
from clip_urls import to_url, PRO_CLIPS_DIR  # noqa: E402

AMATEUR_CLIPS_DIR = os.path.join(DATA_DIR, '04_clips', 'amateur')
MANIFEST_PATH = os.path.join(AMATEUR_CLIPS_DIR, 'manifest.json')
LABELS_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'amateur_swing_labels.json')

# Older raw-footage-ingest batches (predate manifest.json/
# amateur_swing_labels.json) -- one ingest_report.json per source video,
# shot_type there is an unverified automated-classifier guess, not ground
# truth. "Review-only" stream (roadmap 1b, 2026-09-11): not wired into
# calibrate_similarity.py/evaluate_amateur_dataset.py, which need a matching
# data/03_swing_detection/amateur_<video_id>_swings.json this older batch
# never got -- corrections here just relabel ingest_report.json in place so
# Jack can watch + label by eye first, before deciding whether any are worth
# properly folding into the real eval set.
RAW_INGEST_DIR = os.path.join(DATA_DIR, 'runtime', 'raw_footage_ingest')


def _raw_ingest_candidates():
    """{video_id: [ingest_report entries]} for every ingest_report.json found
    directly under a raw_footage_ingest/<video_id>/ subfolder."""
    out = []
    if not os.path.isdir(RAW_INGEST_DIR):
        return out
    for video_id in sorted(os.listdir(RAW_INGEST_DIR)):
        report_path = os.path.join(RAW_INGEST_DIR, video_id, 'ingest_report.json')
        if not os.path.isfile(report_path):
            continue
        with open(report_path, encoding='utf-8') as f:
            entries = json.load(f)
        for e in entries:
            out.append((video_id, report_path, e))
    return out


def list_candidates(limit=None):
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    labels = {}
    reviewed_ids = set()
    if os.path.exists(LABELS_PATH):
        with open(LABELS_PATH, encoding='utf-8') as f:
            labels_data = json.load(f)
        labels = labels_data.get('labels', {})
        reviewed_ids = set(labels_data.get('reviewed', []))

    candidates = []
    by_label = {}
    reviewed_count = 0
    for e in manifest:
        cid = f'{e["video_id"]}_{e["swing_id"]}'
        label = labels.get(cid)
        by_label[label] = by_label.get(label, 0) + 1
        if cid in reviewed_ids:
            reviewed_count += 1
            continue
        candidates.append({
            'id': cid,
            'video_id': e['video_id'],
            'swing_id': e['swing_id'],
            'clip_url': to_url('/pro-clips', PRO_CLIPS_DIR, e['clip_path']),
            'label': label,
            'peak_time_sec': e.get('peak_time_sec'),
            'source': 'amateur_eval',
        })

    raw_total = 0
    for video_id, _report_path, e in _raw_ingest_candidates():
        raw_total += 1
        label = e.get('shot_type')
        by_label[label] = by_label.get(label, 0) + 1
        if e.get('manually_reviewed'):
            reviewed_count += 1
            continue
        candidates.append({
            'id': f'raw:{video_id}:{e["index"]}',
            'video_id': video_id,
            'swing_id': e['index'],
            'clip_url': to_url('/raw-footage-clips', RAW_INGEST_DIR, e['clip_path']),
            'label': label,
            'peak_time_sec': e.get('peak_time_sec'),
            'source': 'raw_ingest',
            # unverified auto-classifier guess, not ground truth -- surfaced
            # so a low_confidence / near-tied backhand score is visible
            # without having to open ingest_report.json by hand.
            'low_confidence': e.get('low_confidence'),
            'shot_scores': e.get('shot_scores'),
        })

    # Sort non-backhand-first so a re-review pass looking specifically for
    # missed backhands doesn't have to page past already-confirmed ones --
    # 'skip' and 'forehand' are the two labels most likely to hide a missed
    # backhand (a real backhand mistaken for "not a shot" or misclassified).
    order = {'skip': 0, 'forehand': 1, 'serve': 2, 'backhand': 3, None: -1}
    candidates.sort(key=lambda c: (order.get(c['label'], 4), c['video_id'], c['swing_id']))

    if limit:
        candidates = candidates[:int(limit)]

    total = len(manifest) + raw_total
    return {
        'candidates': candidates,
        'progress': {'total': total, 'reviewed': reviewed_count, 'remaining': total - reviewed_count,
                     'by_label': by_label},
    }


def main():
    limit = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(list_candidates(limit)))


if __name__ == '__main__':
    main()
