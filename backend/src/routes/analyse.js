const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { currentTier } = require('../utils/tier');
const { PYTHON, DATA_DIR, SCRIPTS_DIR } = require('../config/paths');
const { SHOT_TYPES } = require('../config/shotTypes');
const { persistAndCrop, croppedProClipPath, toUrl, PRO_CLIPS_DIR, PRO_CLIPS_CROPPED_DIR } = require('../utils/videoCrop');
const { reserveDailyUsageSlot, releaseUsageSlot, LIMIT_EXCEEDED } = require('../utils/usageLimit');
const { runPythonJson } = require('../utils/runPythonJson');

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

router.post('/analyse', requireAuth, upload.single('video'), async (req, res) => {
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
  // Validated before the usage-slot reservation below so a malformed
  // contactTime 400s without burning one of the free tier's limited daily
  // slots -- this used to be checked after reservation and had no release
  // on this particular early-return path, silently costing a free user a
  // slot for a request that never ran an analysis.
  let parsedContactTime;
  if (contactTime !== undefined && contactTime !== '') {
    parsedContactTime = parseFloat(contactTime);
    if (Number.isNaN(parsedContactTime)) {
      cleanup();
      return res.status(400).json({ error: 'contactTime must be a number (seconds)' });
    }
  }

  // Premium accounts are unlimited -- only free-tier accounts are capped.
  // /analyse requires auth (requireAuth above) specifically so this can't be
  // bypassed by dropping the Authorization header: an earlier optionalAuth
  // version let a capped free user do exactly that and get unlimited
  // analyses as an "anonymous" caller, since req.user was simply absent.
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
  const isFreeUser = currentTier(req.user.id) === 'free';
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
  if (parsedContactTime !== undefined) {
    args.push('--contact-time', String(parsedContactTime));
  }
  if (viewDirectionHint === 'front' || viewDirectionHint === 'back') {
    args.push('--view-direction-hint', viewDirectionHint);
  }

  try {
    // NOT parallelized with Promise.all, despite persistAndCrop not reading
    // `result` -- looks independent by data-flow alone, but persistAndCrop
    // copies-then-unlinks req.file.path (videoCrop.js's EXDEV workaround),
    // and the matcher subprocess below is given that same path as an argv
    // string and opens/reads it itself over its own runtime. Running them
    // concurrently would race a synchronous unlink against a Python
    // interpreter + MediaPipe import + video-open that's slower by a wide
    // margin, i.e. the file being deleted out from under the still-running
    // matcher on essentially every request, not as a rare edge case.
    const result = await runPythonJson(PYTHON, args, { timeoutMs: ANALYSIS_TIMEOUT_MS, label: 'pro_matcher.py' });

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
  } catch (err) {
    cleanup();
    releaseUsageSlot(db, usageRowId);
    console.error(`[analyse] ${err.message}`, err.stderr?.slice(-2000));
    const messages = {
      spawn_failed: 'Failed to start analysis process',
      invalid_json: 'Analysis produced invalid output',
      nonzero_exit: (() => {
        try { return JSON.parse(err.stdout).error; } catch { return 'Analysis failed'; }
      })(),
    };
    res.status(500).json({ error: messages[err.kind] || 'Analysis failed' });
  }
});

module.exports = router;
