const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
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

const app = express();
app.use(cors());
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
  const row = db.prepare('SELECT 1 FROM analyses WHERE result_json LIKE ? LIMIT 1')
    .get(`%/user-clips/${dirName}/%`);
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

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

module.exports = app;
