"""
Feature-capture pass for vertical camera elevation, run across the full
pro_database.json (631 entries) plus today's 2 known-elevated real videos.

Does NOT touch trajectory extraction or DTW data -- loads the existing
pro_database.json, re-runs infer_camera_angle() per entry's clip_path, and
writes a small elevation_features dict (post height, ankle gap, and several
other raw signals infer_camera_angle() already computes) onto each entry in
place. This is feature capture only -- see calibrate_elevation_outlier.py for
the actual multi-feature outlier-detection calibration step that decides
whether any of this is usable (a single-feature version of this was tried
first and did not separate known-good from known-bad footage).

Also writes data/runtime/known_elevated_features.json so the calibration
script doesn't need to re-run pose extraction on the 2 known-elevated videos.

Usage:
  python enrich_pro_elevation.py
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import infer_camera_angle, create_landmarker

DB_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'
KNOWN_ELEVATED_VIDEOS = [
    r'C:\Users\jackp\tennis_app\data\01_source_videos\testing\mark_vs_silas_trimmed.mp4',
    r'C:\Users\jackp\tennis_app\data\01_source_videos\testing\nicolas_vs_florian_trimmed.mp4',
]


FEATURE_KEYS = ['post_height_frac', 'elevation_gap', 'net_apparent_ratio', 'net_y', 'player_net_offset', 'player_vis']


def _extract_features(debug):
    if not isinstance(debug, dict):
        return {k: None for k in FEATURE_KEYS}
    net = debug.get('net') or {}
    return {
        'post_height_frac':  debug.get('post_height_frac'),
        'elevation_gap':     debug.get('elevation_gap'),
        'net_apparent_ratio': debug.get('net_apparent_ratio'),
        'net_y':              net.get('y'),
        'player_net_offset':  debug.get('player_net_offset'),
        'player_vis':         debug.get('player_vis'),
    }


def enrich_database(landmarker):
    with open(DB_PATH) as f:
        db = json.load(f)

    coverage = {k: 0 for k in FEATURE_KEYS}
    neither = 0

    for i, entry in enumerate(db['entries']):
        clip_path = entry.get('clip_path')
        features = {k: None for k in FEATURE_KEYS}
        confidence = None
        if clip_path and os.path.exists(clip_path):
            try:
                _, conf, debug = infer_camera_angle(clip_path, landmarker=landmarker)
                features = _extract_features(debug)
                confidence = conf
            except Exception:
                pass

        entry['elevation_features'] = features
        entry['elevation_confidence'] = confidence

        any_present = False
        for k in FEATURE_KEYS:
            if features[k] is not None:
                coverage[k] += 1
                any_present = True
        if not any_present:
            neither += 1

        if (i + 1) % 100 == 0:
            print(f'  [{i+1}/{len(db["entries"])}] coverage so far: {coverage}')

    with open(DB_PATH, 'w') as f:
        json.dump(db, f)

    print(f'\nDone. {len(db["entries"])} entries enriched.')
    for k in FEATURE_KEYS:
        print(f'  {k}: {coverage[k]}/{len(db["entries"])} ({100*coverage[k]//len(db["entries"])}%)')
    print(f'  no features at all: {neither}/{len(db["entries"])}')

    return db['entries']


def measure_known_elevated(landmarker):
    results = []
    for video in KNOWN_ELEVATED_VIDEOS:
        if not os.path.exists(video):
            print(f'  Skipping (not found): {video}')
            continue
        _, conf, debug = infer_camera_angle(video, landmarker=landmarker)
        features = _extract_features(debug)
        print(f'  {os.path.basename(video)}: {features} conf={conf}')
        results.append({'video': os.path.basename(video), 'features': features, 'confidence': conf})
    return results


KNOWN_ELEVATED_OUT = r'C:\Users\jackp\tennis_app\data\runtime\known_elevated_features.json'


if __name__ == '__main__':
    print('Creating pose landmarker...')
    lm = create_landmarker()

    print('\n=== Enriching pro_database.json (631 entries) ===')
    entries = enrich_database(lm)

    print('\n=== Measuring known-elevated real videos ===')
    known_elevated = measure_known_elevated(lm)

    os.makedirs(os.path.dirname(KNOWN_ELEVATED_OUT), exist_ok=True)
    with open(KNOWN_ELEVATED_OUT, 'w') as f:
        json.dump(known_elevated, f, indent=2)
    print(f'\nSaved known-elevated features to {KNOWN_ELEVATED_OUT}')
    print('Run calibrate_elevation_outlier.py next for the actual calibration step.')
