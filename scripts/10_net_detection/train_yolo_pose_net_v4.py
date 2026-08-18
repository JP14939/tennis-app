"""Retrain the net-keypoint YOLO-pose model on the v4 dataset -- same v2+v3
positive labels as v3, plus real Claude-confirmed negative ("no tennis net")
examples for the first time (see prepare_net_pose_dataset_v4.py)."""
from ultralytics import YOLO

DATA_YAML = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_dataset_v4\data.yaml'

if __name__ == '__main__':
    model = YOLO('yolo11n-pose.pt')
    model.train(
        data=DATA_YAML,
        epochs=150,
        imgsz=320,
        batch=8,
        patience=40,
        project=r'C:\Users\jackp\tennis_app\data\10_net_detection',
        name='yolo_pose_run_v4',
        exist_ok=True,
        verbose=True,
    )
