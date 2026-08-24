const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const requireAuth = require('../middleware/requireAuth');
const { SCRIPTS_DIR, PYTHON } = require('../config/paths');
const { runPythonJson } = require('../utils/runPythonJson');
const { safeVideoExt, videoFileFilter } = require('../utils/videoUpload');

const router = express.Router();

const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');
const CHECKER = path.join(SCRIPTS_DIR, '00_utils', 'check_camera_setup.py');
const CHECK_TIMEOUT_MS = 30 * 1000; // just angle inference on a few sampled frames, should be fast
const CALIBRATION_SERVER_URL = 'http://127.0.0.1:5055/check';

fs.mkdirSync(UPLOADS_DIR, { recursive: true });

const upload = multer({
  storage: multer.diskStorage({
    destination: UPLOADS_DIR,
    filename: (req, file, cb) => {
      cb(null, `calib_${Date.now()}_${Math.round(Math.random() * 1e6)}${safeVideoExt(file.originalname)}`);
    },
  }),
  fileFilter: videoFileFilter,
  limits: { fileSize: 200 * 1024 * 1024 }, // 200MB
});

// Live snapshots are small compressed JPEGs (quality 0.3, no video), not full
// uploads -- kept in memory rather than written to disk since they're never
// needed after the single proxied request.
const uploadSnapshot = multer({ storage: multer.memoryStorage(), limits: { fileSize: 5 * 1024 * 1024 } });

// requireAuth: this spawns a real CPU-heavy Python process per request on a
// 200MB upload -- left open to unauthenticated callers it's a trivial
// resource-exhaustion DoS on the single-box hosted deploy.
router.post('/check-setup', requireAuth, upload.single('video'), async (req, res) => {
  const cleanup = () => {
    if (req.file) fs.unlink(req.file.path, () => {});
  };

  if (!req.file) {
    return res.status(400).json({ error: 'No video file uploaded (expected field "video")' });
  }

  try {
    const result = await runPythonJson(PYTHON, [CHECKER, req.file.path], {
      timeoutMs: CHECK_TIMEOUT_MS,
      label: 'check_camera_setup.py',
    });
    res.json(result);
  } catch (err) {
    console.error(`[check-setup] ${err.message}`, err.stderr?.slice(-2000));
    const messages = {
      spawn_failed: 'Failed to start camera setup check',
      invalid_json: 'Camera setup check produced invalid output',
      nonzero_exit: (() => {
        try { return JSON.parse(err.stdout).message; } catch { return 'Camera setup check failed'; }
      })(),
    };
    res.status(500).json({ error: messages[err.kind] || 'Camera setup check failed' });
  } finally {
    cleanup();
  }
});

// Live positioning check -- proxies one camera snapshot to the persistent
// calibration_server.py process (see server.js) instead of spawning Python
// fresh. Non-fatal by design: the frontend treats a failure here as "no live
// feedback this cycle", not an error state, so this route degrades to a
// plain error response rather than anything more elaborate.
router.post('/check-setup-live', requireAuth, uploadSnapshot.single('snapshot'), async (req, res) => {
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
    // Was swallowed entirely -- the caller got a generic 503 and the server
    // kept no record of which failure it was (process down, malformed JSON,
    // network fault), leaving the live-calibration loop undiagnosable. Every
    // sibling catch in this file logs before responding; this one didn't.
    console.error('[check-setup-live] calibration server request failed:', err.message);
    res.status(503).json({ error: 'Live calibration server unavailable' });
  }
});

module.exports = router;
