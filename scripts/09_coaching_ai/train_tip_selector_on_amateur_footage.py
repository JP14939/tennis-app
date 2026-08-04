"""
Feed real amateur swings (visually labeled via make_amateur_contact_sheets.py)
through the teacher-student tip-selector loop for the first time ever with
real, non-synthetic deviation data.

For each labeled amateur swing:
  1. Build its trajectory from the source video's full-video pose data,
     reusing build_pro_database.extract_swing_trajectory() directly (same
     function used to build the pro database itself -- same normalisation,
     same windowing).
  2. Find its best-matching pro entry for that shot_type via the same
     DTW-distance + optional angle-filter logic compare_swing.compare()
     uses (inlined here so the raw pro trajectory is available directly).
  3. Call select_coaching_tips.get_coaching_tips() -- the real
     teacher-student call, which scores issues, gets the student's pick,
     calls the Claude verifier, and logs the example.

Never touches pro_database.json or data/04_clips/<shot_type>/ -- amateur
clips are the user side of comparisons only.
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '06_database_build'))

from infer_angle import infer_camera_angle
from build_pro_database import build_pose_index, extract_swing_trajectory, KEY_LANDMARKS
from trajectory_compare import dtw_distance
from tip_selector import score_issues
from select_coaching_tips import get_coaching_tips
from tip_training_log import agreement_rate, read_log

# A real technique fault doesn't put a landmark multiple shoulder-widths from
# where it should be -- deviations past this are far more likely pose-tracking
# noise (amateur rally footage runs 45-88% pose-detection vs. ~100% for the
# curated pro clips, auto-detected contact points instead of user-marked ones,
# and single-person tracking in busy multi-player frames) than a genuine
# fault. Skip the whole example rather than let it inflate the training log
# with an "obviously broken" case that trivially agrees with the student.
MAX_PLAUSIBLE_DEVIATION = 1.5

LABELS_PATH = r'C:\Users\jackp\tennis_app\data\08_coaching_ai\amateur_swing_labels.json'
MANIFEST_PATH = r'C:\Users\jackp\tennis_app\data\04_clips\amateur\manifest.json'
POSES_DIR = r'C:\Users\jackp\tennis_app\data\02_pose_extraction'
SWINGS_DIR = r'C:\Users\jackp\tennis_app\data\03_swing_detection'
DB_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'
ANGLE_WINDOW = 20

# Tracks which individual swings (not whole videos -- later runs add more
# swings from the same videos) have already been run through this script, so
# re-running doesn't call the verifier again on the same example and
# double-count it in tip_training_log.jsonl.
PROCESSED_PATH = r'C:\Users\jackp\tennis_app\data\08_coaching_ai\amateur_swings_processed.json'


def find_best_pro_match(user_trajectory, shot_type, user_angle, db_entries):
    candidates = [e for e in db_entries if e['shot_type'] == shot_type]
    if user_angle is not None:
        angle_filtered = [c for c in candidates
                           if c.get('camera_angle') is not None
                           and abs(c['camera_angle'] - user_angle) <= ANGLE_WINDOW]
        if len(angle_filtered) >= 5:
            candidates = angle_filtered

    best_entry, best_dist = None, float('inf')
    for entry in candidates:
        dist = dtw_distance(user_trajectory, entry['trajectory'], KEY_LANDMARKS)
        if dist < best_dist:
            best_dist, best_entry = dist, entry
    return best_entry, best_dist


def main():
    with open(LABELS_PATH, encoding='utf-8') as f:
        labels = json.load(f)['labels']
    with open(MANIFEST_PATH) as f:
        manifest = {f'{m["video_id"]}_{m["swing_id"]}': m for m in json.load(f)}
    with open(DB_PATH) as f:
        db_entries = json.load(f)['entries']

    processed = set()
    if os.path.exists(PROCESSED_PATH):
        with open(PROCESSED_PATH) as f:
            processed = set(json.load(f))

    usable = [(cell_id, shot_type) for cell_id, shot_type in labels.items()
              if shot_type != 'skip' and cell_id not in processed]
    print(f'{len(usable)} labeled amateur swings to process (of {len(labels)} candidates, '
          f'{len(processed)} already processed in earlier runs)\n')

    pose_index_cache = {}
    n_ok = n_fail = 0

    for i, (cell_id, shot_type) in enumerate(usable, 1):
        processed.add(cell_id)

        entry = manifest.get(cell_id)
        if entry is None:
            print(f'[{i}/{len(usable)}] {cell_id}: no manifest entry — skipping')
            n_fail += 1
            continue

        video_id = entry['video_id']
        if video_id not in pose_index_cache:
            with open(os.path.join(POSES_DIR, f'amateur_{video_id}_poses.json')) as f:
                pose_data = json.load(f)
            pose_index_cache[video_id] = (build_pose_index(pose_data['frames']), pose_data['fps'])
        pose_index, fps = pose_index_cache[video_id]

        swing = {'peak_frame': entry['peak_frame']}
        user_trajectory = extract_swing_trajectory(swing, pose_index, fps)
        if user_trajectory is None:
            print(f'[{i}/{len(usable)}] {cell_id} ({shot_type}): too few usable pose frames — skipping')
            n_fail += 1
            continue

        user_angle, _, _ = infer_camera_angle(entry['clip_path'])

        best_entry, best_dist = find_best_pro_match(user_trajectory, shot_type, user_angle, db_entries)
        if best_entry is None:
            print(f'[{i}/{len(usable)}] {cell_id} ({shot_type}): no pro candidates — skipping')
            n_fail += 1
            continue

        scored = score_issues(user_trajectory, best_entry['trajectory'], shot_type)
        worst = max((s['magnitude'] for s in scored), default=0.0)
        if worst > MAX_PLAUSIBLE_DEVIATION:
            print(f'[{i}/{len(usable)}] {cell_id} ({shot_type}): implausible deviation '
                  f'({worst:.2f} > {MAX_PLAUSIBLE_DEVIATION}) — likely tracking noise, skipping')
            n_fail += 1
            continue

        print(f'[{i}/{len(usable)}] {cell_id} ({shot_type}) vs {best_entry["id"]} (dist={best_dist:.3f})...', flush=True)
        try:
            tips, meta = get_coaching_tips(user_trajectory, best_entry['trajectory'], shot_type)
        except Exception as e:
            print(f'    FAILED: {e}')
            n_fail += 1
            continue

        n_ok += 1
        rate = agreement_rate()
        print(f'    source={meta["source"]} verified={meta["verified"]}'
              + (f' agreed={meta.get("agreed_with_student")}' if meta.get('verified') else '')
              + f' | running agreement rate: {rate if rate is not None else "n/a"}')

    with open(PROCESSED_PATH, 'w') as f:
        json.dump(sorted(processed), f, indent=2)

    print(f'\nDone. {n_ok} examples processed, {n_fail} skipped.')
    total_logged = len(read_log())
    print(f'Total examples now logged in tip_training_log.jsonl: {total_logged}')
    print(f'Overall agreement rate: {agreement_rate()}')


if __name__ == '__main__':
    main()
