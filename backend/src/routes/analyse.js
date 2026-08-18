const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const db = require('../db');
const optionalAuth = require('../middleware/optionalAuth');
const { currentTier } = require('../utils/tier');
const { PYTHON, DATA_DIR, SCRIPTS_DIR } = require('../config/paths');
const { persistAndCrop, croppedProClipPath, toUrl, PRO_CLIPS_DIR, PRO_CLIPS_CROPPED_DIR } = require('../utils/videoCrop');
const { reserveDailyUsageSlot, releaseUsageSlot, LIMIT_EXCEEDED } = require('../utils/usageLimit');

const router = express.Router();

const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');
const MATCHER = path.join(__dirname, '..', 'services', 'pro_matcher.py');
// Free, ongoing training data for the previously-untrained contact-frame
// detector (see scripts/07_ball_racket_tracking/contact_frame_training_log.py)
// -- spawned detached, AFTER the response is sent, never awaited or on the
// response's critical path. Measured this session at ~5s of real work;
// running it inline added that directly to every user's response time for
// a step that gives them nothing back, so it's fully decoupled instead.
const CONTACT_FRAME_LOGGER = path.join(SCRIPTS_DIR, '07_ball_racket_tracking', 'log_user_contact_frame_cli.py');
const SHOT_TYPES = ['forehand', 'backhand', 'serve'];
const ANALYSIS_TIMEOUT_MS = 2 * 60 * 1000; // pose extraction on a short clip should finish well within this
const FREE_DAILY_LIMIT = 2;
// Where the user's uploaded video is kept after analysis (used to be
// deleted immediately -- the sync-compare screen needs it to still exist).
const USER_CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'user_clips');

fs.mkdirSync(UPLOADS_DIR, { recursive: true });
fs.mkdirSync(USER_CLIPS_DIR, { recursive: true });

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

router.post('/analyse', optionalAuth, upload.single('video'), (req, res) => {
  const cleanup = () => {
    if (req.file) fs.unlink(req.file.path, () => {});
  };

  if (!req.file) {
    return res.status(400).json({ error: 'No video file uploaded (expected field "video")' });
  }

  const { shotType, contactTime, viewDirectionHint } = req.body;
  if (!SHOT_TYPES.includes(shotType)) {
    cleanup();
    return res.status(400).json({ error: `shotType must be one of ${SHOT_TYPES.join(', ')}` });
  }

  // Guests and premium accounts are unlimited -- only identifiable free-tier
  // accounts are capped, and only checked (not forced to log in) so this
  // doesn't change today's unauthenticated behavior for anyone else.
  //
  // The count-check and the usage INSERT used to happen up to
  // ANALYSIS_TIMEOUT_MS (2 minutes) apart -- check here, insert only after
  // the spawned Python process finished -- which let several concurrent
  // requests from the same user all pass the check before any of them
  // recorded usage, exceeding FREE_DAILY_LIMIT. reserveDailyUsageSlot()
  // closes that window by checking-and-inserting in one synchronous
  // (better-sqlite3 calls are sync) transaction, right here, before any
  // async work starts. If the analysis later fails, the reservation is
  // released so a failed attempt still doesn't count against the user --
  // same behavior as before, just race-free.
  const isFreeUser = req.user && currentTier(req.user.id) === 'free';
  let usageRowId = null;
  if (isFreeUser) {
    const reserved = reserveDailyUsageSlot(db, req.user.id, FREE_DAILY_LIMIT);
    if (reserved === LIMIT_EXCEEDED) {
      cleanup();
      return res.status(403).json({
        error: `Free plan is limited to ${FREE_DAILY_LIMIT} analyses per day — upgrade to Premium for unlimited.`,
        code: 'DAILY_LIMIT',
      });
    }
    usageRowId = reserved;
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
  if (viewDirectionHint === 'front' || viewDirectionHint === 'back') {
    args.push('--view-direction-hint', viewDirectionHint);
  }

  const proc = spawn(PYTHON, args);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => {
    proc.kill();
  }, ANALYSIS_TIMEOUT_MS);

  proc.on('close', async (code) => {
    clearTimeout(timeout);

    if (code !== 0) {
      cleanup();
      releaseUsageSlot(db, usageRowId);
      console.error('[analyse] pro_matcher.py failed:', stderr.slice(-2000));
      let error = 'Analysis failed';
      try { error = JSON.parse(stdout).error || error; } catch { /* stdout wasn't JSON */ }
      return res.status(500).json({ error });
    }

    try {
      const result = JSON.parse(stdout);

      // Analysis succeeded -- keep the user's video (used to be deleted
      // here) and crop it for the sync-compare screen. Cropping failure is
      // non-fatal: croppedPath just comes back null and the screen falls
      // back to the original video.
      const uploadId = path.parse(req.file.filename).name;
      const { originalPath, croppedPath } = await persistAndCrop(req.file.path, path.join(USER_CLIPS_DIR, uploadId));

      // Defensive check -- don't hand back a URL that 404s or points at a
      // truncated file (e.g. an interrupted upload on a bad connection).
      // Doesn't fix whatever the underlying cause is, but turns a silent
      // broken video into an honest "unavailable" instead of a black box
      // with no error the frontend has no way to explain.
      let persistedOk = false;
      try {
        persistedOk = fs.statSync(originalPath).size > 0;
      } catch { /* file missing */ }
      if (!persistedOk) {
        console.error('[analyse] persisted user clip missing or empty:', originalPath);
      }

      result.user_clip_url = persistedOk ? toUrl('/user-clips', USER_CLIPS_DIR, originalPath) : null;
      result.user_clip_cropped_url = persistedOk ? toUrl('/user-clips', USER_CLIPS_DIR, croppedPath) : null;

      const top = result.matches?.[0];
      if (top?.clip_path) {
        // pro_database.json stores clip_path relative to PRO_CLIPS_DIR (not
        // an absolute path -- it used to be, which broke the moment the
        // database built on one machine got deployed to another, since
        // toUrl()'s path.relative() only makes sense against a real path on
        // the *current* OS). Resolve to a real absolute path here, once,
        // right where it's actually used.
        const proClipAbsPath = path.join(PRO_CLIPS_DIR, top.clip_path);
        const proCroppedPath = await croppedProClipPath(proClipAbsPath, top.shot_type || shotType);
        top.pro_clip_url = toUrl('/pro-clips', PRO_CLIPS_DIR, proClipAbsPath);
        top.pro_clip_cropped_url = toUrl('/pro-clips-cropped', PRO_CLIPS_CROPPED_DIR, proCroppedPath);
      }

      res.json(result);

      // Fire-and-forget, AFTER the response -- see CONTACT_FRAME_LOGGER's
      // comment above. persistedOk guards against logging against a
      // missing/empty file; contactTime was already validated as a real
      // number earlier in this handler (or this request would have 400'd),
      // so no need to re-validate here.
      if (persistedOk && contactTime !== undefined && contactTime !== '') {
        const bgProc = spawn(PYTHON, [CONTACT_FRAME_LOGGER, originalPath, String(parseFloat(contactTime))], {
          detached: true, stdio: 'ignore',
        });
        bgProc.unref();
      }
    } catch (e) {
      cleanup();
      releaseUsageSlot(db, usageRowId);
      console.error('[analyse] failed to parse pro_matcher.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Analysis produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    cleanup();
    releaseUsageSlot(db, usageRowId);
    console.error('[analyse] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start analysis process' });
  });
});

module.exports = router;
