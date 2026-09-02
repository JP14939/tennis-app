"""Phase 3: fine-tune the ball detector on real labeled swing footage (see
prepare_ball_yolo_dataset.py). Same Ultralytics pattern as
train_yolo_pose_racket.py / scripts/10_net_detection's train_yolo_pose_net_v5.py,
starting from the same yolo11n.pt base the production pipeline already uses
(racket_tracker.get_model()) rather than a pose variant, since this is a
plain bounding-box target, not keypoints."""
import os

from ultralytics import YOLO

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
DATA_YAML = os.path.join(REPO_ROOT, 'data', '10b_ball_detection', 'yolo_dataset_v1', 'data.yaml')
PROJECT_DIR = os.path.join(REPO_ROOT, 'data', '10b_ball_detection')
BASE_WEIGHTS = os.path.join(REPO_ROOT, 'yolo11n.pt')  # already-downloaded base, same one production uses

if __name__ == '__main__':
    model = YOLO(os.path.abspath(BASE_WEIGHTS))
    model.train(
        data=os.path.abspath(DATA_YAML),
        epochs=150,
        imgsz=320,
        batch=8,
        patience=40,
        project=os.path.abspath(PROJECT_DIR),
        name='yolo_ball_run_v1',
        exist_ok=True,
        verbose=True,
    )
