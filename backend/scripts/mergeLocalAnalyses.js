#!/usr/bin/env node
// Merges analyses rows exported by exportAnalysesForMigration.js into THIS
// database as new rows, resolving the target user by email (never assuming
// the source and target databases share the same user id). Never touches
// existing rows -- pure INSERT, no REPLACE, and safe to re-run (skips rows
// that already look present for the same user).
//
//   node scripts/mergeLocalAnalyses.js <path-to-export.json>

const path = require('path');
const fs = require('fs');
const db = require('../src/db');

const exportPath = process.argv[2];
if (!exportPath) {
  console.error('Usage: node scripts/mergeLocalAnalyses.js <path-to-export.json>');
  process.exit(1);
}

const { email, rows } = JSON.parse(fs.readFileSync(exportPath, 'utf8'));

const user = db.prepare('SELECT id FROM users WHERE email = ?').get(email);
if (!user) {
  console.error(`No user with email ${email} exists on THIS database -- refusing to guess/create one.`);
  process.exit(1);
}

const alreadyExists = db.prepare(
  'SELECT 1 FROM analyses WHERE user_id = ? AND shot_type = ? AND similarity = ? AND created_at = ?'
);
const insert = db.prepare(`
  INSERT INTO analyses (user_id, shot_type, similarity, pro_id, angle_label, tip, result_json, created_at)
  VALUES (@user_id, @shot_type, @similarity, @pro_id, @angle_label, @tip, @result_json, @created_at)
`);

let inserted = 0;
let skipped = 0;

const runAll = db.transaction((rows) => {
  for (const row of rows) {
    if (alreadyExists.get(user.id, row.shot_type, row.similarity, row.created_at)) {
      skipped += 1;
      continue;
    }
    insert.run({ ...row, user_id: user.id });
    inserted += 1;
  }
});

runAll(rows);

console.log(`Merged for ${email} (target user id ${user.id}): ${inserted} inserted, ${skipped} skipped as already present.`);
