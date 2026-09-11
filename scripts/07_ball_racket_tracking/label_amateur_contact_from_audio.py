"""
Auto-labels contact time on the amateur swing-clip set from AUDIO, instead of
hand-marking. The amateur SOURCE videos (data/01_source_videos/amateur/*.mp4,
real YouTube match footage) have real audio; the CUT clips
(data/04_clips/amateur/*.mp4) don't -- extract_clips.py's cv2.VideoWriter never
carries an audio stream (same reason Jack's own IMG_5822/5823 raw-ingest clips
lost theirs; see video_io.py's comment). Rather than making Jack hand-mark
these too, this runs the SAME onset_classifier.pkl the live app uses, with the
SAME confidence gate (proba>=0.60, margin>=0.20) against the source video's
audio -- only CONFIDENT picks are trusted as ground truth. This is exactly the
methodology that already validated the pro-database audio fill (Phase B.2:
confident picks land 96% within 50ms of a human mark) -- not a new, untested
shortcut.

Source: data/04_clips/amateur/manifest.json (248 candidates: video_id,
swing_id, peak_frame/peak_time_sec -- a rough wrist-velocity-peak anchor, SOURCE-
video-relative -- clip_path) x data/08_coaching_ai/amateur_swing_labels.json
(shot-type ground truth; 'skip'/unlabeled entries excluded). Per-swing
start_time_sec (to convert the audio pick from source-video-relative to
clip-local time) comes from data/03_swing_detection/amateur_<video_id>_swings.json,
the same file extract_amateur_clips.py read start_frame/end_frame from when it
cut each clip.

Writes to the SAME file mark_amateur_contact_time.py (the manual fallback, for
footage with no audio at all) writes to --
data/07_ball_racket_tracking/amateur_contact_labels.jsonl -- tagged
source='audio_pseudolabel' with its confidence/margin, so amateur_contact_eval.py
can tell the two apart or pool them. Resumable (skips clip_paths already
present, from either source).

Usage:
  python label_amateur_contact_from_audio.py [--limit N] [--shot-type forehand]
"""
import argparse
import datetime as _dt
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), '00_utils'))
from paths import DATA_DIR  # noqa: E402
from audio_onset import extract_audio_wav, has_audio_stream  # noqa: E402
from audio_contact import detect_contact  # noqa: E402

MANIFEST_PATH = os.path.join(DATA_DIR, '04_clips', 'amateur', 'manifest.json')
LABELS_PATH = os.path.join(DATA_DIR, '08_coaching_ai', 'amateur_swing_labels.json')
SWINGS_DIR = os.path.join(DATA_DIR, '03_swing_detection')
SRC_DIR = os.path.join(DATA_DIR, '01_source_videos', 'amateur')
AUDIO_CACHE = os.path.join(DATA_DIR, '07_ball_racket_tracking', '.audio_cache')
OUT_PATH = os.path.join(DATA_DIR, '07_ball_racket_tracking', 'amateur_contact_labels.jsonl')

# Same per-shot-type search windows compare_swing.py uses live (SERVE_AUDIO_
# WINDOW_SEC / GROUNDSTROKE_AUDIO_WINDOW_SEC) -- duplicated here rather than
# imported, since compare_swing.py pulls in cv2/mediapipe at module level and
# this script has no other reason to pay that import cost.
SERVE_AUDIO_WINDOW_SEC = 0.8
GROUNDSTROKE_AUDIO_WINDOW_SEC = 0.5


def _iso_now():
    return _dt.datetime.now().isoformat(timespec='seconds')


def load_candidates(shot_type_filter=None):
    labels = json.load(open(LABELS_PATH))['labels']
    manifest = json.load(open(MANIFEST_PATH))
    out = []
    for m in manifest:
        key = f"{m['video_id']}_{m['swing_id']}"
        shot_type = labels.get(key)
        if shot_type in (None, 'skip'):
            continue
        if shot_type_filter and shot_type != shot_type_filter:
            continue
        out.append({**m, 'shot_type': shot_type})
    return out


_swings_cache = {}


def swing_lookup(video_id, swing_id):
    """{start_time_sec, end_time_sec, fps} for one swing, from the same
    per-video swings JSON extract_amateur_clips.py read start_frame/end_frame
    from originally."""
    if video_id not in _swings_cache:
        path = os.path.join(SWINGS_DIR, f'amateur_{video_id}_swings.json')
        with open(path) as f:
            data = json.load(f)
        _swings_cache[video_id] = {
            'fps': data['fps'],
            'by_id': {sw['swing_id']: sw for sw in data['swings']},
        }
    entry = _swings_cache[video_id]
    sw = entry['by_id'].get(swing_id)
    if sw is None:
        return None
    return {'start_time_sec': sw['start_time_sec'], 'end_time_sec': sw['end_time_sec'],
           'fps': entry['fps']}


def load_done():
    if not os.path.exists(OUT_PATH):
        return set()
    done = set()
    with open(OUT_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                done.add(json.loads(line)['clip_path'])
    return done


def append_row(row):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'a') as f:
        f.write(json.dumps(row) + '\n')


# Slack either side of the swing's own [start_time_sec, end_time_sec] span,
# so the extracted window still comfortably covers the anchor +- search
# window used below.
WINDOW_PAD_SEC = 1.0


def swing_audio_wav(video_id, swing_id, start_time_sec, end_time_sec):
    """A SHORT windowed wav around one swing (not the whole source video --
    onset_envelope() normalises flux by the track's own max, so handing it a
    multi-minute file lets one loud moment ANYWHERE in the match (a cheer, a
    line call) crush every real contact onset to near-zero; a per-swing
    window keeps the normalisation local, matching how the classifier was
    trained on ~3s clip-relative windows in the first place).

    Returns (wav_path, window_start_sec) or (None, None) if there's no
    audio. `window_start_sec`: what source-video time the wav's t=0
    corresponds to (needed to convert a pick back to clip-local time)."""
    src = os.path.join(SRC_DIR, f'{video_id}.mp4')
    window_start_sec = max(0.0, start_time_sec - WINDOW_PAD_SEC)
    dur_sec = (end_time_sec - start_time_sec) + 2 * WINDOW_PAD_SEC
    os.makedirs(AUDIO_CACHE, exist_ok=True)
    wav_path = os.path.join(AUDIO_CACHE, f'amateur_{video_id}_{swing_id}.wav')
    if not os.path.exists(wav_path):
        if not has_audio_stream(src):
            return None, None
        if not extract_audio_wav(src, wav_path, start_sec=window_start_sec, dur_sec=dur_sec):
            return None, None
    return wav_path, window_start_sec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--shot-type', choices=['forehand', 'backhand', 'serve'])
    args = ap.parse_args()

    candidates = load_candidates(shot_type_filter=args.shot_type)
    done = load_done()
    todo = [c for c in candidates if c['clip_path'] not in done]
    if args.limit:
        todo = todo[:args.limit]

    print(f'{len(candidates)} labelled non-skip candidates | {len(done)} already done | '
          f'{len(todo)} to process this run', file=sys.stderr)

    confident = defaultdict(int)
    unconfident = defaultdict(int)
    no_swing_data = no_audio = 0

    for i, cand in enumerate(todo, 1):
        vid, sid, shot = cand['video_id'], cand['swing_id'], cand['shot_type']
        sw = swing_lookup(vid, sid)
        if sw is None:
            no_swing_data += 1
            continue

        wav, window_start_sec = swing_audio_wav(vid, sid, sw['start_time_sec'], sw['end_time_sec'])
        if wav is None:
            no_audio += 1
            continue

        window = SERVE_AUDIO_WINDOW_SEC if shot == 'serve' else GROUNDSTROKE_AUDIO_WINDOW_SEC
        # peak_time_sec is source-video-relative; re-express relative to the
        # windowed wav's own t=0 before handing it to detect_contact.
        anchor_in_wav = cand['peak_time_sec'] - window_start_sec
        ac = detect_contact(
            video_path=None, audio_path=wav,
            anchor_time_sec=anchor_in_wav, search_window_sec=window,
            video_hints={'wrist_peak_sec': anchor_in_wav, 'pose_pred_sec': anchor_in_wav},
        )
        if i % 20 == 0 or i == len(todo):
            print(f'  [{i}/{len(todo)}] {vid} {shot} swing {sid}: '
                  f'{"confident" if ac and ac["confident"] else "not confident" if ac else "no onsets"}',
                  file=sys.stderr)

        if not ac or not ac['confident']:
            unconfident[shot] += 1
            continue

        # ac['contact_time_sec'] is wav-relative; clip-local = wav-relative
        # minus the offset from the clip's own start to the wav's t=0.
        clip_contact_time_sec = ac['contact_time_sec'] - (sw['start_time_sec'] - window_start_sec)
        duration = sw['end_time_sec'] - sw['start_time_sec']
        if not (0.0 <= clip_contact_time_sec <= duration):
            # Sanity guard: the window should keep the pick inside the clip's
            # own span -- if it somehow doesn't, don't trust it as a label.
            unconfident[shot] += 1
            continue

        confident[shot] += 1
        append_row({
            'clip_path': cand['clip_path'],
            'source_video': vid,
            'shot_type': shot,
            'contact_frame': round(clip_contact_time_sec * sw['fps']),
            'contact_time_sec': round(clip_contact_time_sec, 4),
            'fps': round(sw['fps'], 4),
            'confidence': round(ac['confidence'], 4),
            'margin': round(ac['margin'], 4),
            'source': 'audio_pseudolabel',
            'marked_at': _iso_now(),
        })

    total_confident = sum(confident.values())
    print(f'\nDone: {total_confident} confidently labelled ({dict(confident)}), '
          f'{sum(unconfident.values())} not confident enough ({dict(unconfident)}), '
          f'{no_swing_data} missing swing data, {no_audio} no source audio. '
          f'Total in {OUT_PATH}: {len(load_done())}.',
          file=sys.stderr)


if __name__ == '__main__':
    main()
