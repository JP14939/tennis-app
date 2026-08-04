const express = require('express');
const cors = require('cors');
const path = require('path');
const { spawn } = require('child_process');
require('dotenv').config();

const analyseRouter = require('./routes/analyse');
const authRouter = require('./routes/auth');
const calibrationRouter = require('./routes/calibration');
const compareVideosRouter = require('./routes/compareVideos');
const historyRouter = require('./routes/history');

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

// Persistent live-calibration inference process (keeps the net-keypoint
// model loaded in memory so repeated positioning checks are fast, unlike
// every other route above which spawns Python fresh per request). Optional:
// if it fails to start, only POST /api/check-setup-live is affected — the
// rest of the API doesn't depend on it, and that route degrades gracefully.
const PYTHON = path.join(__dirname, '..', '..', 'scripts', 'venv', 'Scripts', 'python.exe');
const CALIBRATION_SERVER_SCRIPT = path.join(__dirname, '..', '..', 'scripts', '00_utils', 'calibration_server.py');

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
