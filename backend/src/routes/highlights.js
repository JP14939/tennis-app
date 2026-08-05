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

const router = express.Router();

const UPLOADS_DIR = path.join(__dirname, '..', '..', 'uploads');
// Persistent -- unlike uploads/, rally clips must outlive the request that
// created them (the user reviews/archives them later), so nothing cleans
// this up after each job the way analyse.js/compareVideos.js clean up
// their ephemeral uploads.
const CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'highlight_clips');
const DETECTOR = path.join(__dirname, '..', 'services', 'rally_detector.py');
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
      const ext = path.extname(file.originalname) || '.mp4';
      cb(null, `match_${Date.now()}_${Math.round(Math.random() * 1e6)}${ext}`);
    },
  }),
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

    try {
      const result = JSON.parse(stdout);
      const insert = db.prepare(`
        INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `);
      for (const rally of result.rallies) {
        insert.run(jobId, userId, rally.clip_path, rally.start_sec, rally.end_sec, rally.duration_sec, rally.swing_count);
      }
      db.prepare(`UPDATE highlight_jobs SET status = 'done', completed_at = datetime('now') WHERE id = ?`).run(jobId);
      sendPushNotification(
        userId,
        'Your rallies are ready',
        `Found ${result.rallies_detected} rall${result.rallies_detected === 1 ? 'y' : 'ies'} in your video — tap to review.`,
        { jobId }
      );
    } catch (e) {
      console.error('[highlights] failed to parse rally_detector.py output:', stdout.slice(-2000));
      db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run('Detection produced invalid output', jobId);
      sendPushNotification(userId, 'Rally detection failed', 'Something went wrong processing your video.');
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    fs.unlink(videoPath, () => {});
    console.error('[highlights] failed to spawn python:', err);
    db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`).run('Failed to start detection process', jobId);
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
  // pending_review = rallies this job produced that the user hasn't tagged
  // yet -- lets the Archive screen show "ready to review" without a
  // separate call per job.
  const jobs = db.prepare(`
    SELECT
      j.id, j.status, j.error, j.created_at, j.completed_at,
      (SELECT COUNT(*) FROM rally_clips c WHERE c.job_id = j.id AND c.outcome_tag IS NULL) AS pending_review
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

router.patch('/highlights/rallies/:id', requireAuth, (req, res) => {
  const { outcome_tag, archived } = req.body || {};
  const clip = db.prepare(`SELECT * FROM rally_clips WHERE id = ? AND user_id = ?`).get(req.params.id, req.user.id);
  if (!clip) return res.status(404).json({ error: 'Rally clip not found' });

  db.prepare(`UPDATE rally_clips SET outcome_tag = ?, archived = ? WHERE id = ?`).run(
    outcome_tag ?? clip.outcome_tag,
    archived !== undefined ? (archived ? 1 : 0) : clip.archived,
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
  if (!token) return res.status(400).json({ error: 'token is required' });

  db.prepare(`INSERT OR IGNORE INTO push_tokens (user_id, token) VALUES (?, ?)`).run(req.user.id, token);
  res.status(204).end();
});

module.exports = router;
