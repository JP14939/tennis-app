"""
One-off/reusable ingestion tool: given a raw, unedited practice video (many
swings back to back, not pre-clipped), finds every real swing in it the same
way list_swing_candidates.py does for the Dev Page's Swing Review tool, cuts
each one out as its own short clip, and pushes each through the exact same
two-step flow the app itself uses for a normal user upload:

  1. POST /api/analyse  (multipart video + shotType [+ contactTime]) --
     runs pro_matcher.py, returns the DTW comparison result.
  2. POST /api/history  (that result JSON) -- actually saves it as a real
     analysis row tied to the account, same as the app does after a normal
     single-swing upload.

Needs a real running backend (this hits it over HTTP, not by calling the
Python pipeline modules directly, so the result is byte-for-byte identical
to what a real upload through the app would produce -- including the
cropped clip persistence, pro-clip matching, etc.) and a JWT for the target
account.

Usage:
  python ingest_raw_footage_to_history.py <video_path> --token <jwt> \
      [--api-base http://localhost:5000] [--out-dir <clip staging dir>] \
      [--dry-run]
"""
import argparse
import json
import os
import sys
import time

import cv2
import requests

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '00_utils'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '02_pose_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '03_swing_detection'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '04_clip_extraction'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '14_shot_classifier'))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '16_shot_verification'))

from paths import DATA_DIR  # noqa: E402
from extract_poses import extract_poses  # noqa: E402
from detect_swings import compute_wrist_velocity, find_swing_peaks, SHOT_WINDOWS, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC  # noqa: E402
from extract_clips import extract_clip  # noqa: E402
from verify_shot_contact import verify_swings, filter_verified_swings  # noqa: E402
from classify_shot import classify  # noqa: E402
from video_io import reencode_to_h264  # noqa: E402

STAGING_DIR = os.path.join(DATA_DIR, 'runtime', 'raw_footage_ingest')
ANALYSE_TIMEOUT_S = 130  # backend's own ANALYSIS_TIMEOUT_MS is 2min -- give a small margin

# Generous fixed window used to cut every candidate clip, regardless of shot
# type -- the largest of detect_swings.SHOT_WINDOWS's three (serve's 1.8/2.0)
# so nothing is ever under-padded. classify_shot.classify() is then run on
# THIS already-cut small clip (see the note below on why), not the raw
# video, so a little extra pre/post-roll on a forehand/backhand costs
# nothing -- compare_swing.py aligns on contactTime either way, same as
# ContactMarkingScreen.js's user-submitted clips already do.
CLIP_PRE_SEC, CLIP_POST_SEC = max(w[0] for w in SHOT_WINDOWS.values()), max(w[1] for w in SHOT_WINDOWS.values())


def find_swings(video_path, sample_every):
    poses_cache = os.path.join(STAGING_DIR, 'poses', os.path.basename(video_path) + '.json')
    os.makedirs(os.path.dirname(poses_cache), exist_ok=True)
    if os.path.exists(poses_cache):
        with open(poses_cache) as f:
            pose_data = json.load(f)
    else:
        extract_poses(video_path, poses_cache, sample_every=sample_every)
        with open(poses_cache) as f:
            pose_data = json.load(f)

    fps = pose_data['fps']
    frames = pose_data['frames']
    velocities = compute_wrist_velocity(frames)
    swings = find_swing_peaks(velocities, frames, fps, THRESHOLD_PERCENTILE, MIN_SWING_GAP_SEC)
    verify_swings(video_path, swings, fps, frames=frames)
    return filter_verified_swings(swings), fps


def extract_clip_for_swing(cap, swing, fps, total_frames, out_dir, index):
    start_frame = max(0, int(swing['peak_frame'] - CLIP_PRE_SEC * fps))
    end_frame = min(total_frames - 1, int(swing['peak_frame'] + CLIP_POST_SEC * fps))

    out_path = os.path.join(out_dir, f'swing_{index:03d}.mp4')
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    extract_clip(cap, start_frame, end_frame, out_path, fps, fourcc)
    # cv2.VideoWriter's mp4v fourcc produces old MPEG-4 Part 2 video on this
    # machine, unplayable in any browser -- see video_io.py's module
    # docstring. /api/analyse persists whatever gets uploaded here as-is
    # (a plain file copy, see backend/src/utils/videoCrop.js's
    # persistAndCrop()), so this clip must already be real H.264 before
    # upload, not just after the server-side crop step.
    reencode_to_h264(out_path)

    contact_frame_guess = swing.get('contact_frame_guess')
    contact_time_in_clip = None
    if contact_frame_guess is not None:
        contact_time_in_clip = round(max(0, (contact_frame_guess - start_frame) / fps), 3)

    return out_path, contact_time_in_clip


def classify_clip(clip_path, contact_time_in_clip):
    """
    Runs on the already-cut small clip, NOT the raw source video --
    classify_shot.classify() with frames_fps=None calls
    compare_swing.extract_user_poses() itself, whose landmarks are a
    dict-keyed-by-name shape; extract_poses.py's raw output (what
    find_swings() above works with) is a differently-shaped list, which
    classify() cannot read (throws AttributeError trying dict.get() on a
    list -- confirmed while building this script; the same mismatch is
    silently swallowed by list_swing_candidates.py's try/except around its
    own classify() call, worth fixing there separately). Re-running pose
    extraction here is cheap because the clip is only ~2-4s, unlike running
    it against the multi-minute source video.
    """
    contact_guess = contact_time_in_clip if contact_time_in_clip is not None else CLIP_PRE_SEC
    try:
        result = classify(clip_path, contact_guess)
        return result['shot_type'], result['scores']
    except Exception as e:
        return None, {'error': str(e)}


def upload_and_save(api_base, token, clip_path, shot_type, contact_time):
    with open(clip_path, 'rb') as f:
        data = {'shotType': shot_type}
        if contact_time is not None:
            data['contactTime'] = str(contact_time)
        res = requests.post(
            f'{api_base}/api/analyse',
            headers={'Authorization': f'Bearer {token}'},
            files={'video': (os.path.basename(clip_path), f, 'video/mp4')},
            data=data,
            timeout=ANALYSE_TIMEOUT_S,
        )
    if not res.ok:
        return None, f'/analyse failed ({res.status_code}): {res.text[:300]}'
    result = res.json()
    # /analyse's response has no shotType field of its own (it's echoed back
    # from what was uploaded with, same as the real app's saveHistory() in
    # frontend/api/history.js does: `{ ...result, shotType }`) -- /history
    # requires it and 400s without it.
    result['shotType'] = shot_type

    res2 = requests.post(
        f'{api_base}/api/history',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        data=json.dumps(result),
        timeout=30,
    )
    if not res2.ok:
        return result, f'/history failed ({res2.status_code}): {res2.text[:300]}'
    return res2.json(), None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video_path')
    parser.add_argument('--token', required=True)
    parser.add_argument('--api-base', default='http://localhost:5000')
    parser.add_argument('--sample-every', type=int, default=2)
    parser.add_argument('--dry-run', action='store_true', help='Detect + extract clips but skip the upload/save step.')
    args = parser.parse_args()

    video_path = os.path.abspath(args.video_path)
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = os.path.join(STAGING_DIR, video_name)
    os.makedirs(out_dir, exist_ok=True)

    print(f'[{video_name}] finding swings (sample_every={args.sample_every})...')
    t0 = time.time()
    swings, fps = find_swings(video_path, args.sample_every)
    print(f'[{video_name}] {len(swings)} verified swings found in {time.time() - t0:.0f}s')

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    report = []
    for i, sw in enumerate(swings, 1):
        clip_path, contact_time = extract_clip_for_swing(cap, sw, fps, total_frames, out_dir, i)
        shot_type, shot_scores = classify_clip(clip_path, contact_time)
        # Not a hard gate -- Jack can retag a saved analysis's shot_type in
        # the app afterward (PATCH /history/:id), so a low-margin guess
        # still gets uploaded rather than silently dropped. Flagged here so
        # the report tells him which ones are worth a second look.
        low_confidence = False
        if shot_type and isinstance(shot_scores, dict) and len(shot_scores) > 1:
            ranked = sorted(shot_scores.values(), reverse=True)
            low_confidence = (ranked[0] - ranked[1]) < 0.15
        entry = {
            'index': i, 'clip_path': clip_path, 'peak_time_sec': sw['peak_time'],
            'shot_type': shot_type, 'shot_scores': shot_scores, 'contact_time_in_clip': contact_time,
            'low_confidence': low_confidence,
        }

        if args.dry_run or not shot_type:
            entry['skipped'] = 'dry-run' if args.dry_run else 'no confident shot_type classification'
            print(f'  [{i}/{len(swings)}] {clip_path} -- skipped ({entry["skipped"]})')
            report.append(entry)
            continue

        saved, err = upload_and_save(args.api_base, args.token, clip_path, shot_type, contact_time)
        if err:
            entry['error'] = err
            print(f'  [{i}/{len(swings)}] {shot_type} -- FAILED: {err}')
        else:
            entry['saved_id'] = saved.get('id')
            entry['similarity'] = saved.get('similarity')
            print(f'  [{i}/{len(swings)}] {shot_type} -- saved as analysis #{saved.get("id")} (similarity {saved.get("similarity")})')
        report.append(entry)

    cap.release()

    report_path = os.path.join(out_dir, 'ingest_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f'\n[{video_name}] done. Report: {report_path}')


if __name__ == '__main__':
    main()
