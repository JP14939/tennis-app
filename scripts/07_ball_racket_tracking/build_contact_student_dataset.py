"""
Phase C.2 -- build the visual-contact student's training set.

For every pro swing in data/03_swing_detection/*_swings_validated.json, get a
contact-frame LABEL from one of two teachers:

  human         -- Jack's Pro Clip Review contact mark (clip_review_log.jsonl)
  audio_teacher -- the PURE-AUDIO onset teacher (onset_classifier_audioonly.pkl),
                   run on the source video's audio, confident picks only.
                   No pose / ball / clip-cut features -> stays independent of
                   the visual student it trains.

Then extract the STUDENT's own evidence from the clip window
(pose -> find_peak_wrist_frame anchor -> track_racket_and_ball ->
find_contact_frame + contact_frame_meta + a wrist velocity/accel/jerk profile)
and log a training row via contact_frame_training_log.log_example().

Resumable: skips (shot_type, swing_id) already logged. Overnight run.

Usage:
  python build_contact_student_dataset.py [--shot-type forehand] [--limit N]
                                          [--audio-only | --human-only]
"""
import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE,
          os.path.join(SCRIPTS_DIR, '00_utils'),
          os.path.join(SCRIPTS_DIR, '02_pose_extraction'),
          os.path.join(SCRIPTS_DIR, '03_swing_detection'),
          os.path.join(SCRIPTS_DIR, '06_database_build'),
          os.path.join(SCRIPTS_DIR, '08_comparison_engine')):
    if p not in sys.path:
        sys.path.insert(0, p)

from paths import DATA_DIR  # noqa: E402
import clip_review_log  # noqa: E402
from source_footage_lookup import (  # noqa: E402
    SWINGS_VALIDATED_BY_SHOT_TYPE, SOURCE_VIDEOS_BY_SHOT_TYPE,
)
from clip_urls import PRO_CLIPS_DIR  # noqa: E402
from audio_onset import FFMPEG, extract_audio_wav  # noqa: E402
import audio_contact  # noqa: E402
import contact_frame_training_log as cflog  # noqa: E402
from contact_evidence import compute_contact_evidence  # noqa: E402
from compare_swing import find_peak_wrist_frame  # noqa: E402

POSE_CACHE = os.path.join(DATA_DIR, '07_ball_racket_tracking', '.student_pose_cache')
AUDIO_CACHE = os.path.join(DATA_DIR, '07_ball_racket_tracking', '.student_audio_cache')
AUDIO_ONLY_MODEL = audio_contact.AUDIO_ONLY_MODEL_PATH
PRO_DB_PATH = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')

AUDIO_PAD_SEC = 0.3      # a little extra audio past the clip end


def _lm_by_name(fr):
    lm = fr.get('landmarks')
    return {d['name']: d for d in lm} if lm else None


def _human_labels():
    """{f'{shot_type}_{swing_id:04d}': clip_relative_contact_sec} -- ONLY the
    entries Jack actually hand-marked a contact frame on ('contact_time_
    corrected', latest 'new' value). 'label_confirmed' in the quality-only
    review means "video is fine", NOT "contact time verified" -- those still
    carry the 1.0s / 1.8s placeholder, so they must NOT be used as labels."""
    latest, corrected = {}, {}
    with open(clip_review_log.LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            latest[r['entry_id']] = r['verdict']
            if r['verdict'] == 'contact_time_corrected' and r.get('note') and '->' in r['note']:
                try:
                    corrected[r['entry_id']] = float(r['note'].split('->')[1].strip().rstrip('s'))
                except ValueError:
                    pass
    return {eid: corrected[eid] for eid, v in latest.items()
            if v == 'contact_time_corrected' and eid in corrected}


def _already_done(exclude_sources=()):
    """swing_keys already logged. `exclude_sources`: sources NOT to count as
    done, so --force-relog can re-extract them (e.g. the pre-Phase-C 'human'
    rows that lack the wrist-kinematics features the model now expects)."""
    done = set()
    for r in cflog.read_log():
        m = r.get('student_meta') or {}
        src = r.get('source')
        if m.get('swing_key') and src in ('human', 'audio_teacher') and src not in exclude_sources:
            done.add(m['swing_key'])
    return done


def _extract_clip(source, start_sec, dur_sec, out_mp4):
    if os.path.exists(out_mp4):
        return True
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    try:
        subprocess.run([FFMPEG, '-y', '-v', 'error', '-ss', f'{start_sec:.3f}',
                        '-t', f'{dur_sec:.3f}', '-i', source, '-an',
                        '-c:v', 'libx264', '-preset', 'ultrafast', out_mp4],
                       check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _get_poses(clip_mp4, key):
    os.makedirs(POSE_CACHE, exist_ok=True)
    cache = os.path.join(POSE_CACHE, f'{key}.json')
    if not os.path.exists(cache):
        from extract_poses import extract_poses
        with contextlib.redirect_stdout(sys.stderr):
            extract_poses(clip_mp4, cache, sample_every=3)
    with open(cache) as f:
        return json.load(f)


def _student_evidence(clip_mp4, key, fps):
    """Runs the live visual contact pipeline on the clip (via the shared
    contact_evidence.compute_contact_evidence, same code compare_swing's
    audioless path uses). Returns (student_frame, confidence, method,
    student_meta, clip_fps) or None."""
    pd = _get_poses(clip_mp4, key)
    raw = pd.get('frames') or []
    frames = [{'frame': fr['frame'], 'landmarks': _lm_by_name(fr)} for fr in raw]
    if not any(f['landmarks'] for f in frames):
        return None
    clip_fps = pd.get('fps') or fps
    anchor_list_idx = find_peak_wrist_frame(frames, clip_fps)
    anchor_frame = frames[anchor_list_idx]['frame']

    ev = compute_contact_evidence(clip_mp4, frames, clip_fps, anchor_frame, anchor_list_idx)
    if ev is None:
        return None
    meta = ev['student_meta']
    meta['swing_key'] = key
    return ev['student_frame'], ev['student_confidence'], ev['student_method'], meta, clip_fps


def process_swing(shot_type, swing, source_video, human_time, want_audio):
    key = f'{shot_type}_{swing["swing_id"]}'
    fps = None
    start_f, end_f = swing['start_frame'], swing['end_frame']

    # source-relative clip start; validated JSON fps is the source fps
    src_fps = swing.get('_src_fps')
    start_sec = start_f / src_fps
    dur_sec = (end_f - start_f) / src_fps

    # ---- teacher label (clip-relative seconds) ----
    if human_time is not None:
        teacher_clip_sec, source = human_time, 'human'
    elif want_audio:
        os.makedirs(AUDIO_CACHE, exist_ok=True)
        wav = os.path.join(AUDIO_CACHE, f'{key}.wav')
        if not extract_audio_wav(source_video, wav, start_sec=start_sec,
                                 dur_sec=dur_sec + AUDIO_PAD_SEC):
            return 'no_audio'
        ac = audio_contact.detect_contact(
            'x', audio_path=wav, model_path=AUDIO_ONLY_MODEL,
            conf_proba=0.75, conf_margin=0.25)
        if not ac or not ac['confident']:
            return 'audio_not_confident'
        teacher_clip_sec, source = ac['contact_time_sec'], 'audio_teacher'
    else:
        return 'no_teacher'

    # ---- student evidence ----
    clip = swing.get('clip_path')
    tmp = None
    if not (clip and os.path.exists(clip)):
        alt = os.path.join(PRO_CLIPS_DIR, shot_type,
                           f'{shot_type}_swing_{swing["swing_id"]:04d}')
        cand = next((p for p in (alt + s for s in ('.mp4',)) if os.path.exists(p)), None)
        clip = cand
    if not (clip and os.path.exists(clip)):
        fd, tmp = tempfile.mkstemp(suffix='.mp4', prefix='studentclip_')
        os.close(fd); os.remove(tmp)
        if not _extract_clip(source_video, start_sec, dur_sec, tmp):
            return 'clip_extract_failed'
        clip = tmp
    try:
        ev = _student_evidence(clip, key, src_fps)
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    if ev is None:
        return 'no_pose'
    student_frame, conf, method, meta, clip_fps = ev

    teacher_frame = round(teacher_clip_sec * clip_fps)
    cflog.log_example(student_frame, conf, method, teacher_frame, clip_fps,
                      source=source, student_meta=meta)
    return source


# ── Practice-footage sweep (--practice) ─────────────────────────────────────
# Separate from the broadcast sweep above: practice_mvp entries live in
# pro_database.json under their own id scheme (practice_<n>), not
# 03_swing_detection/*_swings_validated.json's (shot_type, swing_id) scheme,
# and their contact-time ground truth comes from Jack's Pro Clip Review
# corrections (clip_review_log.jsonl), not _human_labels()'s broadcast-only
# parsing. Deliberately NOT called from correct_contact_time.py's request
# path -- that endpoint is awaited synchronously by the review screen on
# every submit, and _student_evidence() below is a ~10s MediaPipe pass; this
# stays a separate batch/background sweep, same shape as --audio-only, run
# whenever there's a new batch of reviewed practice corrections to pick up.

def _practice_teacher_times():
    """{practice_entry_id: corrected_contact_time_sec} for every practice_mvp
    entry with a real Pro Clip Review verdict. 'contact_time_corrected' gives
    the corrected time directly (same 'a -> b' note parsing _human_labels()
    uses for the broadcast queue); 'label_confirmed' / 'shot_type_corrected'
    mean the contact time shown was already correct when Jack reviewed it, so
    the entry's current clip_contact_time_sec IS the human-verified label."""
    with open(PRO_DB_PATH) as f:
        db = json.load(f)
    contact_by_id = {
        e['id']: e.get('clip_contact_time_sec')
        for e in db['entries'] if e.get('ingest') == 'practice_mvp'
    }
    out = {}
    for eid, (verdict, note) in clip_review_log.latest_verdict_notes().items():
        if not eid.startswith('practice_') or eid not in contact_by_id:
            continue
        if verdict not in clip_review_log.LABEL_REVIEW_VERDICTS:
            continue
        if verdict == 'contact_time_corrected' and note and '->' in note:
            try:
                out[eid] = float(note.split('->')[1].strip().rstrip('s'))
                continue
            except ValueError:
                pass
        if contact_by_id[eid] is not None:
            out[eid] = contact_by_id[eid]
    return out


def _already_done_practice():
    """practice_ entry ids already logged (source='human') in Phase C's
    training log -- mirrors _already_done()'s resumability, scoped to the
    practice id namespace."""
    done = set()
    for r in cflog.read_log():
        m = r.get('student_meta') or {}
        key = m.get('swing_key')
        if key and key.startswith('practice_') and r.get('source') == 'human':
            done.add(key)
    return done


def run_practice(limit=None):
    teacher_times = _practice_teacher_times()
    done = _already_done_practice()
    # Read pro_database.json ONCE up front, not per-swing -- re-opening it on
    # every iteration raced Jack's live Pro Clip Review session (which
    # rewrites the whole file on every correction, non-atomically) and threw
    # a JSONDecodeError mid-sweep the first time this ran concurrently with
    # him reviewing. A single snapshot at sweep-start is both faster and
    # race-free; missing a correction made mid-sweep just means it's picked
    # up on the next run.
    with open(PRO_DB_PATH) as f:
        by_id = {e['id']: e for e in json.load(f)['entries']}

    from collections import Counter
    tally = Counter()
    n = 0
    for eid, teacher_sec in teacher_times.items():
        if eid in done:
            tally['already_done'] += 1
            continue
        if limit and n >= limit:
            break
        entry = by_id.get(eid)
        if entry is None:
            tally['entry_removed'] += 1
            continue
        n += 1
        clip = os.path.join(PRO_CLIPS_DIR, entry['clip_path'])
        if not os.path.exists(clip):
            tally['clip_missing'] += 1
            continue
        try:
            ev = _student_evidence(clip, eid, fps=None)
        except Exception as e:  # noqa: BLE001
            import traceback; traceback.print_exc()
            tally[f'error:{type(e).__name__}'] += 1
            continue
        if ev is None:
            tally['no_pose'] += 1
            continue
        student_frame, conf, method, meta, clip_fps = ev
        teacher_frame = round(teacher_sec * clip_fps)
        cflog.log_example(student_frame, conf, method, teacher_frame, clip_fps,
                          source='human', student_meta=meta)
        tally['human'] += 1
        if n % 25 == 0:
            print(f'  [{n}] {eid} -> logged   {dict(tally)}', file=sys.stderr)

    print('\n=== practice sweep done ===')
    for k, v in sorted(tally.items(), key=lambda t: -t[1]):
        print(f'  {k:<22} {v}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shot-type', choices=['forehand', 'backhand', 'serve'])
    ap.add_argument('--limit', type=int)
    ap.add_argument('--audio-only', action='store_true', help='skip human-labelled swings')
    ap.add_argument('--human-only', action='store_true', help='only human-labelled swings')
    ap.add_argument('--force-relog', action='store_true',
                    help="re-process 'human'-labelled swings even if already logged "
                         "(appends a fresh row; train_contact_frame_model dedups to newest). "
                         "Use to backfill wrist-kinematics features onto pre-Phase-C rows.")
    ap.add_argument('--practice', action='store_true',
                    help='sweep practice_mvp entries reviewed in Pro Clip Review instead of '
                         'the broadcast 03_swing_detection sweep -- separate id scheme/data '
                         'source, mutually exclusive with the flags above.')
    args = ap.parse_args()

    if args.practice:
        run_practice(limit=args.limit)
        return

    human = _human_labels()
    done = _already_done(exclude_sources=('human',) if args.force_relog else ())
    shot_types = [args.shot_type] if args.shot_type else ['forehand', 'backhand', 'serve']

    from collections import Counter
    tally = Counter()
    n = 0
    for st in shot_types:
        val_paths = SWINGS_VALIDATED_BY_SHOT_TYPE.get(st, [])
        src_paths = SOURCE_VIDEOS_BY_SHOT_TYPE.get(st, [])
        for job_i, vp in enumerate(val_paths):
            if not os.path.exists(vp) or job_i >= len(src_paths):
                continue
            src = src_paths[job_i]
            if not os.path.exists(src):
                tally['no_source_video'] += 1
                continue
            data = json.load(open(vp))
            src_fps = data['fps']
            for sw in data['swings']:
                key = f'{st}_{sw["swing_id"]}'
                if key in done:
                    tally['already_done'] += 1
                    continue
                eid = f'{st}_{sw["swing_id"]:04d}'
                htime = human.get(eid)
                if args.human_only and htime is None:
                    continue
                if args.audio_only:
                    htime = None
                sw['_src_fps'] = src_fps
                if args.limit and n >= args.limit:
                    break
                n += 1
                try:
                    res = process_swing(st, sw, src, htime, want_audio=not args.human_only)
                except Exception as e:  # noqa: BLE001
                    import traceback; traceback.print_exc()
                    res = f'error:{type(e).__name__}'
                tally[res] += 1
                if n % 25 == 0:
                    print(f'  [{n}] {st} sw{sw["swing_id"]} -> {res}   {dict(tally)}', file=sys.stderr)
            if args.limit and n >= args.limit:
                break

    print('\n=== done ===')
    for k, v in sorted(tally.items(), key=lambda t: -t[1]):
        print(f'  {k:<22} {v}')
    print(f'\ncontact_frame_training_log now:')
    for src in ('human', 'audio_teacher', 'user_submitted', 'manual_review'):
        s = cflog.stats(window=10 ** 9, source=src)
        print(f'  {src:<16} n={s["n"]}')


if __name__ == '__main__':
    main()
