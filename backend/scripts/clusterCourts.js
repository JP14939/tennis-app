// One-time/re-runnable clustering of courts into "clubs" -- groups of 2+
// courts close enough together to be one real venue (a tennis club, a park
// with several courts), so users can watch the whole venue instead of just
// one court. Not automatic/scheduled: courts don't move once seeded, so
// this only needs re-running when new courts get added to an area (e.g.
// after seedCourts.js/seedEngland.js pull in more OSM data).
//
//   node scripts/clusterCourts.js
//
// Reconciles against existing clubs (matched by overlapping court
// membership) rather than wiping and recreating every run, so existing
// club_watches rows survive a re-run -- only the courts/name/centroid of a
// matched club get updated, and genuinely new clusters get a new club.

const path = require('path');
const db = require(path.join(__dirname, '..', 'src', 'db'));

const EARTH_RADIUS_KM = 6371;
// Courts within this distance of each other are treated as one venue.
// Tennis clubs/park court blocks are typically tens of meters apart; 250m
// comfortably covers a real multi-court venue without merging two separate
// clubs that happen to be in the same neighborhood.
const CLUSTER_RADIUS_KM = 0.25;

function haversineKm(lat1, lng1, lat2, lng2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function centroid(cluster) {
  return {
    lat: cluster.reduce((s, c) => s + c.latitude, 0) / cluster.length,
    lng: cluster.reduce((s, c) => s + c.longitude, 0) / cluster.length,
  };
}

// Grows each cluster against its own running centroid rather than
// court-to-nearest-neighbor -- a naive connected-components graph (any
// court within radius of ANY cluster member) chains through dense areas
// and produces clusters spanning far more real-world distance than a
// single venue ever would (confirmed on real data: single-linkage produced
// clusters up to 57 courts before this fix, vs. a real club's typical
// handful). Requiring proximity to the centroid instead means a court only
// joins if it's actually near the venue's center, so growth in one
// direction can't drag in courts from an unrelated venue further away.
function clusterCourts(courts) {
  const clusters = [];
  const visited = new Set();

  for (const seed of courts) {
    if (visited.has(seed.id)) continue;
    const cluster = [seed];
    visited.add(seed.id);

    let grew = true;
    while (grew) {
      grew = false;
      const { lat, lng } = centroid(cluster);
      for (const other of courts) {
        if (visited.has(other.id)) continue;
        if (haversineKm(lat, lng, other.latitude, other.longitude) <= CLUSTER_RADIUS_KM) {
          visited.add(other.id);
          cluster.push(other);
          grew = true;
        }
      }
    }
    clusters.push(cluster);
  }
  return clusters.filter((c) => c.length >= 2);
}

function deriveName(cluster) {
  // Real OSM data often tags every court at one venue with the same name
  // (e.g. every court at "Riverside Tennis Club" carries that exact name) --
  // use it directly when the majority agree, since that's the real venue
  // name rather than a guess.
  const counts = new Map();
  for (const c of cluster) {
    counts.set(c.name, (counts.get(c.name) || 0) + 1);
  }
  const [topName, topCount] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  if (topCount > cluster.length / 2 && topName !== 'Tennis Court') {
    return topName;
  }
  // Fall back to the nearest-to-centroid court's own name -- more useful
  // than a generic label when nothing named the venue consistently. Prefer
  // a real (non-generic) name even if it's not literally the closest court
  // -- confirmed on real data that the closest court is very often the
  // generic OSM default ("Tennis Court") while a real venue name sits one
  // court further out in the same cluster.
  const { lat, lng } = centroid(cluster);
  const byDistance = [...cluster].sort(
    (a, b) => haversineKm(lat, lng, a.latitude, a.longitude) - haversineKm(lat, lng, b.latitude, b.longitude)
  );
  const nearest = byDistance.find((c) => c.name !== 'Tennis Court') ?? byDistance[0];
  return `Courts near ${nearest.name}`;
}

function reconcile(cluster) {
  const { lat, lng } = centroid(cluster);
  const name = deriveName(cluster);
  const courtIds = cluster.map((c) => c.id);

  // Reuse an existing club if any of this cluster's courts already belong
  // to one -- keeps club_id (and therefore club_watches) stable across
  // re-runs instead of creating a duplicate club every time.
  const placeholders = courtIds.map(() => '?').join(',');
  const existing = db.prepare(
    `SELECT DISTINCT club_id FROM club_courts WHERE court_id IN (${placeholders})`
  ).all(...courtIds);

  let clubId;
  if (existing.length > 0) {
    clubId = existing[0].club_id;
    db.prepare('UPDATE clubs SET name = ?, latitude = ?, longitude = ? WHERE id = ?')
      .run(name, lat, lng, clubId);
  } else {
    const info = db.prepare('INSERT INTO clubs (name, latitude, longitude) VALUES (?, ?, ?)')
      .run(name, lat, lng);
    clubId = info.lastInsertRowid;
  }

  for (const courtId of courtIds) {
    db.prepare('INSERT INTO club_courts (club_id, court_id) VALUES (?, ?) ON CONFLICT(court_id) DO UPDATE SET club_id = excluded.club_id')
      .run(clubId, courtId);
  }
  return { clubId, name, courtCount: courtIds.length };
}

function main() {
  const courts = db.prepare('SELECT id, name, latitude, longitude FROM courts').all();
  const clusters = clusterCourts(courts);

  console.log(`${courts.length} courts, ${clusters.length} clusters of 2+ found`);
  for (const cluster of clusters) {
    const { clubId, name, courtCount } = reconcile(cluster);
    console.log(`  club ${clubId}: "${name}" (${courtCount} courts)`);
  }
}

main();
