"""
Ingest court-level PRACTICE / points footage into the pro-match database, one
detected swing at a time.

The curated `build_pro_database.py` pipeline assigns ONE shot type per whole
source video (a slow-mo forehand compilation, etc.). Practice / points footage
carries forehands, backhands and serves mixed together (and sometimes two
players), so it needs a per-swing path: detect every swing, verify each is a
real strike, classify each one's shot type, and build a pro-DB entry per
survivor.

MVP scope (2026-09-02): SINGLE-PERSON only -- no multi-person pose work.
MediaPipe picks one player per frame; the gates below drop most far-player and
mid-rally-ambiguous swings, and Jack's Pro Clip Review pass is the real quality
backstop. New entries go live in the match pool immediately (unreviewed), same
as the existing never-reviewed entries.

NO Claude by default (Jack's call 2026-09-02): the "is this a real strike?"
filter is the free geometric one (filter_verified_swings -- keeps a swing only
if find_contact_frame found real racket/ball evidence, drops bare
wrist-velocity peaks), and the shot type is the free rule-based classify().
Pass --use-claude to gate each candidate through the Claude teacher instead
(cleaner input to review, ~$0.5/video).

Reuses, unchanged:
  extract_poses, compute_wrist_velocity/find_swing_peaks              (02, 03)
  verify_swings + filter_verified_swings ("real strike?" geometric)  (16)
  classify() rule scorers / get_verified_shot_type (--use-claude)    (14)
  detect_rallies.refine_contact_times (audio "pock" contact frame)   (11)
  trajectory_extraction.extract_swing_trajectory / build_swing_overlay (06)
  infer_camera_angle / infer_angle_from_source                       (05)
  extract_clip                                                       (04)

Appends straight into data/06_pro_database/pro_database.json (+ the overlay
file), skipping entry ids already present -- resumable. Also writes a
per-swing sidecar data/03_swing_detection/<name>_swings_validated.json
carrying shot_type / contact_method / verify_source / classifier_source so
the new entries are heavily filterable later.

Usage:
  python ingest_practice_footage.py practice_02 [practice_03 ...]
  python ingest_practice_footage.py --all
  python ingest_practice_footage.py practice_02 --limit 20   # first 20 swings (a yield probe)
  python ingest_practice_footage.py practice_02 --use-claude  # gate via Claude teacher
"""
import argparse
import contextlib
import json
import os
import sys
import time
import traceback

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
for sub in ('00_utils', '02_pose_extraction', '03_swing_detection', '04_clip_extraction',
            '05_angle_detection', '07_ball_racket_tracking', '11_highlight_clipping',
            '14_shot_classifier', '16_shot_verification'):
    p = os.path.join(SCRIPTS_DIR, sub)
    if p not in sys.path:
        sys.path.insert(0, p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from paths import DATA_DIR  # noqa: E402
from clip_urls import PRO_CLIPS_DIR  # noqa: E402
from extract_poses import extract_poses  # noqa: E402
from detect_swings import (  # noqa: E402
    compute_wrist_velocity, find_swing_peaks, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC,
)
from extract_clips import extract_clip  # noqa: E402
from video_io import reencode_to_h264  # noqa: E402
from infer_angle import infer_camera_angle, infer_angle_from_source, create_landmarker  # noqa: E402
from verify_shot_contact import verify_swings, filter_verified_swings  # noqa: E402
from verify_shot_contact_verified import get_verified_shot_contact  # noqa: E402
from classify_shot import classify  # noqa: E402
from classify_shot_verified import get_verified_shot_type  # noqa: E402
from detect_rallies import refine_contact_times, _as_classify_frames  # noqa: E402
from trajectory_extraction import build_pose_index, extract_swing_trajectory, build_swing_overlay  # noqa: E402

SRC_DIR = os.path.join(DATA_DIR, '01_source_videos', 'practice')
POSES_DIR = os.path.join(DATA_DIR, '02_pose_extraction')
SWINGS_DIR = os.path.join(DATA_DIR, '03_swing_detection')
CLIPS_DIR = os.path.join(PRO_CLIPS_DIR, 'practice')
PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
OVERLAY_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'overlay_trajectories.json')
CHECKPOINT_PATH = os.path.join(DATA_DIR, '06_pro_database', '.practice_ingest_checkpoint.jsonl')

# Per-video swing-id block. > 100000 is the sentinel for "this entry stores its
# own source_video / poses_path / clip_start_frame and is NOT resolvable via
# source_footage_lookup's swing_id // 1000 scheme".
ID_BLOCK = 100000
PRE_PAD_SEC = 1.0
POST_PAD_SEC = 2.0
VALID_SHOT_TYPES = {'forehand', 'backhand', 'serve'}


def _video_index(name):
    """practice_02 -> 2."""
    digits = ''.join(c for c in name if c.isdigit())
    return int(digits) if digits else 0


def _load_checkpoint():
    done = {}
    if not os.path.exists(CHECKPOINT_PATH):
        return done
    with open(CHECKPOINT_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                done[r['id']] = r
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def _append_checkpoint(rec):
    os.makedirs(os.path.dirname(CHECKPOINT_PATH), exist_ok=True)
    with open(CHECKPOINT_PATH, 'a') as f:
        f.write(json.dumps(rec) + '\n')


def _get_poses(video_path, poses_path):
    if not os.path.exists(poses_path):
        print(f'  extracting poses (slow) -> {poses_path}', file=sys.stderr)
        os.makedirs(os.path.dirname(poses_path), exist_ok=True)
        with contextlib.redirect_stdout(sys.stderr):
            extract_poses(video_path, poses_path, sample_every=3)
    with open(poses_path) as f:
        return json.load(f)


def _passes_quality_gate(sw, trajectory):
    """The single-person backstop applied up front so the review queue stays
    sane. Drops far-player / ambiguous / evidence-free swings."""
    if trajectory is None:              # < MIN_TRAJECTORY_POINTS or shoulders unseen
        return False, 'sparse_trajectory'
    method = str(sw.get('contact_method') or '')
    if method == 'wrist_velocity_fallback' and 'contact_time_sec_audio' not in sw \
            and sw.get('contact_confidence', 0) <= 0.3:
        return False, 'no_contact_evidence'
    return True, None


def _real_strike_and_type(video_path, sw, fps, classify_frames, use_claude):
    """Returns (is_real_strike, shot_type_or_None, verify_source, classifier_source).
    Default: free geometric strike filter + rule classifier. use_claude: the
    Claude teacher for both."""
    contact_t = sw.get('contact_time_sec', sw['peak_time'])
    if use_claude:
        is_real, vmeta = get_verified_shot_contact(video_path, sw, fps, use_verifier=True)
        if not is_real:
            return False, None, vmeta.get('source'), None
        shot_type, csrc = vmeta.get('shot_type'), vmeta.get('source')
        if shot_type not in VALID_SHOT_TYPES:
            shot_type, cmeta = get_verified_shot_type(
                video_path, contact_t, use_verifier=True, frames_fps=(classify_frames, fps))
            csrc = cmeta.get('source')
        return True, shot_type, vmeta.get('source'), csrc
    # free path: filter_verified_swings keeps a swing only if find_contact_frame
    # found real racket/ball evidence (drops bare wrist-velocity peaks).
    if not filter_verified_swings([sw]):
        return False, None, 'geometric', None
    try:
        res = classify(video_path, contact_t, frames_fps=(classify_frames, fps))
        return True, res.get('shot_type'), 'geometric', 'rule'
    except Exception:  # noqa: BLE001
        return True, None, 'geometric', 'rule'


def process_video(name, db_ids, checkpoint, limit=None, use_claude=False):
    video_path = os.path.join(SRC_DIR, f'{name}.mp4')
    if not os.path.exists(video_path):
        print(f'  MISSING: {video_path}', file=sys.stderr)
        return [], {}, []

    vidx = _video_index(name)
    poses_path = os.path.join(POSES_DIR, f'{name}_poses.json')
    pose_data = _get_poses(video_path, poses_path)
    fps = pose_data['fps']
    frames = pose_data['frames']
    pose_index = build_pose_index(frames)
    total_frames = pose_data.get('total_frames') or int(round(frames[-1]['frame'])) + 1

    velocities = compute_wrist_velocity(frames)
    raw = find_swing_peaks(velocities, frames, fps, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC)
    print(f'  {name}: {len(raw)} raw swing peaks', file=sys.stderr)
    if limit:
        raw = raw[:limit]

    # racket/ball contact evidence + audio-onset contact frame (mutates raw)
    try:
        verify_swings(video_path, raw, fps, frames=frames)
    except Exception as e:  # noqa: BLE001
        print(f'  verify_swings failed ({e}) -- continuing with wrist peaks', file=sys.stderr)
    try:
        refine_contact_times(video_path, raw, fps)
        for sw in raw:
            if sw.get('contact_method_audio'):
                sw['contact_time_sec_audio'] = sw['contact_time_sec']
    except Exception as e:  # noqa: BLE001
        print(f'  refine_contact_times failed ({e})', file=sys.stderr)

    classify_frames = _as_classify_frames(frames)
    landmarker = create_landmarker()
    os.makedirs(CLIPS_DIR, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')

    entries, overlays, sidecar = [], {}, []
    tally = {'not_real_shot': 0, 'bad_shot_type': 0, 'quality_gate': 0,
             'clip_failed': 0, 'appended': 0, 'already_done': 0}

    for i, sw in enumerate(raw, 1):
        gid = vidx * ID_BLOCK + i
        eid = f'practice_{gid}'
        if eid in db_ids or eid in checkpoint:
            tally['already_done'] += 1
            continue

        rec = {'id': eid, 'video': name, 'swing_index': i, 'peak_frame': sw['peak_frame']}
        try:
            is_real, shot_type, verify_source, class_source = _real_strike_and_type(
                video_path, sw, fps, classify_frames, use_claude)
            if not is_real:
                tally['not_real_shot'] += 1
                rec['result'] = 'not_real_shot'
                _append_checkpoint(rec)
                continue
            if shot_type not in VALID_SHOT_TYPES:
                tally['bad_shot_type'] += 1
                rec['result'] = f'bad_shot_type:{shot_type}'
                _append_checkpoint(rec)
                continue

            # Best contact-frame anchor available: audio onset (if confident) >
            # racket/ball find_contact_frame guess (~3-4f off) > wrist peak
            # (~13f late). Jack fine-tunes in review either way.
            contact_frame = int(sw.get('contact_frame') or sw.get('contact_frame_guess') or sw['peak_frame'])
            trajectory = extract_swing_trajectory({'peak_frame': contact_frame}, pose_index, fps)
            ok, why = _passes_quality_gate(sw, trajectory)
            if not ok:
                tally['quality_gate'] += 1
                rec['result'] = f'quality_gate:{why}'
                _append_checkpoint(rec)
                continue

            clip_start_frame = max(0, int(sw['peak_time'] * fps - PRE_PAD_SEC * fps))
            end_frame = min(total_frames - 1, int(sw['peak_time'] * fps + POST_PAD_SEC * fps))
            clip_rel = f'practice/{name}_swing_{gid}_{shot_type}.mp4'
            clip_abs = os.path.join(PRO_CLIPS_DIR, clip_rel)
            try:
                extract_clip(cap, clip_start_frame, end_frame, clip_abs, fps, fourcc)
                # extract_clip writes mp4v (MPEG-4 Part 2) -- unplayable in a
                # browser, so the Pro Clip Review tool can't show it. Same
                # extract_clip + reencode_to_h264 pattern every other clip path
                # in the pipeline uses (detect_rallies.py, crop_to_subject.py,
                # ingest_raw_footage_to_history.py).
                reencode_to_h264(clip_abs)
            except Exception as e:  # noqa: BLE001
                tally['clip_failed'] += 1
                rec['result'] = f'clip_failed:{e}'
                _append_checkpoint(rec)
                continue

            camera_angle = angle_conf = None
            try:
                a, c, _ = infer_camera_angle(clip_abs, landmarker=landmarker)
                if a is None:
                    a, c, _ = infer_angle_from_source(video_path, sw['peak_time'], landmarker=landmarker)
                if a is not None:
                    camera_angle, angle_conf = a, round(c, 3)
            except Exception:  # noqa: BLE001
                pass

            overlay = build_swing_overlay(pose_index, fps, contact_frame, clip_start_frame)
            entry = {
                'id': eid,
                'shot_type': shot_type,
                'swing_id': gid,
                'confidence': round(float(sw.get('contact_confidence') or 0.5), 3),
                'peak_time': round(sw['peak_time'], 3),
                'clip_contact_time_sec': round((contact_frame - clip_start_frame) / fps, 3),
                'clip_path': clip_rel,
                'camera_angle': camera_angle,
                'angle_confidence': angle_conf,
                'trajectory': trajectory,
                'source_video': f'practice/{name}.mp4',
                'poses_path': os.path.relpath(poses_path, DATA_DIR).replace('\\', '/'),
                'clip_start_frame': clip_start_frame,
                'ingest': 'practice_mvp',
                'contact_method': sw.get('contact_method'),
                'verify_source': verify_source,
                'classifier_source': class_source,
            }
            entries.append(entry)
            overlays[eid] = overlay
            sidecar.append({
                'swing_id': gid, 'swing_index': i, 'shot_type': shot_type,
                'peak_frame': sw['peak_frame'], 'contact_frame': contact_frame,
                'contact_method': sw.get('contact_method'),
                'contact_confidence': sw.get('contact_confidence'),
                'verify_source': verify_source, 'classifier_source': class_source,
                'clip_path': clip_rel, 'camera_angle': camera_angle,
            })
            tally['appended'] += 1
            rec['result'] = 'appended'
            rec['shot_type'] = shot_type
            _append_checkpoint(rec)
        except Exception as e:  # noqa: BLE001
            print(f'  swing {i}: ERROR {e}\n{traceback.format_exc()}', file=sys.stderr)
            rec['result'] = f'error:{type(e).__name__}'
            _append_checkpoint(rec)

        if i % 20 == 0:
            print(f'  [{i}/{len(raw)}] {dict(tally)}', file=sys.stderr)

    cap.release()
    landmarker.close()
    print(f'\n  {name} done: {dict(tally)}', file=sys.stderr)
    return entries, overlays, sidecar


def _merge_into_db(entries, overlays):
    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    existing = {e['id'] for e in db['entries']}
    new = [e for e in entries if e['id'] not in existing]
    if not new:
        print('  no new entries to merge', file=sys.stderr)
        return 0
    ts = time.strftime('%Y%m%d_%H%M%S')
    with open(PRO_DB_PATH) as f, open(
            os.path.join(os.path.dirname(PRO_DB_PATH), f'pro_database_backup_pre_practice_{ts}.json'), 'w') as bf:
        bf.write(f.read())
    db['entries'].extend(new)
    db['total'] = len(db['entries'])
    shots = {'forehand': 0, 'backhand': 0, 'serve': 0}
    for e in db['entries']:
        if e['shot_type'] in shots:
            shots[e['shot_type']] += 1
    db['shots'] = shots
    with open(PRO_DB_PATH, 'w') as f:
        json.dump(db, f)

    if os.path.exists(OVERLAY_DB_PATH):
        try:
            with open(OVERLAY_DB_PATH) as f:
                ov = json.load(f)
        except json.JSONDecodeError:
            ov = None
        if ov is not None:
            ov.update({k: v for k, v in overlays.items() if k not in ov})
            with open(OVERLAY_DB_PATH, 'w') as f:
                json.dump(ov, f)
    print(f'  merged {len(new)} new entries -> total {db["total"]}  shots {shots}', file=sys.stderr)
    return len(new)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('videos', nargs='*', help='practice_02 practice_03 ... (basename, no .mp4)')
    ap.add_argument('--all', action='store_true', help='every practice_*.mp4 in the source dir')
    ap.add_argument('--limit', type=int, help='only the first N detected swings per video (yield probe)')
    ap.add_argument('--use-claude', action='store_true',
                    help='gate each candidate through the Claude teacher (real-strike + shot type) '
                         'instead of the free geometric filter + rule classifier')
    args = ap.parse_args(argv)

    names = args.videos
    if args.all:
        names = sorted(os.path.splitext(f)[0] for f in os.listdir(SRC_DIR) if f.endswith('.mp4'))
    if not names:
        ap.error('give one or more video basenames, or --all')

    with open(PRO_DB_PATH) as f:
        db_ids = {e['id'] for e in json.load(f)['entries']}
    checkpoint = _load_checkpoint()

    grand = {}
    for name in names:
        entries, overlays, sidecar = process_video(
            name, db_ids, checkpoint, limit=args.limit, use_claude=args.use_claude)
        if entries:
            _merge_into_db(entries, overlays)
            db_ids.update(e['id'] for e in entries)
            sc_path = os.path.join(SWINGS_DIR, f'{name}_swings_validated.json')
            with open(sc_path, 'w') as f:
                json.dump({'video': f'practice/{name}.mp4', 'ingest': 'practice_mvp',
                           'swings': sidecar}, f, indent=1)
            print(f'  sidecar -> {sc_path}', file=sys.stderr)
        grand[name] = len(entries)

    print('\n=== ingest summary ===')
    for name, n in grand.items():
        print(f'  {name}: {n} entries appended')
    print('\nNext: enrich_view_direction.py, then review in the Dev Pro Clip Review tool.')


if __name__ == '__main__':
    main()
