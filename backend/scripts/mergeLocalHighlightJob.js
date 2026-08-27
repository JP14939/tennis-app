#!/usr/bin/env node
// Merges one highlight_jobs row (and its rally_clips) from a local export
// into THIS database. Unlike analyses, rally_clips.clip_path is stored as
// an ABSOLUTE filesystem path (see backend/src/routes/highlights.js's
// toClipUrl, which does path.relative(CLIPS_DIR, clip_path) at request
// time) -- so paths captured on one machine are meaningless on another and
// must be rewritten to this machine's CLIPS_DIR before inserting, or clip
// URLs silently break.
//
//   node scripts/mergeLocalHighlightJob.js <path-to-export.json>
//
// The export JSON is produced by exportHighlightJobForMigration.js and
// looks like: { email, job: {...}, rallyClips: [...] } where clipPathRel
// on each rally clip is relative to the SOURCE machine's highlight_clips
// dir, ready to be re-anchored to this machine's CLIPS_DIR.

const path = require('path');
const fs = require('fs');
const db = require('../src/db');
const { DATA_DIR } = require('../src/config/paths');

const CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'highlight_clips');

const exportPath = process.argv[2];
if (!exportPath) {
  console.error('Usage: node scripts/mergeLocalHighlightJob.js <path-to-export.json>');
  process.exit(1);
}

const { email, job, rallyClips } = JSON.parse(fs.readFileSync(exportPath, 'utf8'));

const user = db.prepare('SELECT id FROM users WHERE email = ?').get(email);
if (!user) {
  console.error(`No user with email ${email} exists on THIS database -- refusing to guess/create one.`);
  process.exit(1);
}

const existingJob = db.prepare(
  'SELECT id FROM highlight_jobs WHERE user_id = ? AND created_at = ?'
).get(user.id, job.created_at);
if (existingJob) {
  console.log(`highlight_jobs row for ${email} at ${job.created_at} already present (id ${existingJob.id}) -- nothing to do.`);
  process.exit(0);
}

const insertJob = db.prepare(`
  INSERT INTO highlight_jobs (user_id, status, video_path, error, created_at, completed_at)
  VALUES (@user_id, @status, @video_path, @error, @created_at, @completed_at)
`);
const insertClip = db.prepare(`
  INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count, outcome_tag, archived, created_at, boundary_note)
  VALUES (@job_id, @user_id, @clip_path, @start_sec, @end_sec, @duration_sec, @swing_count, @outcome_tag, @archived, @created_at, @boundary_note)
`);

const run = db.transaction(() => {
  const info = insertJob.run({ ...job, user_id: user.id });
  const newJobId = info.lastInsertRowid;

  for (const clip of rallyClips) {
    const clipPath = path.join(CLIPS_DIR, clip.clipPathRel);
    if (!fs.existsSync(clipPath)) {
      throw new Error(`Expected clip file missing on this machine: ${clipPath} -- transfer it before running this script.`);
    }
    insertClip.run({
      ...clip,
      job_id: newJobId,
      user_id: user.id,
      clip_path: clipPath,
    });
  }

  return newJobId;
});

const newJobId = run();
console.log(`Merged highlight job for ${email}: new id ${newJobId}, ${rallyClips.length} rally clip(s).`);
