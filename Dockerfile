# Single container running both the Node backend and its Python ML pipeline
# (Node spawns Python child processes for inference, including the
# persistent calibration_server.py) -- matches the existing architecture
# exactly rather than splitting into separate services.
FROM python:3.13-slim

# Node 22 via NodeSource (matches the version this app was built against),
# plus system libs OpenCV/mediapipe/sounddevice need at runtime and
# build-essential for any package here without a prebuilt Linux wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg build-essential \
    libgl1 libglib2.0-0 libportaudio2 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps -- installed into a venv at scripts/venv, the exact layout
# backend/src/config/paths.js and every script already expect
# (scripts/venv/bin/python3 on Linux, scripts/venv/Scripts/python.exe on
# Windows dev).
COPY scripts/requirements.txt scripts/requirements.txt
RUN python3 -m venv scripts/venv \
    && scripts/venv/bin/pip install --no-cache-dir -r scripts/requirements.txt

# Pretrained COCO weights (yolo11n.pt / yolo11n-pose.pt) are gitignored --
# not fine-tuned, not original work, auto-downloaded by ultralytics on first
# use. Pre-download them at build time instead of the container's first real
# request stalling on it (or failing if the deployed host has no outbound
# internet).
RUN scripts/venv/bin/python -c "from ultralytics import YOLO; YOLO('yolo11n.pt'); YOLO('yolo11n-pose.pt')"

# Node deps
COPY backend/package.json backend/package-lock.json backend/
RUN cd backend && npm ci --omit=dev

# App code (data/ and backend/data/app.db are NOT copied in -- see
# DEPLOY.md; both are gitignored and mounted as volumes at runtime instead)
COPY backend/ backend/
COPY scripts/ scripts/

EXPOSE 5000
CMD ["node", "backend/src/server.js"]
