import json
import os
import cv2

SAMPLE_COUNT = 10  # how many swings to sample per video

VIDEOS = [
    (
        r'C:\Users\jackp\tennis_app\data\01_source_videos\forehand\forehand_compilation_1.mp4',
        r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings.json',
        r'C:\Users\jackp\tennis_app\data\05_review_samples\forehand',
    ),
    (
        r'C:\Users\jackp\tennis_app\data\01_source_videos\backhand\backhand_compilation_1.mp4',
        r'C:\Users\jackp\tennis_app\data\03_swing_detection\backhand_swings.json',
        r'C:\Users\jackp\tennis_app\data\05_review_samples\backhand',
    ),
    (
        r'C:\Users\jackp\tennis_app\data\01_source_videos\serve\serve_compilation_1.mp4',
        r'C:\Users\jackp\tennis_app\data\03_swing_detection\serve_swings.json',
        r'C:\Users\jackp\tennis_app\data\05_review_samples\serve',
    ),
]


def extract_frame(cap, frame_num, fps, out_path, label):
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    if not ret:
        print(f"  Could not read frame {frame_num}")
        return

    # Resize to reasonable preview size
    h, w = frame.shape[:2]
    max_w = 960
    if w > max_w:
        scale = max_w / w
        frame = cv2.resize(frame, (max_w, int(h * scale)))

    # Overlay label
    cv2.putText(frame, label, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 80), 2, cv2.LINE_AA)

    cv2.imwrite(out_path, frame)


def review(video_path, swings_path, out_dir):
    shot_type = os.path.basename(out_dir)
    print(f"\n--- {shot_type.upper()} ---")

    with open(swings_path) as f:
        data = json.load(f)

    swings = data['swings']
    fps = data['fps']
    total = data['swings_detected']
    print(f"  {total} swings detected in {data['total_duration_sec']}s of video")

    os.makedirs(out_dir, exist_ok=True)

    # Sample evenly across all detected swings
    step = max(1, total // SAMPLE_COUNT)
    sampled = swings[::step][:SAMPLE_COUNT]

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  ERROR: could not open {video_path}")
        return

    for sw in sampled:
        peak_frame = sw['peak_frame']
        label = f"Swing {sw['swing_id']} | t={sw['peak_time_sec']}s | vel={sw['peak_velocity']:.4f}"
        out_path = os.path.join(out_dir, f"swing_{sw['swing_id']:04d}_peak.jpg")
        extract_frame(cap, peak_frame, fps, out_path, label)
        print(f"  Saved swing {sw['swing_id']} (t={sw['peak_time_sec']}s) -> {os.path.basename(out_path)}")

    cap.release()
    print(f"  Review images saved to: {out_dir}")


if __name__ == '__main__':
    for video_path, swings_path, out_dir in VIDEOS:
        if not os.path.exists(swings_path):
            print(f"Skipping {swings_path} (not found)")
            continue
        review(video_path, swings_path, out_dir)

    print("\nDone. Open the review folders to inspect the frames.")
    print("  C:\\Users\\jackp\\tennis_app\\data\\review\\")
