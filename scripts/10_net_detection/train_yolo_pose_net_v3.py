"""Retrain the net-keypoint YOLO-pose model on the expanded v2+v3 dataset (107 usable labels, up from 24)."""
from ultralytics import YOLO

DATA_YAML = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_dataset_v3\data.yaml'

if __name__ == '__main__':
    model = YOLO('yolo11n-pose.pt')
    model.train(
        data=DATA_YAML,
        epochs=150,
        imgsz=320,
        batch=8,
        patience=40,
        project=r'C:\Users\jackp\tennis_app\data\10_net_detection',
        name='yolo_pose_run_v3',
        exist_ok=True,
        verbose=True,
    )
