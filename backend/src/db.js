const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DATA_DIR = path.join(__dirname, '..', 'data');
fs.mkdirSync(DATA_DIR, { recursive: true });

const db = new Database(path.join(DATA_DIR, 'app.db'));

// WAL needs proper mmap/shared-memory support from the underlying
// filesystem -- works fine on a normal disk or a native Linux bind mount,
// but some virtualized mounts (confirmed: Docker Desktop for Windows' file
// sharing layer) can't open the .db-shm file and throw SQLITE_IOERR on
// startup. Non-fatal: fall back to the default rollback-journal mode rather
// than crash the whole server over a filesystem that doesn't support WAL.
try {
  db.pragma('journal_mode = WAL');
} catch (err) {
  console.error('[db] WAL mode unavailable on this filesystem, falling back to default journal mode:', err.message);
}

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name          TEXT NOT NULL,
    tier          TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'premium')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS analyses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    shot_type    TEXT NOT NULL,
    similarity   REAL NOT NULL,
    pro_id       TEXT,
    angle_label  TEXT,
    tip          TEXT,
    result_json  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS analysis_usage (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- Audit trail only -- users.tier stays the single source of truth for
  -- gating, updated directly by the RevenueCat webhook handler. This table
  -- just keeps the raw event history for debugging payment issues.
  CREATE TABLE IF NOT EXISTS payment_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id),
    event_type   TEXT NOT NULL,
    raw_payload  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- One row per uploaded match/practice video processed by the rally
  -- detector. Long-running (pose extraction over 10+ minutes of footage),
  -- so this is a background job the app polls for rather than a
  -- request-response call like /api/analyse.
  CREATE TABLE IF NOT EXISTS highlight_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    video_path   TEXT NOT NULL,
    error        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
  );

  -- One row per detected rally clip. outcome_tag stays NULL until the user
  -- reviews it; archived flips to 1 only once they actually save it (not
  -- just because it was detected), so a rejected/skipped clip never shows
  -- up in the Archive.
  CREATE TABLE IF NOT EXISTS rally_clips (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       INTEGER NOT NULL REFERENCES highlight_jobs(id),
    user_id      INTEGER NOT NULL REFERENCES users(id),
    clip_path    TEXT NOT NULL,
    start_sec    REAL NOT NULL,
    end_sec      REAL NOT NULL,
    duration_sec REAL NOT NULL,
    swing_count  INTEGER,
    outcome_tag  TEXT,
    archived     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS push_tokens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    token        TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );
`);

// No migrations framework here -- CREATE TABLE IF NOT EXISTS above is
// naturally idempotent, but adding a column to an existing table needs its
// own guard so this doesn't error on every restart once the column exists.
const hasNotifCol = db.prepare("PRAGMA table_info(users)").all()
  .some((c) => c.name === 'notifications_enabled');
if (!hasNotifCol) {
  db.exec('ALTER TABLE users ADD COLUMN notifications_enabled INTEGER NOT NULL DEFAULT 1');
}

module.exports = db;
