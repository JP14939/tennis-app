#!/usr/bin/env node
// Exports one highlight_jobs row (and its rally_clips) from the LOCAL
// database for migration to another machine. clipPathRel is stored relative
// to this machine's highlight_clips dir so it can be re-anchored to the
// target machine's own DATA_DIR by mergeLocalHighlightJob.js.
//
//   node scripts/exportHighlightJobForMigration.js <email> <jobId>

const path = require('path');
const fs = require('fs');
const Database = require('better-sqlite3');
const { DATA_DIR } = require('../src/config/paths');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '..', 'data', 'app.db');
const CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'highlight_clips');
const OUT_DIR = path.join(__dirname, '..', 'data', 'migration');

const [email, jobIdArg] = process.argv.slice(2);
const jobId = Number(jobIdArg);
if (!email || !jobId) {
  console.error('Usage: node scripts/exportHighlightJobForMigration.js <email> <jobId>');
  process.exit(1);
}

const db = new Database(DB_PATH, { readonly: true, fileMustExist: true });

const user = db.prepare('SELECT id, email FROM users WHERE email = ?').get(email);
if (!user) {
  console.error(`No local user found with email ${email}`);
  process.exit(1);
}

const job = db.prepare(
  'SELECT status, video_path, error, created_at, completed_at FROM highlight_jobs WHERE id = ? AND user_id = ?'
).get(jobId, user.id);
if (!job) {
  console.error(`No highlight_jobs row with id ${jobId} for ${email}`);
  process.exit(1);
}

const clips = db.prepare(
  'SELECT clip_path, start_sec, end_sec, duration_sec, swing_count, outcome_tag, archived, created_at, boundary_note FROM rally_clips WHERE job_id = ? ORDER BY id'
).all(jobId);

const rallyClips = [];
const missing = [];
for (const clip of clips) {
  if (!fs.existsSync(clip.clip_path)) {
    missing.push(clip.clip_path);
    continue;
  }
  const clipPathRel = path.relative(CLIPS_DIR, clip.clip_path).split(path.sep).join('/');
  rallyClips.push({ ...clip, clipPathRel });
}

fs.mkdirSync(OUT_DIR, { recursive: true });
const outPath = path.join(OUT_DIR, `${email}-highlight-job-${jobId}.json`);
fs.writeFileSync(outPath, JSON.stringify({ email, job, rallyClips }, null, 2));

console.log(`Exported highlight job ${jobId} (${rallyClips.length} clip(s)) -> ${outPath}`);
console.log('Referenced clip files, transfer these:');
for (const clip of rallyClips) console.log(`  ${clip.clip_path}`);
if (missing.length) {
  console.warn(`\nWARNING: ${missing.length} clip file(s) missing locally, excluded:`);
  for (const p of missing) console.warn(`  ${p}`);
}

db.close();
