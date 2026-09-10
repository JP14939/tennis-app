"""v10 -- recall-focused net-keypoint retrain: 2 keypoints (top corners only),
amateur frames added as training data, honest held-out-video split
(prepare_net_pose_dataset_v10.py).

imgsz 640 (was 320). ~4 h on this CPU-only box. Auto-resumes from
yolo_pose_run_v10/weights/last.pt if a previous run was interrupted.
workers=4 (down from 8) -- an imgsz-640 CPU run with 8 dataloader workers was
dying silently around epoch 38, likely memory pressure alongside other jobs.

If it wins on eval_net_keypoints.py, infer_angle.run_net_keypoint_model must
also predict at imgsz=640 -- and re-time the per-request inference.
"""
import os
from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))
NET_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'data', '10_net_detection'))
DATA_YAML = os.path.join(NET_DIR, 'yolo_pose_dataset_v10', 'data.yaml')
LAST = os.path.join(NET_DIR, 'yolo_pose_run_v10', 'weights', 'last.pt')

COMMON = dict(
    data=DATA_YAML, epochs=150, imgsz=640, batch=8, patience=40, degrees=5.0,
    workers=4, project=NET_DIR, name='yolo_pose_run_v10', exist_ok=True, verbose=True,
)

if __name__ == '__main__':
    if os.path.exists(LAST):
        print(f'Resuming from {LAST}', flush=True)
        YOLO(LAST).train(resume=True)
    else:
        YOLO('yolo11n-pose.pt').train(**COMMON)
