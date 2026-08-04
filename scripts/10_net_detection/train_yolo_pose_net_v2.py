"""
Train a YOLO-pose model on the net-keypoint dataset -- same architecture
that worked for the racket keypoint model (train_yolo_pose_racket.py),
chosen specifically because the direct-regression approach the original
net_keypoints model used failed to generalize (confirmed against real
footage earlier this session).
"""
from ultralytics import YOLO

DATA_YAML = r'C:\Users\jackp\tennis_app\data\10_net_detection\yolo_pose_dataset_v2\data.yaml'

if __name__ == '__main__':
    model = YOLO('yolo11n-pose.pt')
    model.train(
        data=DATA_YAML,
        epochs=150,
        imgsz=320,
        batch=8,
        patience=40,
        project=r'C:\Users\jackp\tennis_app\data\10_net_detection',
        name='yolo_pose_run_v2',
        exist_ok=True,
        verbose=True,
    )
