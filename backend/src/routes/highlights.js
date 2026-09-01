const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const requirePremium = require('../middleware/requirePremium');
const { PYTHON, DATA_DIR } = require('../config/paths');
const { sendPushNotification } = require('../utils/pushNotifications');
const { safeVideoExt, videoFileFilter } = require('../utils/videoUpload');
const {
  OUTCOME_TAGS, MAX_LENGTHS, isOutcomeTag, isBoundaryNote, isText,
} = require('../domain/invariants');
const { validate, optional, oneOfMessage } = require('../validation/validateBody');

const router = express.Router();

const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');
// Persistent -- unlike uploads/, rally clips must outlive the request that
// created them (the user reviews/archives them later), so nothing cleans
// this up after each job the way analyse.js/compareVideos.js clean up
// their ephemeral uploads.
const CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'highlight_clips');
const DETECTOR = path.join(__dirname, '..', 'services', 'rally_detector.py');
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

function runJob(jobId, videoPath, userId) {
  db.prepare(`UPDATE highlight_jobs SET status = 'processing' WHERE id = ?`).run(jobId);

  const outputDir = path.join(CLIPS_DIR, String(userId), String(jobId));
  const proc = spawn(PYTHON, [DETECTOR, videoPath, outputDir]);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => proc.kill(), JOB_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    fs.unlink(videoPath, () => {}); // raw upload only ever needed during processing

    if (code !== 0) {
      console.error('[highlights] rally_detector.py failed:', stderr.slice(-2000));
      let error = 'Rally detection failed';
      try { error = JSON.parse(stdout).error || error; } catch { /* stdout wasn't JSON */ }
      db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run(error, jobId);
      sendPushNotification(userId, 'Rally detection failed', error);
      return;
    }

    let result;
    try {
      result = JSON.parse(stdout);
    } catch (e) {
      console.error('[highlights] failed to parse rally_detector.py output:', e.message, stdout.slice(-2000));
      db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run('Detection produced invalid output', jobId);
      sendPushNotification(userId, 'Rally detection failed', 'Something went wrong processing your video.');
      return;
    }

    try {
      const insert = db.prepare(`
        INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `);
      // Transactional so a bad rally mid-list (e.g. a null clip_path
      // hitting the NOT NULL constraint) can't leave a partial set of
      // rally_clips rows inserted while the job status still ends up
      // 'failed' -- previously the loop and the status update were
      // separate statements, so a throw partway through left orphaned
      // clips that still rendered via GET /highlights/:jobId/clips despite
      // the job never being marked 'done'.
      const ingest = db.transaction(() => {
        for (const rally of result.rallies) {
          insert.run(jobId, userId, rally.clip_path, rally.start_sec, rally.end_sec, rally.duration_sec, rally.swing_count);
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
      // Was folded into the JSON-parse catch above, which logged only stdout
      // and never the error itself -- so a DB constraint failure during
      // ingest() left no trace of what actually broke and reported itself to
      // the user as bad detector output.
      console.error('[highlights] failed to ingest rally_detector.py results:', e);
      db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run('Failed to save detected rallies', jobId);
      sendPushNotification(userId, 'Rally detection failed', 'Something went wrong processing your video.');
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    fs.unlink(videoPath, () => {});
    console.error('[highlights] failed to spawn python:', err);
    db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run('Failed to start detection process', jobId);
    // Every other failure path in this function (nonzero exit, invalid JSON
    // output) notifies the user their job failed -- this one (spawn itself
    // never starting, e.g. a bad interpreter path) marked the job failed in
    // the DB but left the user with no proactive signal, unlike the rest.
    sendPushNotification(userId, 'Rally detection failed', 'Failed to start detection process');
  });
}

router.post('/highlights/upload', requireAuth, requirePremium, upload.single('video'), (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: 'No video file uploaded (expected field "video")' });
  }

  const info = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path) VALUES (?, ?)`).run(req.user.id, req.file.path);
  const jobId = info.lastInsertRowid;

  // Not awaited -- runs in the background, response goes back immediately.
  runJob(jobId, req.file.path, req.user.id);

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
    ? db.prepare(`SELECT * FROM rally_clips WHERE job_id = ? ORDER BY start_sec`).all(job.id).map(serializeClip)
    : [];

  res.json({ ...job, rallies });
});

function runReelJob(reelJobId, outputPath, clipPaths) {
  db.prepare(`UPDATE reel_jobs SET status = 'processing' WHERE id = ?`).run(reelJobId);

  const proc = spawn(PYTHON, [STITCHER, outputPath, ...clipPaths]);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  // Safety net against a stuck process now, not tied to any HTTP response --
  // the client learns the outcome by polling reel_jobs regardless.
  const timeout = setTimeout(() => proc.kill(), REEL_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    if (code !== 0) {
      console.error('[highlights] stitch_clips.py failed:', stderr.slice(-2000));
      let error = 'Failed to build highlight reel';
      try { error = JSON.parse(stdout).error || error; } catch { /* stdout wasn't JSON */ }
      db.prepare(`UPDATE reel_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run(error, reelJobId);
      return;
    }
    try {
      const result = JSON.parse(stdout);
      db.prepare(
        `UPDATE reel_jobs SET status = 'done', output_path = ?, completed_at = datetime('now') WHERE id = ?`
      ).run(result.output_path, reelJobId);
    } catch {
      console.error('[highlights] failed to parse stitch_clips.py output:', stdout.slice(-2000));
      db.prepare(`UPDATE reel_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run('Reel builder produced invalid output', reelJobId);
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    console.error('[highlights] failed to spawn stitcher:', err);
    db.prepare(`UPDATE reel_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run('Failed to start reel builder', reelJobId);
  });
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
  runReelJob(reelJobId, outputPath, clips.map((c) => c.clip_path));

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
