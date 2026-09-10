"""v9 -- same data + honest group split as v6, but imgsz 640 instead of 320.

Corner localization is resolution-bound: 320 on a 1920-wide frame is a 6x
downsample. This isolates the imgsz effect (compare v9 vs v6 on
eval_net_keypoints.py). If it wins, infer_angle.run_net_keypoint_model must
also pass imgsz=640 to model.predict -- and re-time inference, since the
backend spawns a Python process per request.
"""
import os
from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_YAML = os.path.normpath(os.path.join(
    HERE, '..', '..', 'data', '10_net_detection', 'yolo_pose_dataset_v6', 'data.yaml'))

if __name__ == '__main__':
    model = YOLO('yolo11n-pose.pt')
    model.train(
        data=DATA_YAML, epochs=150, imgsz=640, batch=8, patience=40,
        project=os.path.normpath(os.path.join(HERE, '..', '..', 'data', '10_net_detection')),
        name='yolo_pose_run_v9', exist_ok=True, verbose=True,
    )
