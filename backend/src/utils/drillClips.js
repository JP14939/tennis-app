const path = require('path');
const { DATA_DIR } = require('../config/paths');

// Shared between routes/drills.js (reads) and routes/dev.js (writes via the
// Dev Page editor) -- same toUrl() pattern as utils/videoCrop.js.
const CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'drill_clips');

function toClipUrl(absPath) {
  if (!absPath) return null;
  const rel = path.relative(CLIPS_DIR, absPath).split(path.sep).join('/');
  return `/drill-clips/${rel}`;
}

module.exports = { CLIPS_DIR, toClipUrl };
