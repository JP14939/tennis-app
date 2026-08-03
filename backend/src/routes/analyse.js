const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const router = express.Router();

const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');
const PYTHON = path.join(__dirname, '..', '..', '..', 'scripts', 'venv', 'Scripts', 'python.exe');
const MATCHER = path.join(__dirname, '..', 'services', 'pro_matcher.py');
const SHOT_TYPES = ['forehand', 'backhand', 'serve'];
const ANALYSIS_TIMEOUT_MS = 2 * 60 * 1000; // pose extraction on a short clip should finish well within this

fs.mkdirSync(UPLOADS_DIR, { recursive: true });

const upload = multer({
  storage: multer.diskStorage({
    destination: UPLOADS_DIR,
    filename: (req, file, cb) => {
      const ext = path.extname(file.originalname) || '.mp4';
      cb(null, `upload_${Date.now()}_${Math.round(Math.random() * 1e6)}${ext}`);
    },
  }),
  limits: { fileSize: 200 * 1024 * 1024 }, // 200MB
});

router.post('/analyse', upload.single('video'), (req, res) => {
  const cleanup = () => {
    if (req.file) fs.unlink(req.file.path, () => {});
  };

  if (!req.file) {
    return res.status(400).json({ error: 'No video file uploaded (expected field "video")' });
  }

  const { shotType, contactTime } = req.body;
  if (!SHOT_TYPES.includes(shotType)) {
    cleanup();
    return res.status(400).json({ error: `shotType must be one of ${SHOT_TYPES.join(', ')}` });
  }

  const args = [MATCHER, req.file.path, shotType, '--top', '3'];
  if (contactTime !== undefined && contactTime !== '') {
    const t = parseFloat(contactTime);
    if (Number.isNaN(t)) {
      cleanup();
      return res.status(400).json({ error: 'contactTime must be a number (seconds)' });
    }
    args.push('--contact-time', String(t));
  }

  const proc = spawn(PYTHON, args);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => {
    proc.kill();
  }, ANALYSIS_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    cleanup();

    if (code !== 0) {
      console.error('[analyse] pro_matcher.py failed:', stderr.slice(-2000));
      let error = 'Analysis failed';
      try { error = JSON.parse(stdout).error || error; } catch { /* stdout wasn't JSON */ }
      return res.status(500).json({ error });
    }

    try {
      const result = JSON.parse(stdout);
      res.json(result);
    } catch (e) {
      console.error('[analyse] failed to parse pro_matcher.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Analysis produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    cleanup();
    console.error('[analyse] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start analysis process' });
  });
});

module.exports = router;
