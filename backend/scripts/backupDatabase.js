#!/usr/bin/env node
// Snapshots the live database via SQLite's Online Backup API (better-sqlite3's
// db.backup()), which is safe to run against a live WAL-mode database with
// concurrent readers/writers -- no need to stop the server for this.
//
//   node scripts/backupDatabase.js                  # backend/data/app.db
//   node scripts/backupDatabase.js <path-to.db>
//
// Writes a timestamped copy into backend/data/backups/ and prunes local
// snapshots beyond RETENTION_COUNT. This is the LOCAL half of durability
// only -- a copy sitting on the same disk as the original doesn't survive
// losing that disk/VM. Off-box shipping (rclone -> Backblaze B2) is a
// separate cron step layered on top of this script; see TODO_MANUAL.md.
//
// Exits 0 on success, 1 on failure (cron/alerting-friendly, same convention
// as verifyIntegrity.js).

const path = require('path');
const fs = require('fs');
const Database = require('better-sqlite3');

const DEFAULT_DB_PATH = path.join(__dirname, '..', 'data', 'app.db');
const BACKUP_DIR = path.join(__dirname, '..', 'data', 'backups');
const RETENTION_COUNT = 14;

const dbPath = process.argv[2] || process.env.DB_PATH || DEFAULT_DB_PATH;

function timestamp() {
  return new Date().toISOString().replace(/:/g, '-').replace(/\.\d+Z$/, 'Z');
}

function pruneOldBackups() {
  const files = fs.readdirSync(BACKUP_DIR)
    .filter((f) => f.startsWith('app-') && f.endsWith('.db'))
    .sort(); // ISO timestamps in the filename sort chronologically as strings
  const toDelete = files.slice(0, Math.max(0, files.length - RETENTION_COUNT));
  for (const f of toDelete) {
    // The backup destination is a byte-for-byte copy of a WAL-mode source, so
    // it can carry its own -wal/-shm sidecars -- delete those too or they
    // orphan silently and retention stops actually bounding disk usage.
    for (const suffix of ['', '-wal', '-shm']) {
      const p = path.join(BACKUP_DIR, f + suffix);
      if (fs.existsSync(p)) fs.unlinkSync(p);
    }
    console.log(`pruned ${f}`);
  }
}

async function main() {
  fs.mkdirSync(BACKUP_DIR, { recursive: true });

  let db;
  try {
    db = new Database(dbPath, { readonly: true, fileMustExist: true });
  } catch (err) {
    console.error(`Could not open database at ${dbPath}\n  ${err.message}`);
    process.exit(1);
  }

  const destPath = path.join(BACKUP_DIR, `app-${timestamp()}.db`);
  try {
    await db.backup(destPath);
  } finally {
    db.close();
  }

  // db.backup() copies the source's page data verbatim, including its WAL
  // journal mode -- switching the copy to DELETE mode folds any pending
  // -wal content into the main file and removes the sidecars, so the single
  // .db file left behind is a complete, self-contained snapshot (important
  // for off-box shipping, where only that one file gets copied out).
  const destDb = new Database(destPath);
  destDb.pragma('journal_mode = DELETE');
  destDb.close();

  const { size } = fs.statSync(destPath);
  console.log(`backed up ${dbPath} -> ${destPath} (${(size / 1024 / 1024).toFixed(2)} MB)`);

  pruneOldBackups();
}

main().catch((err) => {
  console.error('backup failed:', err.message);
  process.exit(1);
});
