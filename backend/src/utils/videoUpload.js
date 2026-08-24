// Shared multer building blocks for every route that accepts an uploaded
// video (analyse.js, compareVideos.js, highlights.js, calibration.js,
// dev.js's drill-video editor). Every one of these used to build its
// stored filename from `path.extname(file.originalname)` with no check at
// all -- an attacker-controlled extension (e.g. ".html", ".svg") on an
// upload that later gets persisted and served back through one of the
// `/user-clips`, `/comparison-clips`, `/highlight-clips`, or `/drill-clips`
// static mounts (server.js) would be served with a browser-guessed
// Content-Type matching that extension instead of a video one -- a stored
// XSS/HTML-injection vector if the uploaded bytes ever reach one of those
// static directories with a non-video extension attached.
const path = require('path');

// Deliberately small and video-only -- this app never needs to accept
// anything else through these fields. Videos exported by a phone camera
// realistically land in one of these containers.
const ALLOWED_VIDEO_EXTENSIONS = new Set(['.mp4', '.mov', '.m4v', '.avi', '.webm', '.mkv', '.3gp']);

class UnsupportedFileTypeError extends Error {
  constructor(message) {
    super(message);
    this.name = 'UnsupportedFileTypeError';
  }
}

// Used inside a multer diskStorage `filename` callback in place of the old
// `path.extname(file.originalname) || '.mp4'` -- falls back to '.mp4'
// instead of trusting whatever extension the client sent, same as before,
// but only when that extension is actually a recognized video one.
function safeVideoExt(originalname) {
  const ext = path.extname(originalname || '').toLowerCase();
  return ALLOWED_VIDEO_EXTENSIONS.has(ext) ? ext : '.mp4';
}

// multer `fileFilter` -- rejects the upload outright (before it's even
// written to disk) when the client-supplied filename doesn't look like a
// video at all, rather than silently accepting it and just renaming its
// extension. Belt-and-braces alongside safeVideoExt() above: this stops the
// file being accepted in the first place; that stops a non-video extension
// naming whatever does get stored.
function videoFileFilter(req, file, cb) {
  const ext = path.extname(file.originalname || '').toLowerCase();
  if (!ALLOWED_VIDEO_EXTENSIONS.has(ext)) {
    return cb(new UnsupportedFileTypeError(`Unsupported file type "${ext || '(none)'}" -- expected a video file`));
  }
  cb(null, true);
}

module.exports = { safeVideoExt, videoFileFilter, UnsupportedFileTypeError };
