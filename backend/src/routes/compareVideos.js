const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const requireAuth = require('../middleware/requireAuth');
const requirePremium = require('../middleware/requirePremium');

const router = express.Router();

const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');
const PYTHON = path.join(__dirname, '..', '..', '..', 'scripts', 'venv', 'Scripts', 'python.exe');
const MATCHER = path.join(__dirname, '..', 'services', 'video_matcher.py');
const SHOT_TYPES = ['forehand', 'backhand', 'serve'];
const COMPARE_TIMEOUT_MS = 3 * 60 * 1000; // two videos processed sequentially, needs more headroom than /analyse

fs.mkdirSync(UPLOADS_DIR, { recursive: true });

const upload = multer({
  storage: multer.diskStorage({
    destination: UPLOADS_DIR,
    filename: (req, file, cb) => {
      const ext = path.extname(file.originalname) || '.mp4';
      cb(null, `upload_${Date.now()}_${Math.round(Math.random() * 1e6)}${ext}`);
    },
  }),
  limits: { fileSize: 200 * 1024 * 1024 }, // 200MB per file
});

router.post('/compare-videos', requireAuth, requirePremium, upload.fields([
  { name: 'reference', maxCount: 1 },
  { name: 'yours', maxCount: 1 },
]), (req, res) => {
  const referenceFile = req.files?.reference?.[0];
  const yoursFile = req.files?.yours?.[0];

  const cleanup = () => {
    if (referenceFile) fs.unlink(referenceFile.path, () => {});
    if (yoursFile) fs.unlink(yoursFile.path, () => {});
  };

  if (!referenceFile || !yoursFile) {
    cleanup();
    return res.status(400).json({ error: 'Both "reference" and "yours" video files are required' });
  }

  const { shotType, contactTimeA, contactTimeB } = req.body;
  if (!SHOT_TYPES.includes(shotType)) {
    cleanup();
    return res.status(400).json({ error: `shotType must be one of ${SHOT_TYPES.join(', ')}` });
  }

  const args = [MATCHER, referenceFile.path, yoursFile.path, shotType];

  for (const [field, flag] of [[contactTimeA, '--contact-a'], [contactTimeB, '--contact-b']]) {
    if (field !== undefined && field !== '') {
      const t = parseFloat(field);
      if (Number.isNaN(t)) {
        cleanup();
        return res.status(400).json({ error: `${flag} value must be a number (seconds)` });
      }
      args.push(flag, String(t));
    }
  }

  const proc = spawn(PYTHON, args);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => {
    proc.kill();
  }, COMPARE_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    cleanup();

    if (code !== 0) {
      console.error('[compare-videos] video_matcher.py failed:', stderr.slice(-2000));
      let error = 'Comparison failed';
      try { error = JSON.parse(stdout).error || error; } catch { /* stdout wasn't JSON */ }
      return res.status(500).json({ error });
    }

    try {
      const result = JSON.parse(stdout);
      res.json(result);
    } catch (e) {
      console.error('[compare-videos] failed to parse video_matcher.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Comparison produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    cleanup();
    console.error('[compare-videos] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start comparison process' });
  });
});

module.exports = router;
