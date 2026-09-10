"""
One-time enrichment pass: run racket+body tracking (track_racket_in_clip.py)
across every pro_database.json entry's clip, storing a normalised average
racket-handle-to-hip-midpoint distance as entry['racket_body_distance'].
Entries where the racket is never confidently detected keep this field null
rather than a fabricated number -- the body-rotation phase falls back to
rotation-only scoring for those matches (see phase_breakdown.py).

Backs up pro_database.json first, same precedent as
pro_database_backup_pre_elevation_enrichment.json earlier this session.
"""
import json
import os
import shutil
import sys
import time

FORCE = '--force' in sys.argv  # recompute entries that already have the field

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '07_ball_racket_tracking'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from paths import DATA_DIR  # noqa: E402
from track_racket_in_clip import track_racket_body, avg_racket_body_distance, racket_body_features  # noqa: E402
from infer_angle import create_landmarker  # noqa: E402

DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
BACKUP_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database_backup_pre_racket_body_enrichment.json')
# clip_path is stored RELATIVE to data/04_clips (see relative_clip_path() in
# build_pro_database.py) -- resolve it the same way compare_swing.compare() does.
CLIPS_DIR = os.path.join(DATA_DIR, '04_clips')


def main():
    if not os.path.exists(BACKUP_PATH):
        shutil.copy(DB_PATH, BACKUP_PATH)
        print(f'Backed up to {BACKUP_PATH}')

    with open(DB_PATH) as f:
        db = json.load(f)

    entries = db['entries']
    landmarker = create_landmarker()

    n_ok = n_null = n_missing_clip = n_skip = 0
    start = time.time()
    for i, entry in enumerate(entries):
        # Resume a partial run: an entry that already carries the key was done
        # on a previous pass (this is idempotent, --force to redo).
        if 'racket_body_distance' in entry and not FORCE:
            n_skip += 1
            continue

        clip_rel = entry.get('clip_path')
        clip_path = os.path.join(CLIPS_DIR, clip_rel) if clip_rel else None
        if not clip_path or not os.path.exists(clip_path):
            entry['racket_body_distance'] = None
            n_missing_clip += 1
            continue

        feats = None
        try:
            frame_results = track_racket_body(clip_path, landmarker=landmarker, sample_every=4)
            feats = racket_body_features(frame_results)
        except Exception as e:
            print(f'  [{i}] {entry["id"]} error: {e}', file=sys.stderr)

        dist = feats['mean'] if feats else None
        # keep the scalar phase_breakdown.score_body_rotation() already reads,
        # plus the richer summary the technique-score rubric wants
        entry['racket_body_distance'] = dist
        entry['racket_body_features'] = feats
        if dist is None:
            n_null += 1
        else:
            n_ok += 1

        if (i + 1) % 20 == 0:
            done = i + 1 - n_skip
            elapsed = time.time() - start
            rate = done / elapsed if elapsed else 0
            eta_min = (len(entries) - i - 1) / rate / 60 if rate else 0
            print(f'  {i+1}/{len(entries)} | ok={n_ok} null={n_null} missing_clip={n_missing_clip} '
                  f'skip={n_skip} | {rate:.2f}/s | ETA {eta_min:.1f}min', flush=True)
        # Flush to disk periodically so a crash / kill keeps progress -- the
        # per-entry resume check above picks up from here on the next run.
        if (i + 1) % 50 == 0:
            with open(DB_PATH, 'w') as f:
                json.dump(db, f)

    landmarker.close()

    with open(DB_PATH, 'w') as f:
        json.dump(db, f)

    total = len(entries)
    print(f'\nDone. {n_ok}/{total} entries got a real racket_body_distance '
          f'({100*n_ok/total:.1f}%), {n_null} null (racket/pose not confidently detected), '
          f'{n_missing_clip} missing clip file, {n_skip} already done (resumed).')


if __name__ == '__main__':
    main()
