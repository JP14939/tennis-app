const path = require('path');
const fs = require('fs');
const { DATA_DIR } = require('../config/paths');
const {
  persistAndCrop, croppedProClipPath, toUrl, PRO_CLIPS_DIR, PRO_CLIPS_CROPPED_DIR,
} = require('../utils/videoCrop');

const USER_CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'user_clips');

// Shared post-processing for a pro_matcher.py result -- extracted out of
// routes/analyse.js so routes/highlights.js's per-shot analyze endpoint
// (analyzing one shot out of an already-detected rally clip, rather than a
// fresh upload) produces a byte-for-byte identical response shape without a
// second hand-maintained copy of this logic drifting from the original.
//
// `deleteSource`: analyse.js's caller passes true -- its source is a
// throwaway multer upload, gone once persisted. highlights.js's caller must
// pass false -- its source is the persisted rally_clips file, still needed
// for this rally's OTHER shots and any future re-analysis of this one.
async function finalizeAnalysisResult(result, { sourcePath, destDir, shotType, deleteSource }) {
  const { originalPath, croppedPath } = await persistAndCrop(sourcePath, destDir, { deleteSource });

  // Defensive check -- don't hand back a URL that 404s or points at a
  // truncated file (e.g. an interrupted upload on a bad connection, or a
  // full disk during the copy above).
  let persistedOk = false;
  try {
    persistedOk = fs.statSync(originalPath).size > 0;
  } catch { /* file missing */ }
  if (!persistedOk) {
    console.error('[finalizeAnalysisResult] persisted user clip missing or empty:', originalPath);
  }

  result.user_clip_url = persistedOk ? toUrl('/user-clips', USER_CLIPS_DIR, originalPath) : null;
  result.user_clip_cropped_url = persistedOk ? toUrl('/user-clips', USER_CLIPS_DIR, croppedPath) : null;

  const top = result.matches?.[0];
  if (top?.clip_path) {
    // pro_database.json stores clip_path relative to PRO_CLIPS_DIR, resolved
    // to a real absolute path here (see analyse.js's original comment on
    // this for why -- cross-machine deploys break a stored-absolute path).
    const proClipAbsPath = path.join(PRO_CLIPS_DIR, top.clip_path);
    const proCroppedPath = await croppedProClipPath(proClipAbsPath, top.shot_type || shotType);

    let proClipOk = false;
    try {
      proClipOk = fs.statSync(proClipAbsPath).size > 0;
    } catch { /* file missing */ }
    if (!proClipOk) {
      console.error('[finalizeAnalysisResult] matched pro clip missing or empty:', proClipAbsPath);
    }

    top.pro_clip_url = proClipOk ? toUrl('/pro-clips', PRO_CLIPS_DIR, proClipAbsPath) : null;
    top.pro_clip_cropped_url = proClipOk
      ? toUrl('/pro-clips-cropped', PRO_CLIPS_CROPPED_DIR, proCroppedPath)
      : null;
  }

  // originalPath/persistedOk returned alongside the mutated result -- some
  // callers (analyse.js's fire-and-forget contact-frame logger) need the
  // actual persisted file path, not just the URL derived from it.
  return { result, originalPath, persistedOk };
}

module.exports = { finalizeAnalysisResult, USER_CLIPS_DIR };
