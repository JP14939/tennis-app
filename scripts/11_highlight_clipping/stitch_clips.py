"""
Stitch multiple rally clips into a single highlight reel.

No ffmpeg/moviepy on this machine (see 00_utils/trim_video.py's comment) --
reads each clip's frames with OpenCV and rewrites them into one output file,
the same approach already used by extract_clips.py / detect_rallies.py /
trim_video.py elsewhere in this pipeline. Source clips are assumed to share
the same fps/resolution (true here -- they're all written by the same
extract_clip() call against the same source match video), so no
scaling/reencoding step is needed; a mismatched clip is skipped with a
reason rather than crashing the whole reel. None of these clips carry audio
(cv2.VideoWriter never wrote any to begin with), so there's no audio
sync concern either.

Usage:
  python stitch_clips.py <output_path> <clip_path_1> [clip_path_2 ...]

Output (stdout): JSON --
  {"output_path": "...", "clips_stitched": N, "clips_skipped": [...],
   "total_frames": N, "duration_sec": N}
On error: {"error": "..."}
"""
import sys
import os
import json
import cv2


def stitch_clips(clip_paths, output_path):
    if not clip_paths:
        raise ValueError('No clips to stitch')

    writer = None
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    written_clips = 0
    skipped = []
    total_frames = 0
    ref_fps = ref_w = ref_h = None

    for clip_path in clip_paths:
        if not os.path.exists(clip_path):
            skipped.append({'clip': clip_path, 'reason': 'missing'})
            continue

        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            skipped.append({'clip': clip_path, 'reason': 'unreadable'})
            continue

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            # Some clips (mis-parsed container/codec) report fps=0 -- used
            # unguarded below both as the VideoWriter's fps and as the
            # duration_sec divisor, the latter crashing with
            # ZeroDivisionError. 30 matches this pipeline's ASSUMED_FPS
            # elsewhere (e.g. frontend/screens/ContactMarkingScreen.js).
            fps = 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if writer is None:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))
            ref_fps, ref_w, ref_h = fps, w, h
        elif (w, h) != (ref_w, ref_h):
            skipped.append({'clip': clip_path, 'reason': f'resolution mismatch ({w}x{h} vs {ref_w}x{ref_h})'})
            cap.release()
            continue

        clip_frames = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            writer.write(frame)
            clip_frames += 1
        cap.release()

        total_frames += clip_frames
        written_clips += 1

    if writer is not None:
        writer.release()

    if written_clips == 0:
        raise RuntimeError('No clips could be stitched (all missing/unreadable)')

    return {
        'output_path': output_path,
        'clips_stitched': written_clips,
        'clips_skipped': skipped,
        'total_frames': total_frames,
        'duration_sec': round(total_frames / ref_fps, 1),
    }


def main():
    if len(sys.argv) < 3:
        print(json.dumps({'error': 'Usage: stitch_clips.py <output_path> <clip_path_1> [clip_path_2 ...]'}))
        sys.exit(1)

    output_path = sys.argv[1]
    clip_paths = sys.argv[2:]

    try:
        result = stitch_clips(clip_paths, output_path)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
