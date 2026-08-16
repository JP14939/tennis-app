// One-time bulk seed of every OSM-tagged tennis court in England, so any
// location a user opens Find Games in already has real data instead of
// relying on GET /courts's per-area lazy self-heal (routes/courts.js) to
// have been triggered there first.
//
//   node scripts/seedEngland.js
//
// Upserts on osm_id (see overpassCourts.js), so re-running later to refresh
// is safe. Single large Overpass query -- can take a couple of minutes.
const path = require('path');
const { seedCourtsInArea } = require(path.join(__dirname, '..', 'src', 'utils', 'overpassCourts'));

async function main() {
  console.log('Querying Overpass for every tennis court in England (this can take a couple of minutes)...');
  const inserted = await seedCourtsInArea('England');
  console.log(`Upserted ${inserted} courts into the database.`);
}

main().catch((err) => {
  console.error('Seed failed:', err.message);
  process.exit(1);
});
