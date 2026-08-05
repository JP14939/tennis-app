const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
require('dotenv').config();

const { SCRIPTS_DIR, DATA_DIR, PYTHON } = require('./config/paths');
const analyseRouter = require('./routes/analyse');
const authRouter = require('./routes/auth');
const calibrationRouter = require('./routes/calibration');
const compareVideosRouter = require('./routes/compareVideos');
const historyRouter = require('./routes/history');
const billingRouter = require('./routes/billing');
const webhooksRouter = require('./routes/webhooks');
const highlightsRouter = require('./routes/highlights');

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
const RUNTIME_SWEEP_DIRS = [
  path.join(DATA_DIR, 'runtime', 'user_clips'),
  path.join(DATA_DIR, 'runtime', 'comparison_clips'),
];
const RUNTIME_MAX_AGE_MS = 24 * 60 * 60 * 1000;

function sweepOldRuntimeDirs() {
  for (const dir of RUNTIME_SWEEP_DIRS) {
    fs.readdir(dir, (err, entries) => {
      if (err) return; // dir may not exist yet -- fine, nothing to sweep
      for (const entry of entries) {
        const entryPath = path.join(dir, entry);
        fs.stat(entryPath, (statErr, stat) => {
          if (statErr || !stat.isDirectory()) return;
          if (Date.now() - stat.mtimeMs > RUNTIME_MAX_AGE_MS) {
            fs.rm(entryPath, { recursive: true, force: true }, () => {});
          }
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
