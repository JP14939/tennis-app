const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const requirePremium = require('../middleware/requirePremium');
const { currentTier } = require('../utils/tier');
const { PYTHON, DATA_DIR } = require('../config/paths');
const { sendPushNotification } = require('../utils/pushNotifications');
const { runPythonJson } = require('../utils/runPythonJson');
const { resolveJobFailureMessage } = require('../utils/resolveJobFailureMessage');
const { safeVideoExt, videoFileFilter } = require('../utils/videoUpload');
const { reserveDailyUsageSlot, releaseUsageSlot, LIMIT_EXCEEDED } = require('../utils/usageLimit');
const { finalizeAnalysisResult, USER_CLIPS_DIR } = require('../services/finalizeAnalysisResult');
const {
  OUTCOME_TAGS, MAX_LENGTHS, isOutcomeTag, isBoundaryNote, isText,
} = require('../domain/invariants');
const { validate, optional, oneOfMessage } = require('../validation/validateBody');
const { rateLimit } = require('../middleware/rateLimit');

const router = express.Router();

// Same resource-exhaustion reasoning as analyse.js's analyseLimiter -- a full
// match video (up to 2GB) runs pose extraction for up to JOB_TIMEOUT_MS (1
// hour) per request, and requirePremium alone doesn't cap how many of these
// a premium account can queue. Keyed by user id.
const highlightsUploadLimiter = rateLimit({ windowMs: 10 * 60 * 1000, max: 5, keyPrefix: 'highlights-upload', keyGenerator: (req) => req.user?.id ?? req.ip });

const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');
// Persistent -- unlike uploads/, rally clips must outlive the request that
// created them (the user reviews/archives them later), so nothing cleans
// this up after each job the way analyse.js/compareVideos.js clean up
// their ephemeral uploads.
const CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'highlight_clips');
const DETECTOR = path.join(__dirname, '..', 'services', 'rally_detector.py');
// Same script /api/analyse spawns -- a shot picked from an already-detected
// rally clip is analyzed through the identical pipeline, not a second one.
const MATCHER = path.join(__dirname, '..', 'services', 'pro_matcher.py');
const ANALYSIS_TIMEOUT_MS = 2 * 60 * 1000; // matches analyse.js's own ceiling for the same subprocess
// Duplicated from analyse.js rather than shared -- see that file's own
// comment on why a daily cap exists at all (free-tier resource exhaustion).
// This is the same expensive MediaPipe subprocess, so it draws on the same
// analysis_usage accounting rather than getting a free pass.
const FREE_DAILY_LIMIT = 2;
const analyzeShotLimiter = rateLimit({ windowMs: 10 * 60 * 1000, max: 30, keyPrefix: 'analyse-shot', keyGenerator: (req) => req.user?.id ?? req.ip });
const STITCHER = path.join(__dirname, '..', '..', '..', 'scripts', '11_highlight_clipping', 'stitch_clips.py');
// Stitching re-copies every frame of every clip via OpenCV (no ffmpeg on
// this machine -- see stitch_clips.py's module comment), not a fast stream
// copy. The original 2-minute ceiling here was measured wrong: a real test
// against 3 real rally clips (113s combined footage) needed >120s and got
// killed by this exact timeout, converting a legitimately-still-working job
// into a false 'failed' status. Now that the endpoint enqueues a background
// job instead of blocking the HTTP response (see runReelJob()), there's no
// reason this needs to stay anywhere near as tight as it did when it used
// to gate how long a client's request stayed open -- raised generously.
const REEL_TIMEOUT_MS = 10 * 60 * 1000;
// Pose extraction over a full match video is slow and untimed so far --
// generous ceiling so a long session isn't killed mid-processing. Revisit
// once real timing on real match-length videos is observed.
const JOB_TIMEOUT_MS = 60 * 60 * 1000; // 1 hour

fs.mkdirSync(UPLOADS_DIR, { recursive: true });
fs.mkdirSync(CLIPS_DIR, { recursive: true });

const upload = multer({
  storage: multer.diskStorage({
    destination: UPLOADS_DIR,
    filename: (req, file, cb) => {
      cb(null, `match_${Date.now()}_${Math.round(Math.random() * 1e6)}${safeVideoExt(file.originalname)}`);
    },
  }),
  fileFilter: videoFileFilter,
  limits: { fileSize: 2 * 1024 * 1024 * 1024 }, // 2GB -- full match videos, not short swing clips
});

// Absolute filesystem path -> URL servable via the /highlight-clips static
// mount (server.js), so the frontend never sees filesystem paths.
function toClipUrl(absPath) {
  const rel = path.relative(CLIPS_DIR, absPath).split(path.sep).join('/');
  return `/highlight-clips/${rel}`;
}

function serializeClip(clip) {
  return { ...clip, clip_url: toClipUrl(clip.clip_path) };
}

// Attaches this rally's persisted per-shot data (shot_type, clip-relative
// contact_time_sec) -- see rally_shots' schema comment in db.js. Rallies
// created before this table existed simply have no rows here, so this
// degrades to shots: [] rather than erroring.
function serializeClipWithShots(clip) {
  const shots = db.prepare(
    `SELECT shot_index, shot_type, contact_time_sec FROM rally_shots WHERE rally_clip_id = ? ORDER BY shot_index`
  ).all(clip.id);
  return { ...serializeClip(clip), shots };
}

// Per-kind failure copy for the two background job runners below -- same
// convention as dev.js's sendPythonJson (see its own comment): the messages
// a PythonProcessError.kind maps to are written once per job type instead of
// hand-rolled per catch branch. 'nonzero_exit' has no fixed message here --
// the detector/stitcher's own reported error (parsed from stdout) takes
// priority over the fallback text, same as before this was deepened.
const RALLY_DETECTION_MESSAGES = {
  timeout: 'Rally detection timed out -- please try a shorter video.',
  invalid_json: 'Something went wrong processing your video.',
  spawn_failed: 'Failed to start detection process',
  nonzero_exit: 'Rally detection failed',
};
const REEL_BUILD_MESSAGES = {
  timeout: 'Reel building timed out.',
  invalid_json: 'Reel builder produced invalid output',
  spawn_failed: 'Failed to start reel builder',
  nonzero_exit: 'Failed to build highlight reel',
};

async function runJob(jobId, videoPath, userId) {
  db.prepare(`UPDATE highlight_jobs SET status = 'processing' WHERE id = ?`).run(jobId);

  const outputDir = path.join(CLIPS_DIR, String(userId), String(jobId));
  // Highlight jobs are always phone footage -- disable the trajectory-kNN FH/BH
  // step (its pro pool is broadcast and mislabels every phone selfie backhand
  // as a forehand). Mirror lefties before geom's view-invariant side test.
  const detectorArgs = [DETECTOR, videoPath, outputDir, '--no-trajectory'];
  const handed = db.prepare('SELECT handed FROM users WHERE id = ?').get(userId)?.handed;
  if (handed === 'left') detectorArgs.push('--handedness', 'left');

  let result;
  try {
    result = await runPythonJson(PYTHON, detectorArgs, { timeoutMs: JOB_TIMEOUT_MS, label: 'rally_detector.py' });
  } catch (err) {
    fs.unlink(videoPath, () => {}); // raw upload only ever needed during processing
    console.error(`[highlights] rally_detector.py failed (${err.kind}):`, err.stderr?.slice(-2000) || err.message);
    const message = resolveJobFailureMessage(err, RALLY_DETECTION_MESSAGES);
    db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run(message, jobId);
    sendPushNotification(userId, 'Rally detection failed', message);
    return;
  }

  fs.unlink(videoPath, () => {}); // raw upload only ever needed during processing

  try {
    const insert = db.prepare(`
      INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    const insertShot = db.prepare(`
      INSERT INTO rally_shots (rally_clip_id, shot_index, shot_type, contact_time_sec)
      VALUES (?, ?, ?, ?)
    `);
    // Transactional so a bad rally mid-list (e.g. a null clip_path
    // hitting the NOT NULL constraint) can't leave a partial set of
    // rally_clips rows inserted while the job status still ends up
    // 'failed' -- previously the loop and the status update were
    // separate statements, so a throw partway through left orphaned
    // clips that still rendered via GET /highlights/:jobId/clips despite
    // the job never being marked 'done'. Per-shot rows are inserted in the
    // same transaction, right after their parent rally_clips row, so a
    // bad shot can't leave a rally half-written either.
    const ingest = db.transaction(() => {
      for (const rally of result.rallies) {
        const info = insert.run(jobId, userId, rally.clip_path, rally.start_sec, rally.end_sec, rally.duration_sec, rally.swing_count);
        for (const shot of rally.shots ?? []) {
          insertShot.run(info.lastInsertRowid, shot.shot_index, shot.shot_type, shot.contact_time_sec);
        }
      }
      db.prepare(`UPDATE highlight_jobs SET status = 'done', completed_at = datetime('now') WHERE id = ?`).run(jobId);
    });
    ingest();
    sendPushNotification(
      userId,
      'Your rallies are ready',
      `Found ${result.rallies_detected} rall${result.rallies_detected === 1 ? 'y' : 'ies'} in your video — tap to review.`,
      { jobId }
    );
  } catch (e) {
    // Deliberately a separate catch from the runPythonJson() one above --
    // this failure isn't the detector's fault (its JSON already parsed
    // successfully), it's a DB constraint failure during ingest(). Folding
    // it into the other catch used to log only stdout and never the error
    // itself, misreporting a DB failure to the user as bad detector output.
    console.error('[highlights] failed to ingest rally_detector.py results:', e);
    db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run('Failed to save detected rallies', jobId);
    sendPushNotification(userId, 'Rally detection failed', 'Something went wrong processing your video.');
  }
}

router.post('/highlights/upload', requireAuth, requirePremium, highlightsUploadLimiter, upload.single('video'), (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: 'No video file uploaded (expected field "video")' });
  }

  const info = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path) VALUES (?, ?)`).run(req.user.id, req.file.path);
  const jobId = info.lastInsertRowid;

  // Not awaited -- runs in the background, response goes back immediately.
  // runJob is now an async function (it awaits runPythonJson internally) --
  // every throw inside it is already try/caught, but an un-awaited async
  // call is still a promise nobody holds a reference to, so any future edit
  // that adds a throw outside those try blocks would become an unhandled
  // rejection instead of a caught error. Attach a catch here as a permanent
  // backstop against that, same reasoning as runReelJob's call site below.
  runJob(jobId, req.file.path, req.user.id).catch((err) => {
    console.error('[highlights] runJob rejected unexpectedly:', err);
  });

  res.status(202).json({ jobId });
});

router.get('/highlights/jobs', requireAuth, (req, res) => {
  // pending_review = rallies this job produced that the user hasn't given an
  // outcome yet -- lets the Archive screen show "ready to review" without a
  // separate call per job. Boundary review (was this session bundled into
  // the same outcome question -- no longer) is a completely separate,
  // dev-only queue now: pending_boundary_review, same shape, counting
  // boundary_note instead. The two are independent on purpose -- an outcome
  // and a boundary judgment are unrelated questions asked by two different
  // screens now (HighlightReviewScreen.js vs DevRallyBoundaryReviewScreen.js).
  const jobs = db.prepare(`
    SELECT
      j.id, j.status, j.error, j.created_at, j.completed_at,
      (SELECT COUNT(*) FROM rally_clips c WHERE c.job_id = j.id AND c.outcome_tag IS NULL) AS pending_review,
      (SELECT COUNT(*) FROM rally_clips c WHERE c.job_id = j.id AND c.boundary_note IS NULL) AS pending_boundary_review
    FROM highlight_jobs j
    WHERE j.user_id = ?
    ORDER BY j.created_at DESC
  `).all(req.user.id);
  res.json({ jobs });
});

router.get('/highlights/jobs/:id', requireAuth, (req, res) => {
  const job = db.prepare(`SELECT * FROM highlight_jobs WHERE id = ? AND user_id = ?`).get(req.params.id, req.user.id);
  if (!job) return res.status(404).json({ error: 'Job not found' });

  const rallies = job.status === 'done'
    ? db.prepare(`SELECT * FROM rally_clips WHERE job_id = ? ORDER BY start_sec`).all(job.id).map(serializeClipWithShots)
    : [];

  res.json({ ...job, rallies });
});

// Analyzes one shot picked out of an already-detected rally clip, using the
// pipeline's own detected contact frame -- no manual contact-marking
// round-trip needed, since detect_rallies.py already found it. Reuses the
// same pro_matcher.py invocation and post-processing /api/analyse uses, so
// the response shape matches exactly and ResultsScreen.js renders it with
// no changes to its render path.
router.post('/highlights/rallies/:id/shots/:shotIndex/analyze', requireAuth, analyzeShotLimiter, async (req, res) => {
  const shotIndex = Number(req.params.shotIndex);
  if (!Number.isInteger(shotIndex) || shotIndex < 0) {
    return res.status(400).json({ error: 'shotIndex must be a non-negative integer' });
  }

  const clip = db.prepare(`SELECT * FROM rally_clips WHERE id = ? AND user_id = ?`).get(req.params.id, req.user.id);
  if (!clip) return res.status(404).json({ error: 'Rally clip not found' });

  const shot = db.prepare(
    `SELECT * FROM rally_shots WHERE rally_clip_id = ? AND shot_index = ?`
  ).get(clip.id, shotIndex);
  if (!shot) return res.status(404).json({ error: 'Shot not found' });

  // Same free-tier accounting as /api/analyse -- this spawns the identical
  // expensive subprocess, it shouldn't get a free pass just because the
  // source clip already existed.
  const isFreeUser = currentTier(req.user.id) === 'free';
  let usageRowId = null;
  if (isFreeUser) {
    const reserved = reserveDailyUsageSlot(db, req.user.id, FREE_DAILY_LIMIT);
    if (reserved === LIMIT_EXCEEDED) {
      return res.status(403).json({
        error: `Free plan is limited to ${FREE_DAILY_LIMIT} analyses per day — upgrade to Premium for unlimited.`,
        code: 'DAILY_LIMIT',
      });
    }
    usageRowId = reserved;
  }

  const handed = db.prepare('SELECT handed FROM users WHERE id = ?').get(req.user.id)?.handed;
  const args = [MATCHER, clip.clip_path, shot.shot_type, '--top', '3', '--contact-time', String(shot.contact_time_sec)];
  if (handed === 'left') args.push('--handedness', 'left');

  let result;
  try {
    result = await runPythonJson(PYTHON, args, { timeoutMs: ANALYSIS_TIMEOUT_MS, label: 'pro_matcher.py' });
  } catch (err) {
    // The matcher never ran to completion -- this free-tier slot bought
    // nothing, give it back (see analyse.js's identical reasoning).
    releaseUsageSlot(db, usageRowId);
    console.error(`[highlights] analyze-shot pro_matcher.py failed (${err.kind}):`, err.stderr?.slice(-2000) || err.message);
    const messages = {
      spawn_failed: 'Failed to start analysis process',
      invalid_json: 'Analysis produced invalid output',
      timeout: 'Analysis timed out',
      nonzero_exit: (() => {
        try { return JSON.parse(err.stdout).error; } catch { return 'Analysis failed'; }
      })(),
    };
    return res.status(500).json({ error: messages[err.kind] || 'Analysis failed' });
  }

  try {
    // deleteSource:false -- unlike /api/analyse's throwaway upload, this
    // source is the persisted rally clip, still needed for this rally's
    // other shots (and any re-analysis of this one).
    //
    // destDir includes a per-request suffix (analyse.js gets the same
    // uniqueness for free from multer's own randomized upload filename) --
    // a bare `rally_<id>_shot_<index>` would give two concurrent requests
    // for the same shot (a double-tap, or two devices on the same account)
    // the identical destination path, racing persistAndCrop's copyFileSync/
    // cropToSubject against each other into the same files.
    await finalizeAnalysisResult(result, {
      sourcePath: clip.clip_path,
      destDir: path.join(USER_CLIPS_DIR, `rally_${clip.id}_shot_${shot.shot_index}_${Date.now()}_${Math.round(Math.random() * 1e6)}`),
      shotType: shot.shot_type,
      deleteSource: false,
    });
    res.json(result);
  } catch (err) {
    // Analysis already succeeded by this point -- same reasoning as
    // analyse.js's identical catch: this is a post-processing failure, not
    // a failed analysis, so the usage slot is NOT released here.
    console.error(`[highlights] analyze-shot post-processing failed after a successful analysis: ${err.message}`);
    if (!res.headersSent) {
      res.status(500).json({ error: 'Analysis succeeded but the response could not be completed' });
    }
  }
});

async function runReelJob(reelJobId, outputPath, clipPaths) {
  db.prepare(`UPDATE reel_jobs SET status = 'processing' WHERE id = ?`).run(reelJobId);

  // Safety net against a stuck process now, not tied to any HTTP response --
  // the client learns the outcome by polling reel_jobs regardless.
  let result;
  try {
    result = await runPythonJson(PYTHON, [STITCHER, outputPath, ...clipPaths], { timeoutMs: REEL_TIMEOUT_MS, label: 'stitch_clips.py' });
  } catch (err) {
    console.error(`[highlights] stitch_clips.py failed (${err.kind}):`, err.stderr?.slice(-2000) || err.message);
    const message = resolveJobFailureMessage(err, REEL_BUILD_MESSAGES);
    db.prepare(`UPDATE reel_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run(message, reelJobId);
    return;
  }

  // runPythonJson already guarantees `result` is valid parsed JSON by the
  // time this resolves -- no separate JSON.parse/catch needed here the way
  // the hand-rolled version needed one (that failure mode is now
  // err.kind === 'invalid_json' above, handled once for every job type).
  db.prepare(
    `UPDATE reel_jobs SET status = 'done', output_path = ?, completed_at = datetime('now') WHERE id = ?`
  ).run(result.output_path, reelJobId);
}

router.post('/highlights/jobs/:id/reel', requireAuth, requirePremium, (req, res) => {
  const job = db.prepare(`SELECT * FROM highlight_jobs WHERE id = ? AND user_id = ?`).get(req.params.id, req.user.id);
  if (!job) return res.status(404).json({ error: 'Job not found' });
  if (job.status !== 'done') return res.status(400).json({ error: 'Job is not ready yet' });

  const { top, rallyIds } = req.body || {};
  // A non-integer element (e.g. an object/array a buggy client sent) bound
  // straight into the '?' placeholders below throws a RangeError deep in
  // better-sqlite3 ("Too few parameter values were provided"), crashing the
  // route with a 500 instead of a clean 400.
  if (Array.isArray(rallyIds) && !rallyIds.every(Number.isInteger)) {
    return res.status(400).json({ error: 'rallyIds must be an array of integers' });
  }
  let clips;
  if (Array.isArray(rallyIds)) {
    // An explicit `rallyIds: []` (e.g. the client's picker UI with every
    // rally deselected) used to fall through to the `else` branch below and
    // silently build a reel from the top-3-by-duration default instead --
    // the caller's explicit "none of these" was overridden rather than
    // honored or rejected. Now it's a clean 400 instead of a surprise reel;
    // omit rallyIds entirely to get the top-N default.
    if (rallyIds.length === 0) {
      return res.status(400).json({ error: 'rallyIds cannot be empty -- select at least one rally, or omit rallyIds to use the default top clips' });
    }
    const placeholders = rallyIds.map(() => '?').join(',');
    clips = db.prepare(
      `SELECT * FROM rally_clips WHERE job_id = ? AND user_id = ? AND id IN (${placeholders})`
    ).all(job.id, req.user.id, ...rallyIds);
    // Preserve the order the caller asked for, not SQLite's return order.
    const byId = new Map(clips.map((c) => [c.id, c]));
    clips = rallyIds.map((id) => byId.get(id)).filter(Boolean);
  } else {
    const n = Number.isInteger(top) && top > 0 ? top : 3;
    clips = db.prepare(
      `SELECT * FROM rally_clips WHERE job_id = ? AND user_id = ? ORDER BY duration_sec DESC LIMIT ?`
    ).all(job.id, req.user.id, n);
  }

  if (clips.length === 0) {
    return res.status(400).json({ error: 'No matching rallies to stitch' });
  }

  const outputPath = path.join(CLIPS_DIR, String(req.user.id), String(job.id), `reel_${Date.now()}.mp4`);
  const rallyIdsResolved = clips.map((c) => c.id);
  const info = db.prepare(
    `INSERT INTO reel_jobs (highlight_job_id, user_id, rally_ids) VALUES (?, ?, ?)`
  ).run(job.id, req.user.id, JSON.stringify(rallyIdsResolved));
  const reelJobId = info.lastInsertRowid;

  // Not awaited -- runs in the background, response goes back immediately.
  // See runJob's call site above for why this needs a .catch backstop.
  runReelJob(reelJobId, outputPath, clips.map((c) => c.clip_path)).catch((err) => {
    console.error('[highlights] runReelJob rejected unexpectedly:', err);
  });

  res.status(202).json({ reelJobId });
});

router.get('/highlights/reel-jobs/:id', requireAuth, (req, res) => {
  const reelJob = db.prepare(`SELECT * FROM reel_jobs WHERE id = ? AND user_id = ?`).get(req.params.id, req.user.id);
  if (!reelJob) return res.status(404).json({ error: 'Reel job not found' });

  res.json({
    status: reelJob.status,
    reel_url: reelJob.output_path ? toClipUrl(reelJob.output_path) : null,
    rally_ids: JSON.parse(reelJob.rally_ids),
    error: reelJob.error,
  });
});

router.patch('/highlights/rallies/:id', requireAuth, (req, res) => {
  const { outcome_tag, archived, boundary_note } = req.body || {};

  // Both fields are human review verdicts that leave this app: outcome_tag
  // drives profile.js's Player Type, and boundary_note is training data
  // tune_rally_gap.py reads to tune the rally detector. Neither was checked
  // at all before, so a typo'd tag silently became a category nothing counts,
  // and a malformed boundary_note silently poisoned the training signal.
  // isBoundaryNote also enforces the grammar, not just the vocabulary: it's a
  // comma-joined list, and 'ok'/'should_split' are whole-clip verdicts that
  // can't coexist with anything else.
  const bad = validate([
    ['outcome_tag', outcome_tag, optional(isOutcomeTag), oneOfMessage(OUTCOME_TAGS)],
    ['boundary_note', boundary_note, isBoundaryNote, 'must be a comma-joined list of ok, started_too_late, cut_off_early, should_split (ok/should_split cannot be combined)'],
    // Was used raw (`archived ? 1 : 0`) with no type check -- any truthy
    // non-boolean (e.g. the string "false") coerced to archived=1 with no
    // 400 to signal the caller's mistake, same class of bug as the
    // flagged_not_shot/confirmed_real_shot fix in history.js.
    ['archived', archived, (v) => v === undefined || typeof v === 'boolean', 'must be true or false'],
  ]);
  if (bad) return res.status(400).json(bad);

  const clip = db.prepare(`SELECT * FROM rally_clips WHERE id = ? AND user_id = ?`).get(req.params.id, req.user.id);
  if (!clip) return res.status(404).json({ error: 'Rally clip not found' });

  // `?? clip.boundary_note` treats an OMITTED key the same as an explicit
  // null, so there was no way to actually clear a previously-set
  // boundary_note -- DevRallyBoundaryReviewScreen.js unchecking every
  // boundary box for a clip sends a body with the key left out entirely
  // (JSON.stringify drops undefined-valued keys), and the stale note
  // silently kept poisoning tune_rally_gap.py's training data. Distinguish
  // "key present" (even if null/'', a real clear request) from "key absent"
  // (no change intended) instead.
  const clearsBoundaryNote = Object.prototype.hasOwnProperty.call(req.body || {}, 'boundary_note');

  db.prepare(`UPDATE rally_clips SET outcome_tag = ?, archived = ?, boundary_note = ? WHERE id = ?`).run(
    outcome_tag ?? clip.outcome_tag,
    archived !== undefined ? (archived ? 1 : 0) : clip.archived,
    clearsBoundaryNote ? (boundary_note ?? null) : clip.boundary_note,
    clip.id
  );

  res.json(serializeClip(db.prepare(`SELECT * FROM rally_clips WHERE id = ?`).get(clip.id)));
});

router.get('/highlights/archive', requireAuth, (req, res) => {
  const clips = db.prepare(
    `SELECT * FROM rally_clips WHERE user_id = ? AND archived = 1 ORDER BY created_at DESC`
  ).all(req.user.id).map(serializeClip);
  res.json({ clips });
});

router.post('/push-token', requireAuth, (req, res) => {
  const { token } = req.body || {};
  // An Expo push token is a short opaque string. Capping it stops a client
  // filling push_tokens (UNIQUE, so one row per distinct value) with junk.
  const bad = validate([
    ['token', token, isText(MAX_LENGTHS.pushToken), `must be a string of ${MAX_LENGTHS.pushToken} characters or fewer`],
  ]);
  if (bad) return res.status(400).json(bad);

  // `token` is UNIQUE per device, not per user -- a device can be reused by a
  // different account (shared device, logout/login without reinstalling), so
  // re-registering an existing token must move it to the new owner rather
  // than silently no-op and leave it pointing at the previous user forever.
  db.prepare(`
    INSERT INTO push_tokens (user_id, token) VALUES (?, ?)
    ON CONFLICT(token) DO UPDATE SET user_id = excluded.user_id, created_at = datetime('now')
  `).run(req.user.id, token);
  res.status(204).end();
});

module.exports = router;
