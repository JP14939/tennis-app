const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { SCRIPTS_DIR, DATA_DIR, PYTHON } = require('../config/paths');

const CROP_SCRIPT = path.join(SCRIPTS_DIR, '12_video_crop', 'crop_to_subject.py');
const CROP_TIMEOUT_MS = 60 * 1000;
const PRO_CLIPS_DIR = path.join(DATA_DIR, '04_clips');
const PRO_CLIPS_CROPPED_DIR = path.join(DATA_DIR, '04_clips_cropped');

// Runs scripts/12_video_crop/crop_to_subject.py. That script never raises --
// it always prints {"cropped": true} or {"cropped": false, "reason": "..."}
// -- so this resolves to the output path on success or null on any failure,
// and never rejects: a failed crop should fall back to the original video,
// not break the comparison request it's attached to.
function cropToSubject(inputPath, outputPath) {
  return new Promise((resolve) => {
    const proc = spawn(PYTHON, [CROP_SCRIPT, inputPath, outputPath]);
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (c) => { stdout += c; });
    proc.stderr.on('data', (c) => { stderr += c; });

    const timeout = setTimeout(() => proc.kill(), CROP_TIMEOUT_MS);

    proc.on('close', () => {
      clearTimeout(timeout);
      try {
        const result = JSON.parse(stdout);
        if (result.cropped) return resolve(outputPath);
        console.error('[videoCrop] crop skipped:', result.reason);
      } catch {
        console.error('[videoCrop] crop_to_subject.py produced invalid output:', (stdout || stderr).slice(-500));
      }
      resolve(null);
    });

    proc.on('error', (err) => {
      clearTimeout(timeout);
      console.error('[videoCrop] failed to spawn python:', err);
      resolve(null);
    });
  });
}

// Moves a multer-uploaded file into persistent storage (so it survives past
// this request, unlike the old immediate-delete behaviour) and crops it.
// Returns { originalPath, croppedPath } -- croppedPath is null if cropping
// failed, which callers treat as "no cropped version available".
async function persistAndCrop(uploadPath, destDir) {
  fs.mkdirSync(destDir, { recursive: true });
  const ext = path.extname(uploadPath) || '.mp4';
  const originalPath = path.join(destDir, `original${ext}`);
  fs.renameSync(uploadPath, originalPath);
  const croppedPath = await cropToSubject(originalPath, path.join(destDir, 'cropped.mp4'));
  return { originalPath, croppedPath };
}

// Pro clips are shared across every user and never modified in place --
// cache the cropped copy at data/04_clips_cropped/<shot_type>/<filename>,
// the same convention scripts/12_video_crop/precrop_pro_database.py uses,
// so a lazily-cropped clip here is reused by later requests and vice versa.
async function croppedProClipPath(clipPath, shotType) {
  const outPath = path.join(PRO_CLIPS_CROPPED_DIR, shotType, path.basename(clipPath));
  if (fs.existsSync(outPath)) return outPath;
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  return cropToSubject(clipPath, outPath);
}

function toUrl(mount, root, absPath) {
  if (!absPath) return null;
  const rel = path.relative(root, absPath).split(path.sep).join('/');
  return `${mount}/${rel}`;
}

module.exports = {
  cropToSubject,
  persistAndCrop,
  croppedProClipPath,
  toUrl,
  PRO_CLIPS_DIR,
  PRO_CLIPS_CROPPED_DIR,
};
