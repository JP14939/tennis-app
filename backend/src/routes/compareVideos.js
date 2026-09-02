const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const requireAuth = require('../middleware/requireAuth');
const requirePremium = require('../middleware/requirePremium');
const { PYTHON, DATA_DIR } = require('../config/paths');
const { SHOT_TYPES } = require('../config/shotTypes');
const { persistAndCrop, toUrl } = require('../utils/videoCrop');
const { runPythonJson } = require('../utils/runPythonJson');
const { safeVideoExt, videoFileFilter } = require('../utils/videoUpload');
const { isTimestampSec } = require('../domain/invariants');
const { rateLimit } = require('../middleware/rateLimit');

const router = express.Router();

// Same resource-exhaustion reasoning as analyse.js's analyseLimiter -- two
// full videos processed sequentially per request, requirePremium doesn't cap
// how many times a premium account can trigger it. Keyed by user id.
const compareLimiter = rateLimit({ windowMs: 10 * 60 * 1000, max: 15, keyPrefix: 'compare-videos', keyGenerator: (req) => req.user?.id ?? req.ip });

const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');
const MATCHER = path.join(__dirname, '..', 'services', 'video_matcher.py');
const COMPARE_TIMEOUT_MS = 3 * 60 * 1000; // two videos processed sequentially, needs more headroom than /analyse
// Both uploaded videos used to be deleted right after comparison -- kept
// here now so the sync-compare screen can play them back afterward.
const COMPARISON_CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'comparison_clips');

fs.mkdirSync(UPLOADS_DIR, { recursive: true });
fs.mkdirSync(COMPARISON_CLIPS_DIR, { recursive: true });

const upload = multer({
  storage: multer.diskStorage({
    destination: UPLOADS_DIR,
    filename: (req, file, cb) => {
      cb(null, `upload_${Date.now()}_${Math.round(Math.random() * 1e6)}${safeVideoExt(file.originalname)}`);
    },
  }),
  fileFilter: videoFileFilter,
  limits: { fileSize: 200 * 1024 * 1024 }, // 200MB per file
});

router.post('/compare-videos', requireAuth, requirePremium, compareLimiter, upload.fields([
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
      // isTimestampSec (not just isFinite) so negative values and values past
      // MAX_VIDEO_SECONDS 400 here too, same as any other video-offset field
      // -- see analyse.js's contactTime for the matching fix.
      if (!isTimestampSec(t)) {
        cleanup();
        return res.status(400).json({ error: `${flag} value must be a number of seconds between 0 and the video length` });
      }
      args.push(flag, String(t));
    }
  }

  runPythonJson(PYTHON, args, { timeoutMs: COMPARE_TIMEOUT_MS, label: 'video_matcher.py' })
    .then(async (result) => {
      // Comparison succeeded -- keep both videos (used to be deleted here)
      // and crop each for the sync-compare screen. Cropping failure is
      // non-fatal per video; the screen falls back to the original.
      const jobId = `${Date.now()}_${Math.round(Math.random() * 1e6)}`;
      const [ref, yours] = await Promise.all([
        persistAndCrop(referenceFile.path, path.join(COMPARISON_CLIPS_DIR, jobId, 'reference')),
        persistAndCrop(yoursFile.path, path.join(COMPARISON_CLIPS_DIR, jobId, 'yours')),
      ]);
      result.reference_clip_url = toUrl('/comparison-clips', COMPARISON_CLIPS_DIR, ref.originalPath);
      result.reference_clip_cropped_url = toUrl('/comparison-clips', COMPARISON_CLIPS_DIR, ref.croppedPath);
      result.your_clip_url = toUrl('/comparison-clips', COMPARISON_CLIPS_DIR, yours.originalPath);
      result.your_clip_cropped_url = toUrl('/comparison-clips', COMPARISON_CLIPS_DIR, yours.croppedPath);

      res.json(result);
    })
    .catch((err) => {
      cleanup();
      console.error(`[compare-videos] ${err.message}`, err.stderr?.slice(-2000));
      const messages = {
        spawn_failed: 'Failed to start comparison process',
        invalid_json: 'Comparison produced invalid output',
        nonzero_exit: (() => {
          try { return JSON.parse(err.stdout).error; } catch { return 'Comparison failed'; }
        })(),
      };
      res.status(500).json({ error: messages[err.kind] || 'Comparison failed' });
    });
});

module.exports = router;
