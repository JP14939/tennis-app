const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const router = express.Router();

const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');
const PYTHON = path.join(__dirname, '..', '..', '..', 'scripts', 'venv', 'Scripts', 'python.exe');
const CHECKER = path.join(__dirname, '..', '..', '..', 'scripts', '00_utils', 'check_camera_setup.py');
const CHECK_TIMEOUT_MS = 30 * 1000; // just angle inference on a few sampled frames, should be fast
const CALIBRATION_SERVER_URL = 'http://127.0.0.1:5055/check';

fs.mkdirSync(UPLOADS_DIR, { recursive: true });

const upload = multer({
  storage: multer.diskStorage({
    destination: UPLOADS_DIR,
    filename: (req, file, cb) => {
      const ext = path.extname(file.originalname) || '.mp4';
      cb(null, `calib_${Date.now()}_${Math.round(Math.random() * 1e6)}${ext}`);
    },
  }),
  limits: { fileSize: 200 * 1024 * 1024 }, // 200MB
});

// Live snapshots are small compressed JPEGs (quality 0.3, no video), not full
// uploads -- kept in memory rather than written to disk since they're never
// needed after the single proxied request.
const uploadSnapshot = multer({ storage: multer.memoryStorage(), limits: { fileSize: 5 * 1024 * 1024 } });

router.post('/check-setup', upload.single('video'), (req, res) => {
  const cleanup = () => {
    if (req.file) fs.unlink(req.file.path, () => {});
  };

  if (!req.file) {
    return res.status(400).json({ error: 'No video file uploaded (expected field "video")' });
  }

  const proc = spawn(PYTHON, [CHECKER, req.file.path]);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => {
    proc.kill();
  }, CHECK_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    cleanup();

    if (code !== 0) {
      console.error('[check-setup] check_camera_setup.py failed:', stderr.slice(-2000));
      let error = 'Camera setup check failed';
      try { error = JSON.parse(stdout).message || error; } catch { /* stdout wasn't JSON */ }
      return res.status(500).json({ error });
    }

    try {
      const result = JSON.parse(stdout);
      res.json(result);
    } catch (e) {
      console.error('[check-setup] failed to parse output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Camera setup check produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    cleanup();
    console.error('[check-setup] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start camera setup check' });
  });
});

// Live positioning check -- proxies one camera snapshot to the persistent
// calibration_server.py process (see server.js) instead of spawning Python
// fresh. Non-fatal by design: the frontend treats a failure here as "no live
// feedback this cycle", not an error state, so this route degrades to a
// plain error response rather than anything more elaborate.
router.post('/check-setup-live', uploadSnapshot.single('snapshot'), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: 'No snapshot uploaded (expected field "snapshot")' });
  }

  try {
    const response = await fetch(CALIBRATION_SERVER_URL, {
      method: 'POST',
      body: req.file.buffer,
      headers: { 'Content-Type': 'application/octet-stream' },
    });
    const result = await response.json();
    res.status(response.status).json(result);
  } catch (err) {
    res.status(503).json({ error: 'Live calibration server unavailable' });
  }
});

module.exports = router;
