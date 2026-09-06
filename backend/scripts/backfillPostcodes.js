// One-off/re-runnable backfill for courts.postcode and clubs.postcode on
// rows that don't have one yet -- covers the ~33k OSM-seeded courts (and any
// pre-existing clubs) that predate the postcode column, plus anything a
// previous run's failed lookups left null. Safe to re-run: only touches rows
// where postcode IS NULL, so it never re-queries a row that already has one.
//
//   node scripts/backfillPostcodes.js
//
// Uses the bulk reverse-geocode endpoint (utils/postcodeLookup.js ->
// postcodes.io, free, no API key) in batches of 100, not one request per
// row -- the request path (routes/courts.js) and the clustering script
// (scripts/clusterCourts.js) already do single best-effort lookups inline
// for NEW rows; this script is only for the backlog that already existed
// before the postcode column did.
const path = require('path');
const db = require(path.join(__dirname, '..', 'src', 'db'));
const { bulkLookupPostcodes } = require(path.join(__dirname, '..', 'src', 'utils', 'postcodeLookup'));

async function backfillTable(table) {
  const rows = db.prepare(`SELECT id, latitude, longitude FROM ${table} WHERE postcode IS NULL`).all();
  if (rows.length === 0) {
    console.log(`${table}: nothing to backfill`);
    return;
  }

  console.log(`${table}: looking up ${rows.length} row(s) with no postcode...`);
  const postcodes = await bulkLookupPostcodes(rows);

  const update = db.prepare(`UPDATE ${table} SET postcode = ? WHERE id = ?`);
  const applyAll = db.transaction(() => {
    let updated = 0;
    for (const [id, postcode] of postcodes) {
      if (postcode) {
        update.run(postcode, id);
        updated += 1;
      }
    }
    return updated;
  });
  const updated = applyAll();
  console.log(`${table}: resolved ${updated}/${rows.length} (the rest had nothing postcodes.io could match)`);
}

async function main() {
  await backfillTable('courts');
  await backfillTable('clubs');
}

if (require.main === module) {
  main().catch((err) => {
    console.error('backfillPostcodes failed:', err.message);
    process.exit(1);
  });
}

module.exports = { backfillTable };
