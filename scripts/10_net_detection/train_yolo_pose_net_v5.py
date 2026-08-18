"""Retrain the net-keypoint YOLO-pose model on the v5 dataset -- v4's
positives+negatives plus new empty-court/no-player positives (see
prepare_net_pose_dataset_v5.py) targeting the generalization gap found this
session: the model only recognized real nets directly when a player was
also in frame."""
from ultralytics import YOLO

DATA_YAML = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_dataset_v5\data.yaml'

if __name__ == '__main__':
    model = YOLO('yolo11n-pose.pt')
    model.train(
        data=DATA_YAML,
        epochs=150,
        imgsz=320,
        batch=8,
        patience=40,
        project=r'C:\Users\jackp\tennis_app\data\10_net_detection',
        name='yolo_pose_run_v5',
        exist_ok=True,
        verbose=True,
    )
