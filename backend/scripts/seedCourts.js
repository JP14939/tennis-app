// One-time/re-runnable seed of real tennis court locations from
// OpenStreetMap's free Overpass API into the `courts` table. Not called at
// request time (Overpass has rate limits) -- run manually for a local area:
//
//   node scripts/seedCourts.js --lat=51.5074 --lng=-0.1278 --radiusKm=15
//
// Upserts on osm_id, so re-running for the same area is safe. Shares its
// fetch/upsert logic with the lazy self-heal path in routes/courts.js --
// see utils/overpassCourts.js.

const path = require('path');
const { seedCourtsNear } = require(path.join(__dirname, '..', 'src', 'utils', 'overpassCourts'));

function parseArgs() {
  const args = {};
  for (const arg of process.argv.slice(2)) {
    const [key, value] = arg.replace(/^--/, '').split('=');
    args[key] = value;
  }
  const lat = parseFloat(args.lat);
  const lng = parseFloat(args.lng);
  const radiusKm = parseFloat(args.radiusKm) || 15;
  if (Number.isNaN(lat) || Number.isNaN(lng)) {
    console.error('Usage: node seedCourts.js --lat=<lat> --lng=<lng> [--radiusKm=15]');
    process.exit(1);
  }
  return { lat, lng, radiusKm };
}

async function main() {
  const { lat, lng, radiusKm } = parseArgs();
  console.log(`Querying Overpass for tennis courts within ${radiusKm}km of ${lat},${lng}...`);
  const inserted = await seedCourtsNear(lat, lng, radiusKm);
  console.log(`Upserted ${inserted} courts into the database.`);
}

main().catch((err) => {
  console.error('Seed failed:', err.message);
  process.exit(1);
});
