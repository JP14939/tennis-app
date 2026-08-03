"""
Train a YOLO-pose model on the racket keypoint dataset — purpose-built
keypoint architecture, testing whether it does better than the earlier
direct-coordinate-regression model at this same (small) data scale.
"""
from ultralytics import YOLO

DATA_YAML = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\yolo_pose_dataset\data.yaml'

if __name__ == '__main__':
    model = YOLO('yolo11n-pose.pt')  # pretrained, nano — reinitializes pose head for our 5-point skeleton
    model.train(
        data=DATA_YAML,
        epochs=150,
        imgsz=320,
        batch=8,
        patience=40,
        project=r'C:\Users\jackp\tennis_app\data\09_racket_keypoints',
        name='yolo_pose_run',
        exist_ok=True,
        verbose=True,
    )
