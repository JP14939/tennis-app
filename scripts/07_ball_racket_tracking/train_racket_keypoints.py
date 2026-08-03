"""
Train a racket keypoint regression model on the vision-labeled crops.

5 keypoints per racket: handle, throat, tip, left_edge, right_edge.
Given the tiny dataset (~84 examples), this uses transfer learning — a
frozen ImageNet-pretrained MobileNetV3-Small backbone with a small trainable
regression head — rather than training a CNN from scratch, which would
overfit badly at this scale. This is a proof-of-concept model: expect
meaningful error, and treat results as a first validation of the whole
pipeline (labeling -> training -> inference), not a production-ready model.
"""
import json
import os
import random

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms

random.seed(3)
torch.manual_seed(3)

CROPS_DIR = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\crops'
LABELS_PATH = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\labels.json'
MODEL_OUT = r'C:\Users\jackp\tennis_app\data\09_racket_keypoints\racket_keypoint_model.pt'

IMG_SIZE = 160
POINTS = ['handle', 'throat', 'tip', 'left_edge', 'right_edge']

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def load_examples():
    with open(LABELS_PATH) as f:
        data = json.load(f)
    examples = []
    for item in data['labels']:
        if not item['usable']:
            continue
        img_path = os.path.join(CROPS_DIR, item['crop_file'])
        img = cv2.imread(img_path)
        h, w = img.shape[:2]
        coords = []
        for p in POINTS:
            x, y = item['keypoints'][p]
            coords.append(x / w)
            coords.append(y / h)
        examples.append({'crop_file': item['crop_file'], 'image': img, 'target': np.array(coords, dtype=np.float32)})
    return examples


class RacketKeypointDataset(Dataset):
    def __init__(self, examples, augment=False):
        self.examples = examples
        self.augment = augment
        self.normalize = transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        ex = self.examples[idx]
        img = cv2.resize(ex['image'], (IMG_SIZE, IMG_SIZE))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        target = ex['target'].copy()

        if self.augment and random.random() < 0.5:
            img = np.ascontiguousarray(img[:, ::-1, :])  # horizontal flip
            # flip x coords, and swap left_edge <-> right_edge (indices 3,4 in POINTS)
            for i in range(5):
                target[i * 2] = 1.0 - target[i * 2]
            target = target.reshape(5, 2)
            target[[3, 4]] = target[[4, 3]]
            target = target.reshape(10)

        if self.augment:
            # mild brightness/contrast jitter
            alpha = 1.0 + random.uniform(-0.15, 0.15)
            beta = random.uniform(-15, 15)
            img = np.clip(img.astype(np.float32) * alpha + beta, 0, 255).astype(np.uint8)

        img_t = torch.from_numpy(img).permute(2, 0, 1).float() / 255.0
        img_t = self.normalize(img_t)
        return img_t, torch.from_numpy(target)


def build_model():
    backbone = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    for param in backbone.features.parameters():
        param.requires_grad = False  # freeze — too little data to fine-tune the backbone
    in_features = backbone.classifier[0].in_features
    backbone.classifier = nn.Sequential(
        nn.Linear(in_features, 64),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(64, 10),
        nn.Sigmoid(),  # coords normalised to [0,1]
    )
    return backbone


def main():
    examples = load_examples()
    random.shuffle(examples)
    n_val = max(8, int(len(examples) * 0.15))
    val_examples = examples[:n_val]
    train_examples = examples[n_val:]
    print(f'{len(train_examples)} train, {len(val_examples)} val examples')

    train_ds = RacketKeypointDataset(train_examples, augment=True)
    val_ds = RacketKeypointDataset(val_examples, augment=False)
    train_loader = DataLoader(train_ds, batch_size=8, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=8, shuffle=False)

    model = build_model()
    optimizer = torch.optim.Adam(model.classifier.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.MSELoss()

    best_val_loss = float('inf')
    epochs = 80
    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for imgs, targets in train_loader:
            optimizer.zero_grad()
            preds = model(imgs)
            loss = loss_fn(preds, targets)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * imgs.size(0)
        train_loss /= len(train_ds)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for imgs, targets in val_loader:
                preds = model(imgs)
                val_loss += loss_fn(preds, targets).item() * imgs.size(0)
        val_loss /= len(val_ds)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), MODEL_OUT)

        if epoch % 10 == 0 or epoch == epochs - 1:
            print(f'epoch {epoch:3d}  train_mse={train_loss:.5f}  val_mse={val_loss:.5f}')

    print(f'\nBest val MSE: {best_val_loss:.5f}')
    # Convert normalised MSE to an approximate pixel error for interpretability
    avg_crop_dim = np.mean([ex['image'].shape[0] for ex in examples])
    approx_pixel_rmse = (best_val_loss ** 0.5) * avg_crop_dim
    print(f'Approx pixel RMSE (at avg crop size ~{avg_crop_dim:.0f}px): {approx_pixel_rmse:.1f}px')
    print(f'Model saved to {MODEL_OUT}')


if __name__ == '__main__':
    main()
