#!/usr/bin/env node
// Exports one user's `analyses` rows from the LOCAL database, plus the list
// of video-clip subdirectories those rows reference, so they can be merged
// into the hosted database without losing the video files (this exact
// failure mode -- rows migrated without their clips -- already happened
// once, see HANDOVER.md item #42).
//
//   node scripts/exportAnalysesForMigration.js <email>
//
// Writes backend/data/migration/<email>-analyses.json containing the rows
// and the resolved clip directories. Read-only against the source database.

const path = require('path');
const fs = require('fs');
const Database = require('better-sqlite3');
const { DATA_DIR } = require('../src/config/paths');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '..', 'data', 'app.db');
const USER_CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'user_clips');
const OUT_DIR = path.join(__dirname, '..', 'data', 'migration');

const email = process.argv[2];
if (!email) {
  console.error('Usage: node scripts/exportAnalysesForMigration.js <email>');
  process.exit(1);
}

const db = new Database(DB_PATH, { readonly: true, fileMustExist: true });

const user = db.prepare('SELECT id, email FROM users WHERE email = ?').get(email);
if (!user) {
  console.error(`No local user found with email ${email}`);
  process.exit(1);
}

const rows = db.prepare(
  'SELECT shot_type, similarity, pro_id, angle_label, tip, result_json, created_at FROM analyses WHERE user_id = ? ORDER BY id'
).all(user.id);

// Pull the /user-clips/<uploadId>/... paths referenced by each row's
// result_json so the exact subdirectories needed can be rsynced separately
// -- transferring only what's referenced, not the whole (potentially huge)
// user_clips directory.
const clipDirs = new Set();
function collectClipDir(url) {
  if (!url || !url.startsWith('/user-clips/')) return;
  const rel = url.slice('/user-clips/'.length);
  const uploadId = rel.split('/')[0];
  if (uploadId) clipDirs.add(uploadId);
}

for (const row of rows) {
  let result;
  try {
    result = JSON.parse(row.result_json);
  } catch {
    continue;
  }
  collectClipDir(result.user_clip_url);
  collectClipDir(result.user_clip_cropped_url);
}

const missingDirs = [];
for (const uploadId of clipDirs) {
  const dirPath = path.join(USER_CLIPS_DIR, uploadId);
  if (!fs.existsSync(dirPath)) missingDirs.push(uploadId);
}

fs.mkdirSync(OUT_DIR, { recursive: true });
const outPath = path.join(OUT_DIR, `${email}-analyses.json`);
fs.writeFileSync(outPath, JSON.stringify({
  email,
  exportedAt: new Date().toISOString(),
  rows,
  clipDirs: [...clipDirs],
}, null, 2));

console.log(`Exported ${rows.length} analyses for ${email} -> ${outPath}`);
console.log(`Referenced clip subdirectories (${clipDirs.size}), transfer these from ${USER_CLIPS_DIR}:`);
for (const uploadId of clipDirs) console.log(`  ${uploadId}`);
if (missingDirs.length) {
  console.warn(`\nWARNING: ${missingDirs.length} referenced clip dir(s) do not exist locally -- those rows' videos are already unavailable:`);
  for (const uploadId of missingDirs) console.warn(`  ${uploadId}`);
}

db.close();
