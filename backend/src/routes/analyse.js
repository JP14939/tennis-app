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
const { finalizeAnalysisResult, USER_CLIPS_DIR } = require('../services/finalizeAnalysisResult');
const { reserveDailyUsageSlot, releaseUsageSlot, LIMIT_EXCEEDED } = require('../utils/usageLimit');
const { runPythonJson } = require('../utils/runPythonJson');
const { safeVideoExt, videoFileFilter } = require('../utils/videoUpload');
const { isTimestampSec } = require('../domain/invariants');
const { rateLimit } = require('../middleware/rateLimit');

const router = express.Router();

// FREE_DAILY_LIMIT below only caps SUCCESSFUL saved-to-usage analyses --
// releaseUsageSlot() un-reserves a failed one, by design, so a legitimate
// user isn't charged for a request that errored through no fault of their
// own. That means nothing was capping the number of *attempts*: a free
// account submitting a video engineered to fail pose extraction (or a
// premium account with no daily cap at all) could spawn the real
// MediaPipe subprocess an unlimited number of times, exhausting the
// single-box hosted deploy's CPU/memory -- the same resource-exhaustion
// shape that already motivated requiring auth on calibration.js's
// /check-setup. Keyed by user id (not IP) so it can't be sidestepped by
// rotating accounts behind the same connection the way an IP-keyed limit
// could be; generous enough that no real usage pattern should ever hit it.
const analyseLimiter = rateLimit({ windowMs: 10 * 60 * 1000, max: 30, keyPrefix: 'analyse', keyGenerator: (req) => req.user?.id ?? req.ip });

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

fs.mkdirSync(UPLOADS_DIR, { recursive: true });
fs.mkdirSync(USER_CLIPS_DIR, { recursive: true });

const upload = multer({
  storage: multer.diskStorage({
    destination: UPLOADS_DIR,
    filename: (req, file, cb) => {
      cb(null, `upload_${Date.now()}_${Math.round(Math.random() * 1e6)}${safeVideoExt(file.originalname)}`);
    },
  }),
  fileFilter: videoFileFilter,
  limits: { fileSize: 200 * 1024 * 1024 }, // 200MB
});

router.post('/analyse', requireAuth, analyseLimiter, upload.single('video'), async (req, res) => {
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
    // isTimestampSec (not just isFinite) so negative values and values past
    // MAX_VIDEO_SECONDS 400 here too, same as any other video-offset field
    // (e.g. coach.js's timestampSec) -- these used to only reject
    // Infinity/-Infinity/NaN, letting a negative or absurdly large contact
    // time reach the Python subprocess and corrupt the contact-frame
    // alignment instead of failing cleanly.
    if (!isTimestampSec(parsedContactTime)) {
      cleanup();
      return res.status(400).json({ error: 'contactTime must be a number of seconds between 0 and the video length' });
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

  // Left-handed players' swings are the mirror image of the (all right-handed)
  // pro database -- compare_swing.py flips the uploaded trajectory before the
  // DTW match when told to. Read server-side rather than trusting the client.
  const handed = db.prepare('SELECT handed FROM users WHERE id = ?').get(req.user.id)?.handed;

  const args = [MATCHER, req.file.path, shotType, '--top', '3'];
  if (parsedContactTime !== undefined) {
    args.push('--contact-time', String(parsedContactTime));
  }
  if (viewDirectionHint === 'front' || viewDirectionHint === 'back') {
    args.push('--view-direction-hint', viewDirectionHint);
  }
  if (handed === 'left') {
    args.push('--handedness', 'left');
  }

  let result;
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
    result = await runPythonJson(PYTHON, args, { timeoutMs: ANALYSIS_TIMEOUT_MS, label: 'pro_matcher.py' });
  } catch (err) {
    // The Python matcher itself never ran to completion -- this free-tier
    // slot bought nothing, so give it back. (Anything that fails AFTER this
    // point, in the block below, means the actual analysis succeeded and
    // must NOT refund the slot -- see that block's own catch.)
    cleanup();
    releaseUsageSlot(db, usageRowId);
    console.error(`[analyse] ${err.message}`, err.stderr?.slice(-2000));
    const messages = {
      spawn_failed: 'Failed to start analysis process',
      invalid_json: 'Analysis produced invalid output',
      timeout: 'Analysis timed out — try a shorter clip',
      nonzero_exit: (() => {
        try { return JSON.parse(err.stdout).error; } catch { return 'Analysis failed'; }
      })(),
    };
    return res.status(500).json({ error: messages[err.kind] || 'Analysis failed' });
  }

  try {
    // Analysis succeeded -- keep the user's video (used to be deleted
    // here) and crop it for the sync-compare screen. Cropping failure is
    // non-fatal: croppedPath just comes back null and the screen falls
    // back to the original video. deleteSource:true -- req.file.path is a
    // throwaway multer upload, gone once persisted (unlike
    // highlights.js's per-shot analyze endpoint, whose source is a
    // persisted rally clip other shots still need).
    const uploadId = path.parse(req.file.filename).name;
    const { originalPath, persistedOk } = await finalizeAnalysisResult(result, {
      sourcePath: req.file.path,
      destDir: path.join(USER_CLIPS_DIR, uploadId),
      shotType,
      deleteSource: true,
    });

    res.json(result);

    // Fire-and-forget, AFTER the response -- see CONTACT_FRAME_LOGGER's
    // comment above. persistedOk guards against logging against a
    // missing/empty file; contactTime was already validated as a real
    // number earlier in this handler (or this request would have 400'd),
    // so no need to re-validate here. Wrapped in its own try/catch: a
    // synchronous throw from spawn() here (distinct from the 'error' event
    // handled below, which fires async) happens AFTER res.json() above has
    // already sent the response -- left uncaught, it used to fall into the
    // outer catch, which called res.status(500)... a second time, throwing
    // ERR_HTTP_HEADERS_SENT with nothing to catch it (an unhandled
    // exception that takes the whole process down), and also wrongly
    // released a usage slot for an analysis that had already succeeded.
    try {
      if (persistedOk && contactTime !== undefined && contactTime !== '') {
        const bgProc = spawn(PYTHON, [CONTACT_FRAME_LOGGER, originalPath, String(parseFloat(contactTime))], {
          detached: true, stdio: 'ignore',
        });
        // Without this, a spawn failure (e.g. ENOENT on the script path, or
        // EMFILE under load) fires Node's 'error' event with no listener,
        // which throws and crashes the ENTIRE server process for every
        // concurrent user -- not just this request, since this spawn happens
        // fire-and-forget after the response was already sent. Same shape of
        // bug runPythonJson.js's header comment describes fixing for
        // foreground calls; this detached call bypasses that helper entirely.
        bgProc.on('error', (err) => {
          console.error('[analyse] contact-frame logger failed to start:', err.message);
        });
        bgProc.unref();
      }
    } catch (err) {
      console.error('[analyse] contact-frame logger failed to start:', err.message);
    }
  } catch (err) {
    // The Python matcher already produced a real result by this point --
    // this catch only covers post-processing (persisting/cropping the
    // user's own clip, resolving the pro clip URL). Unlike the block above,
    // this must NOT release the usage slot: doing the real, expensive work
    // successfully and then hitting e.g. a full disk on the cheap local
    // file-copy step is not a failed analysis, and refunding the slot here
    // would let a persistent local infra issue (USER_CLIPS_DIR filling up)
    // silently give every free user unlimited real analyses for as long as
    // it lasts.
    cleanup();
    console.error(`[analyse] post-processing failed after a successful analysis: ${err.message}`);
    if (!res.headersSent) {
      res.status(500).json({ error: 'Analysis succeeded but the response could not be completed' });
    }
  }
});

module.exports = router;
