"""v6 -- v4 labels, HONEST source-group train/val split (prepare_net_pose_dataset_v6.py).
Same imgsz/epochs as v2-v5 so the only variable vs v4 is the split. The val
Pose mAP here is the first trustworthy one; judge keep/ship on
eval_net_keypoints.py against net_keypoint_testset_v1, not on this number."""
import os
from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_YAML = os.path.normpath(os.path.join(
    HERE, '..', '..', 'data', '10_net_detection', 'yolo_pose_dataset_v6', 'data.yaml'))

if __name__ == '__main__':
    model = YOLO('yolo11n-pose.pt')
    model.train(
        data=DATA_YAML, epochs=150, imgsz=320, batch=8, patience=40,
        project=os.path.normpath(os.path.join(HERE, '..', '..', 'data', '10_net_detection')),
        name='yolo_pose_run_v6', exist_ok=True, verbose=True,
    )
