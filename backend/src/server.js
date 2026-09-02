const express = require('express');
const cors = require('cors');
const compression = require('compression');
const path = require('path');
const fs = require('fs');
const multer = require('multer');
const { spawn } = require('child_process');
require('dotenv').config();

const { SCRIPTS_DIR, DATA_DIR, PYTHON } = require('./config/paths');
const db = require('./db');
const analyseRouter = require('./routes/analyse');
const authRouter = require('./routes/auth');
const calibrationRouter = require('./routes/calibration');
const compareVideosRouter = require('./routes/compareVideos');
const historyRouter = require('./routes/history');
const billingRouter = require('./routes/billing');
const webhooksRouter = require('./routes/webhooks');
const highlightsRouter = require('./routes/highlights');
const coachRouter = require('./routes/coach');
const profileRouter = require('./routes/profile');
const courtsRouter = require('./routes/courts');
const messagesRouter = require('./routes/messages');
const friendsRouter = require('./routes/friends');
const annotationsRouter = require('./routes/annotations');
const leaderboardRouter = require('./routes/leaderboard');
const devRouter = require('./routes/dev');
const drillsRouter = require('./routes/drills');
const { UnsupportedFileTypeError } = require('./utils/videoUpload');

const app = express();
// Hosted behind Caddy (docker-compose.yml) -- without this, req.ip is always
// the Caddy container's own address, which would make every caller share one
// IP-keyed rate-limit bucket (middleware/rateLimit.js) instead of being
// limited individually. `1` trusts exactly one hop, matching the one reverse
// proxy in front of this container.
app.set('trust proxy', 1);
app.use(cors());
// JSON API responses (esp. GET /api/history, which grows with account size)
// went from loopback-fast to real internet round-trips once the hosted
// backend became the default target -- gzip cuts that payload noticeably.
// Static video files under /user-clips etc. are already compressed formats,
// so compression's default filter (skips already-compressed content types)
// leaves those alone.
app.use(compression());
app.use(express.json());

app.get('/health', (req, res) => {
  res.json({ status: 'OK', message: 'Server is running' });
});

app.use('/api', analyseRouter);
app.use('/api', authRouter);
app.use('/api', calibrationRouter);
app.use('/api', compareVideosRouter);
app.use('/api', historyRouter);
app.use('/api', billingRouter);
app.use('/api', webhooksRouter);
app.use('/api', highlightsRouter);
app.use('/api', coachRouter);
app.use('/api', profileRouter);
app.use('/api', courtsRouter);
app.use('/api', messagesRouter);
app.use('/api', friendsRouter);
app.use('/api', annotationsRouter);
app.use('/api', leaderboardRouter);
app.use('/api', devRouter);
app.use('/api', drillsRouter);

// Rally clips need to be watchable from the app after the request that
// created them is long gone -- first real use of static file serving in
// this backend (every other route returns JSON only).
app.use('/highlight-clips', express.static(path.join(DATA_DIR, 'runtime', 'highlight_clips')));

// Sync-scroller video sources: the pro database's own clips (never modified
// in place) plus their pose-cropped copies, and the per-request uploaded
// videos (analyse.js / compareVideos.js) that used to be deleted right after
// comparison -- they're now kept around so the results screens can play them.
app.use('/pro-clips', express.static(path.join(DATA_DIR, '04_clips')));
app.use('/pro-clips-cropped', express.static(path.join(DATA_DIR, '04_clips_cropped')));
app.use('/user-clips', express.static(path.join(DATA_DIR, 'runtime', 'user_clips')));
app.use('/comparison-clips', express.static(path.join(DATA_DIR, 'runtime', 'comparison_clips')));
// Drills & Lessons instructional videos, uploaded via the Dev Page editor
// (routes/dev.js) -- persistent like /pro-clips, never swept.
app.use('/drill-clips', express.static(path.join(DATA_DIR, 'runtime', 'drill_clips')));
// Static candidate frames (JPEGs, not video) for the Dev Page's manual
// ball-labeling tool -- see the ball detector project's plan.
app.use('/ball-label-frames', express.static(path.join(DATA_DIR, '10b_ball_detection', 'candidate_frames')));
// Original, uncut compilation videos the pro database was built from --
// serves "View in source footage" on the Pro Clip Review Dev Page tool
// (Sprint 0 of the 2026-08-27 ML reliability plan), so a flagged clip can be
// checked against full surrounding context instead of just its isolated
// ~3s cut. These files are large (100MB-1.3GB); express.static supports
// HTTP Range requests out of the box, so seeking to a specific timestamp
// doesn't require downloading the whole file first.
app.use('/source-footage', express.static(path.join(DATA_DIR, '01_source_videos')));

// Standalone reset-password.html (self-serve password reset, 2026-08-20)
// -- served from the backend directly rather than through the Expo app,
// since only this backend is permanently hosted; the reset email's link
// points straight at /reset-password.html?token=... on this same origin.
app.use(express.static(path.join(__dirname, '..', 'public')));

// Basic starting point, not a robust job queue: sweep upload-derived runtime
// dirs older than a day so /user-clips and /comparison-clips don't grow
// forever. Pro clips (04_clips, 04_clips_cropped) are never swept -- those
// are the shared database, not per-request uploads.
//
// user_clips is NOT purely ephemeral, though: analyse.js persists every
// upload there and stores its /user-clips/<dir>/... URL in a saved History
// row's result_json, and History rows are meant to stay watchable for as
// long as the row exists (retention is tier-limited via FREE_TIER_LIMIT, not
// time-limited). A flat 24h age sweep silently deleted the file out from
// under still-existing History rows -- every saved analysis older than a day
// showed "Video unavailable" in Sync Compare (found live: nothing had been
// analysed in the last 24h, so 100% of History was broken). comparison_clips
// (Versus mode) has no such row -- VersusResultsScreen only ever reads it
// once, immediately after the compare request, so it's genuinely safe to
// sweep on age alone.
const USER_CLIPS_DIR_FOR_SWEEP = path.join(DATA_DIR, 'runtime', 'user_clips');
const RUNTIME_SWEEP_DIRS = [
  { dir: USER_CLIPS_DIR_FOR_SWEEP, checkHistoryReference: true },
  { dir: path.join(DATA_DIR, 'runtime', 'comparison_clips'), checkHistoryReference: false },
];
const RUNTIME_MAX_AGE_MS = 24 * 60 * 60 * 1000;

function isReferencedByHistory(dirName) {
  // dirName is a filesystem directory name (e.g. "upload_1737000000000_123456")
  // and routinely contains underscores -- LIKE treats '_' as a single-char
  // wildcard and '%' as any-length, so without escaping them a dirName could
  // spuriously match an unrelated row whose URL merely differs by one
  // character in that position, keeping a sweepable directory alive forever.
  const escaped = dirName.replace(/[_%]/g, '\\$&');
  const row = db.prepare("SELECT 1 FROM analyses WHERE result_json LIKE ? ESCAPE '\\' LIMIT 1")
    .get(`%/user-clips/${escaped}/%`);
  return !!row;
}

function sweepOldRuntimeDirs() {
  for (const { dir, checkHistoryReference } of RUNTIME_SWEEP_DIRS) {
    fs.readdir(dir, (err, entries) => {
      if (err) return; // dir may not exist yet -- fine, nothing to sweep
      for (const entry of entries) {
        const entryPath = path.join(dir, entry);
        fs.stat(entryPath, (statErr, stat) => {
          if (statErr || !stat.isDirectory()) return;
          if (Date.now() - stat.mtimeMs <= RUNTIME_MAX_AGE_MS) return;
          if (checkHistoryReference && isReferencedByHistory(entry)) return;
          fs.rm(entryPath, { recursive: true, force: true }, () => {});
        });
      }
    });
  }
}
setInterval(sweepOldRuntimeDirs, 60 * 60 * 1000);
sweepOldRuntimeDirs();

// Persistent live-calibration inference process (keeps the net-keypoint
// model loaded in memory so repeated positioning checks are fast, unlike
// every other route above which spawns Python fresh per request). Optional:
// if it fails to start, only POST /api/check-setup-live is affected — the
// rest of the API doesn't depend on it, and that route degrades gracefully.
const CALIBRATION_SERVER_SCRIPT = path.join(SCRIPTS_DIR, '00_utils', 'calibration_server.py');

async function startCalibrationServer() {
  // Guard against leaking a new (model-holding, ~300MB) process on every
  // nodemon restart -- if one's already listening (e.g. survived a restart,
  // or this is a `rs`/file-save reload), skip spawning another.
  try {
    await fetch('http://127.0.0.1:5055/check');
    console.log('[calibration_server] already running, skipping spawn');
    return;
  } catch {
    // ECONNREFUSED -- nothing listening yet, proceed to spawn below.
  }

  const proc = spawn(PYTHON, [CALIBRATION_SERVER_SCRIPT]);
  proc.stdout.on('data', (chunk) => process.stdout.write(`[calibration_server] ${chunk}`));
  proc.stderr.on('data', (chunk) => process.stderr.write(`[calibration_server] ${chunk}`));
  proc.on('error', (err) => console.error('[calibration_server] failed to start:', err));
  proc.on('exit', (code) => {
    console.error(`[calibration_server] exited (code ${code})`);
  });

  // Best-effort cleanup so a normal restart doesn't orphan the child even
  // when the "already running" check above raced it (nodemon restarts kill
  // this process with SIGTERM, not a graceful shutdown hook by default).
  const cleanup = () => { try { proc.kill(); } catch { /* already gone */ } };
  process.on('exit', cleanup);
  process.on('SIGTERM', cleanup);
  process.on('SIGINT', cleanup);

  return proc;
}
startCalibrationServer();

// Global error handler -- must be registered last (Express only treats a
// 4-arg middleware as an error handler, and only errors thrown/rejected by
// something registered BEFORE this point reach it). Without this, Express 5
// still catches a rejected promise from an async route handler (unlike
// Express 4, no manual try/catch-and-next is required for that part), but
// its own default handler returns an HTML/plain-text error page -- every
// other failure path in this app returns {error: '...'} JSON, so an
// uncaught DB/bcrypt error or an oversized multer upload broke that
// contract for exactly those failure modes. This restores it.
// eslint-disable-next-line no-unused-vars
app.use((err, req, res, next) => {
  if (err instanceof multer.MulterError) {
    const message = err.code === 'LIMIT_FILE_SIZE' ? 'Uploaded file is too large' : err.message;
    return res.status(400).json({ error: message });
  }
  if (err instanceof UnsupportedFileTypeError) {
    return res.status(400).json({ error: err.message });
  }
  if (err.type === 'entity.parse.failed' || err instanceof SyntaxError) {
    return res.status(400).json({ error: 'Malformed JSON in request body' });
  }
  console.error('[server] unhandled error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

module.exports = app;
