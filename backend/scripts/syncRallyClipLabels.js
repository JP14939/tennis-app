#!/usr/bin/env node
// Syncs rally_clips review verdicts (outcome_tag/archived/boundary_note)
// from an export produced on another machine into THIS database, matched
// by id. Only safe to use when both databases' rally_clips rows for the
// affected ids are known to share the same primary keys (e.g. one was
// originally copied from the other before diverging) -- verify that before
// running this against a database that wasn't seeded that way.
//
//   node scripts/syncRallyClipLabels.js <path-to-export.json>
//
// Export format: [{ id, outcome_tag, archived, boundary_note }, ...]

const fs = require('fs');
const db = require('../src/db');

const exportPath = process.argv[2];
if (!exportPath) {
  console.error('Usage: node scripts/syncRallyClipLabels.js <path-to-export.json>');
  process.exit(1);
}

const rows = JSON.parse(fs.readFileSync(exportPath, 'utf8'));

const existing = db.prepare('SELECT id, outcome_tag, archived FROM rally_clips WHERE id = ?');
const update = db.prepare('UPDATE rally_clips SET outcome_tag = ?, archived = ?, boundary_note = ? WHERE id = ?');

let updated = 0;
let alreadyLabeled = 0;
let missing = 0;

const runAll = db.transaction((rows) => {
  for (const row of rows) {
    const current = existing.get(row.id);
    if (!current) {
      missing += 1;
      console.warn(`No rally_clips row with id ${row.id} on this database -- skipped.`);
      continue;
    }
    if (current.outcome_tag !== null) {
      alreadyLabeled += 1;
      continue;
    }
    update.run(row.outcome_tag, row.archived ? 1 : 0, row.boundary_note ?? null, row.id);
    updated += 1;
  }
});

runAll(rows);

console.log(`Synced: ${updated} updated, ${alreadyLabeled} already labeled here (skipped, not overwritten), ${missing} id(s) not found.`);
