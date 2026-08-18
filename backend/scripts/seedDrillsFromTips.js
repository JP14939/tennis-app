// One-time/re-runnable seed of free Drills content from the existing
// coaching-tips bank (data/08_coaching_ai/coaching_tips_database.json --
// the same data TipsSection.js/TipDiagram.js already use per-analysis) into
// the drill_items table, so the Drills library isn't empty pending manual
// entry through the Dev Page editor. Every tip id here already has a
// matching hand-authored diagram in tipDiagrams/tipVisuals.js, so each
// seeded drill gets a real illustration for free.
//
//   node scripts/seedDrillsFromTips.js
//
// Idempotent by diagram_tip_id: skips (never overwrites) a shot_type whose
// diagram_tip_id already has a non-archived drill_items row, so re-running
// after a Dev Page hand-edit won't clobber it.
const path = require('path');
const fs = require('fs');
const db = require(path.join(__dirname, '..', 'src', 'db'));

const TIPS_DB_PATH = path.join(__dirname, '..', '..', 'data', '08_coaching_ai', 'coaching_tips_database.json');
const SHOT_TYPES = ['forehand', 'backhand', 'serve'];

function main() {
  const data = JSON.parse(fs.readFileSync(TIPS_DB_PATH, 'utf8'));

  const exists = db.prepare('SELECT 1 FROM drill_items WHERE diagram_tip_id = ? AND archived = 0');
  const insert = db.prepare(`
    INSERT INTO drill_items (kind, shot_type, title, video_path, explanation, emphasis, diagram_tip_id, is_premium, sort_order)
    VALUES ('drill', ?, ?, NULL, ?, ?, ?, 0, ?)
  `);

  let inserted = 0;
  let skipped = 0;

  for (const shotType of SHOT_TYPES) {
    const entries = data[shotType] ?? [];
    entries.forEach((entry, i) => {
      if (exists.get(entry.id)) {
        console.log(`skip  ${entry.id} (already seeded)`);
        skipped += 1;
        return;
      }
      const explanation = entry.tips?.moderate?.[0];
      if (!explanation || !entry.drill) {
        console.log(`skip  ${entry.id} (missing explanation or drill text)`);
        skipped += 1;
        return;
      }
      insert.run(shotType, entry.description, explanation, entry.drill, entry.id, i);
      console.log(`insert ${entry.id} (${shotType})`);
      inserted += 1;
    });
  }

  console.log(`\nDone. Inserted ${inserted}, skipped ${skipped}.`);
}

main();
