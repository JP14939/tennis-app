import cv2
import json
import os
import sys
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "pose_landmarker.task")

LANDMARK_NAMES = [
    "nose","left_eye_inner","left_eye","left_eye_outer","right_eye_inner","right_eye",
    "right_eye_outer","left_ear","right_ear","mouth_left","mouth_right","left_shoulder",
    "right_shoulder","left_elbow","right_elbow","left_wrist","right_wrist","left_pinky",
    "right_pinky","left_index","right_index","left_thumb","right_thumb","left_hip",
    "right_hip","left_knee","right_knee","left_ankle","right_ankle","left_heel",
    "right_heel","left_foot_index","right_foot_index"
]

def extract_poses(video_path, output_path, sample_every=3):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: could not open {video_path}")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Video: {os.path.basename(video_path)}")
    print(f"Frames: {total_frames}, FPS: {fps:.1f}, Duration: {total_frames/fps:.1f}s")
    print(f"Sampling every {sample_every} frames...")

    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        output_segmentation_masks=False,
        num_poses=1,
    )

    results = []
    frame_idx = 0
    processed = 0

    with vision.PoseLandmarker.create_from_options(options) as landmarker:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_every == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect(mp_image)

                frame_data = {"frame": frame_idx, "timestamp": round(frame_idx / fps, 3), "landmarks": None}

                if result.pose_landmarks:
                    frame_data["landmarks"] = [
                        {
                            "name": LANDMARK_NAMES[i],
                            "x": round(lm.x, 4),
                            "y": round(lm.y, 4),
                            "z": round(lm.z, 4),
                            "visibility": round(lm.visibility, 4)
                        }
                        for i, lm in enumerate(result.pose_landmarks[0])
                    ]

                results.append(frame_data)
                processed += 1

                if processed % 100 == 0:
                    detected = sum(1 for r in results if r["landmarks"])
                    print(f"  {processed} samples ({frame_idx}/{total_frames} frames) — pose detected in {detected}")

            frame_idx += 1

    cap.release()

    detected = sum(1 for r in results if r["landmarks"])
    print(f"\nDone. {processed} samples, pose detected in {detected} ({100*detected//processed if processed else 0}%)")

    with open(output_path, "w") as f:
        json.dump({"video": os.path.basename(video_path), "fps": fps, "total_frames": total_frames, "frames": results}, f)

    print(f"Saved to {output_path}")

if __name__ == "__main__":
    video = r"C:\Users\jackp\tennis_app\data\01_source_videos\forehand\forehand_compilation_1.mp4"
    output = r"C:\Users\jackp\tennis_app\data\02_pose_extraction\forehand_poses.json"
    extract_poses(video, output, sample_every=3)
