// Runs the same rally-detection logic as POST /highlights/upload
// (routes/highlights.js's runJob()), but against a video file already
// sitting on this machine's disk -- for files too large for that route's
// 2GB multer limit, or any other case where uploading a file that's
// already local over HTTP would just be a slow, pointless copy.
//
//   node scripts/runLocalHighlightJob.js <video_path> <user_email>
//
// Prints the resulting highlight_jobs id on success -- feed that into
// scripts/15_batch_analysis/analyze_rallies_parallel.py next.
const path = require('path');
const fs = require('fs');
const { spawnSync } = require('child_process');
const db = require(path.join(__dirname, '..', 'src', 'db'));
const { PYTHON, DATA_DIR } = require(path.join(__dirname, '..', 'src', 'config', 'paths'));

const DETECTOR = path.join(__dirname, '..', 'src', 'services', 'rally_detector.py');
const CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'highlight_clips');

function main() {
  const [videoPath, userEmail] = process.argv.slice(2);
  if (!videoPath || !userEmail) {
    console.error('Usage: node runLocalHighlightJob.js <video_path> <user_email>');
    process.exit(1);
  }
  if (!fs.existsSync(videoPath)) {
    console.error(`Video not found: ${videoPath}`);
    process.exit(1);
  }

  const user = db.prepare('SELECT id FROM users WHERE email = ?').get(userEmail);
  if (!user) {
    console.error(`No user with email ${userEmail}`);
    process.exit(1);
  }

  const info = db.prepare(
    `INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, ?, 'processing')`
  ).run(user.id, videoPath);
  const jobId = info.lastInsertRowid;
  console.log(`Created highlight_jobs row ${jobId}, running rally_detector.py (this can take a while for a full match video)...`);

  const outputDir = path.join(CLIPS_DIR, String(user.id), String(jobId));
  const result = spawnSync(PYTHON, [DETECTOR, videoPath, outputDir], {
    encoding: 'utf8',
    maxBuffer: 50 * 1024 * 1024,
  });

  if (result.error) {
    db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`)
      .run(String(result.error), jobId);
    console.error('Failed to spawn python:', result.error);
    process.exit(1);
  }

  if (result.status !== 0) {
    let error = 'Rally detection failed';
    try { error = JSON.parse(result.stdout).error || error; } catch { /* stdout wasn't JSON */ }
    db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`)
      .run(error, jobId);
    console.error('rally_detector.py failed:', (result.stderr || '').slice(-2000));
    process.exit(1);
  }

  let parsed;
  try {
    parsed = JSON.parse(result.stdout);
  } catch {
    db.prepare(`UPDATE highlight_jobs SET status = 'failed', error = ?, completed_at = datetime('now') WHERE id = ?`)
      .run('Detection produced invalid output', jobId);
    console.error('Failed to parse rally_detector.py output:', result.stdout.slice(-2000));
    process.exit(1);
  }

  const insert = db.prepare(`
    INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `);
  for (const rally of parsed.rallies) {
    insert.run(jobId, user.id, rally.clip_path, rally.start_sec, rally.end_sec, rally.duration_sec, rally.swing_count);
  }
  db.prepare(`UPDATE highlight_jobs SET status = 'done', completed_at = datetime('now') WHERE id = ?`).run(jobId);

  console.log(`Done. job_id=${jobId} rallies_detected=${parsed.rallies_detected} swings_candidates=${parsed.swings_candidates} swings_verified=${parsed.swings_verified}`);
}

main();
