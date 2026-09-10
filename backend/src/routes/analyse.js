const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const db = require('../db');
const optionalAuth = require('../middleware/optionalAuth');
const { currentTier } = require('../utils/tier');
const { PYTHON, DATA_DIR, SCRIPTS_DIR } = require('../config/paths');
const { SHOT_TYPES } = require('../config/shotTypes');
const { finalizeAnalysisResult, USER_CLIPS_DIR } = require('../services/finalizeAnalysisResult');
const { reserveDailyUsageSlot, releaseUsageSlot, LIMIT_EXCEEDED } = require('../utils/usageLimit');
const { runPythonJson } = require('../utils/runPythonJson');
const { safeVideoExt, videoFileFilter } = require('../utils/videoUpload');
const { isTimestampSec, FREE_TIER_DAILY_ANALYSIS_LIMIT } = require('../domain/invariants');
const { rateLimit, ipRateLimit, tryConsume } = require('../middleware/rateLimit');

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
// Second, coarser layer keyed by IP. The per-user limit above bounds any one
// account; this bounds a single attacker cycling through many accounts (each
// signup gets its own fresh per-user allowance and its own FREE_DAILY_LIMIT)
// from one connection -- the residual gap called out in PRE_RELEASE_CHECK.md
// A1. Deliberately generous: a household or club on one NAT'd IP with several
// real players should never reach it, but it still caps the spawn count from
// any single origin well below what the single hosted box can be flooded with.
const analyseIpLimiter = ipRateLimit('analyse-ip', 80);

// Guests (no account) can run an analysis so the onboarding flow can show the
// score BEFORE asking for a signup (see docs/plans/onboarding_plan.md, "gate
// at the reveal"). A guest run still spawns MediaPipe on the single box and
// isn't covered by the per-account FREE_TIER_DAILY_ANALYSIS_LIMIT, so it gets
// its own hard, low per-IP ceiling -- consumed inline in the handler (not as
// middleware) so it's only spent once a request has cleared every validation
// gate and is actually about to spawn Python; a fat-fingered file pick costs
// nothing. This does NOT fully close the "capped free user drops their token
// for a couple more runs" gap (2 free + 2 guest per IP), but the guest ceiling
// is low, IP-keyed, and only reachable by someone deliberately rotating IPs
// for a handful of extra spawns -- not worth engineering against on a
// single-box deploy.
const GUEST_ANALYSE_WINDOW_MS = 24 * 60 * 60 * 1000;
const GUEST_ANALYSE_MAX = 2;

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
// Shared with routes/highlights.js and integrityChecks.js -- see the comment
// on FREE_TIER_DAILY_ANALYSIS_LIMIT in domain/invariants.js.
const FREE_DAILY_LIMIT = FREE_TIER_DAILY_ANALYSIS_LIMIT;

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

router.post('/analyse', optionalAuth, analyseIpLimiter, analyseLimiter, upload.single('video'), async (req, res) => {
  const isGuest = !req.user;
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

  // Guests: consume one of the 2/24h-per-IP slots now that the request has
  // cleared every validation gate above and is genuinely about to spawn
  // Python. `code: 'GUEST_LIMIT'` lets the client show a "create an account"
  // screen instead of a generic failure. See GUEST_ANALYSE_MAX's comment for
  // the residual "drop the token for a couple more runs" gap.
  if (isGuest && !tryConsume(`analyse-guest:${req.ip}`, GUEST_ANALYSE_WINDOW_MS, GUEST_ANALYSE_MAX)) {
    cleanup();
    return res.status(429).json({
      error: 'Create a free account to keep analysing — guests get 2 per day.',
      code: 'GUEST_LIMIT',
    });
  }

  // Premium accounts are unlimited; free-tier accounts are capped per day;
  // guests don't touch analysis_usage at all (no user row to key it to).
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
  const isFreeUser = !isGuest && currentTier(req.user.id) === 'free';
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
  const handed = isGuest ? undefined : db.prepare('SELECT handed FROM users WHERE id = ?').get(req.user.id)?.handed;

  // --top 1: results only ever show the single best match now (the pro
  // identity / "other close matches" list was removed -- most pro-DB clips
  // aren't identified, so a "matched to Forehand Technique #142" caption read
  // as broken). Asking for fewer also skips 2x per-match coaching-tip
  // selection in compare_swing.py.
  const args = [MATCHER, req.file.path, shotType, '--top', '1'];
  if (parsedContactTime !== undefined) {
    args.push('--contact-time', String(parsedContactTime));
  }
  if (viewDirectionHint === 'front' || viewDirectionHint === 'back') {
    args.push('--view-direction-hint', viewDirectionHint);
  }
  // The matcher returns `result.view_gate` (roadmap 1a behind-the-baseline
  // check) and the frontend warns on it; the match still runs. To promote it
  // to a hard reject, set RALLYMAX_ENFORCE_VIEW_GATE=1 in backend/.env on the
  // server -- compare_swing.py then raises and the error surfaces via the
  // nonzero_exit branch below.
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
    // The matcher exits non-zero with {error, code?} JSON on stdout. `code` is
    // set for structured rejections the app handles specially -- currently only
    // VIEW_NOT_USABLE (behind-the-baseline view gate), which drives a
    // 'check your camera setup' screen instead of a generic failure.
    let nonzeroError = 'Analysis failed';
    let nonzeroCode = null;
    if (err.kind === 'nonzero_exit') {
      try {
        const parsed = JSON.parse(err.stdout);
        nonzeroError = parsed.error || nonzeroError;
        nonzeroCode = parsed.code || null;
      } catch { /* keep defaults */ }
    }
    const messages = {
      spawn_failed: 'Failed to start analysis process',
      invalid_json: 'Analysis produced invalid output',
      timeout: 'Analysis timed out — try a shorter clip',
      nonzero_exit: nonzeroError,
    };
    const body = { error: messages[err.kind] || 'Analysis failed' };
    if (nonzeroCode) body.code = nonzeroCode;
    return res.status(500).json(body);
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
      // Skipped for guests -- this is training data keyed to a real user's
      // manual contact mark; an anonymous one adds noise, not signal.
      if (!isGuest && persistedOk && contactTime !== undefined && contactTime !== '') {
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
    // persistAndCrop can partially write into USER_CLIPS_DIR/<uploadId>
    // before failing (e.g. disk full mid-copy on the cropped variant) --
    // unlike compareVideos.js's equivalent path, which removes its whole
    // per-job directory on a partial persistAndCrop failure, this had no
    // such cleanup, leaking an orphaned/partial directory under
    // USER_CLIPS_DIR forever on every post-processing failure.
    const uploadId = path.parse(req.file.filename).name;
    fs.rmSync(path.join(USER_CLIPS_DIR, uploadId), { recursive: true, force: true });
    console.error(`[analyse] post-processing failed after a successful analysis: ${err.message}`);
    if (!res.headersSent) {
      res.status(500).json({ error: 'Analysis succeeded but the response could not be completed' });
    }
  }
});

module.exports = router;
