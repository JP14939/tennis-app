import argparse
import cv2

# Cuts an arbitrary [start_sec, start_sec + duration_sec) window out of a video.
# Same OpenCV cut pattern as extract_clip() in 04_clip_extraction/extract_clips.py.
# Standalone dev CLI, not called by the app pipeline -- output is written with
# cv2.VideoWriter's mp4v fourcc same as everywhere else in this pipeline (old
# MPEG-4 Part 2, unplayable in a browser -- see 00_utils/video_io.py's module
# docstring); pass the output through video_io.reencode_to_h264() if you need
# to actually watch the result in the app rather than just inspect frames.


def trim_video(input_path, output_path, start_sec, duration_sec=None):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    start_frame = int(start_sec * fps)
    end_frame = total_frames if duration_sec is None else min(total_frames, int((start_sec + duration_sec) * fps))

    print(f"Input: {w}x{h} @ {fps:.1f}fps, {total_frames} frames ({total_frames/fps:.1f}s)")
    print(f"Trimming frames {start_frame}..{end_frame} ({(end_frame-start_frame)/fps:.1f}s) -> {output_path}")

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    written = 0
    for _ in range(end_frame - start_frame):
        ret, frame = cap.read()
        if not ret:
            break
        writer.write(frame)
        written += 1

    writer.release()
    cap.release()
    print(f"Done. Wrote {written} frames.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Trim a video to a [start, start+duration] window")
    parser.add_argument('input', help='Path to source video')
    parser.add_argument('output', help='Path to write trimmed video')
    parser.add_argument('--start-sec', type=float, default=0.0)
    parser.add_argument('--duration-sec', type=float, default=None)
    args = parser.parse_args()
    trim_video(args.input, args.output, args.start_sec, args.duration_sec)
