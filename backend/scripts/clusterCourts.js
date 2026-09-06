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
const { haversineKm } = require(path.join(__dirname, '..', 'src', 'utils', 'geo'));
const { lookupPostcode } = require(path.join(__dirname, '..', 'src', 'utils', 'postcodeLookup'));

// Courts within this distance of a NEIGHBOUR are treated as one mesh --
// a true node-graph connected-components clustering, not the earlier
// centroid-growing approach (see git history): courts are nodes, an edge
// connects two courts <=100m apart, and a club is one connected component.
// A straight line of courts each 90m from the next is deliberately one club
// even though the two ends are hundreds of meters apart -- confirmed with
// the product owner directly, including the tradeoff against a stricter
// "every pair within 100m" reading. 100m (vs. the old 250m) keeps this
// tighter than the single-linkage chaining that caused the historical
// 57-court mega-cluster bug: a much smaller radius means far fewer edges
// per court in practice, so a chain has to be a genuinely dense line of
// real neighbouring courts to form, not just "somewhere in the same park".
const CLUSTER_RADIUS_KM = 0.1;

// Union-find (disjoint-set) over court ids -- the standard structure for
// "connected components of a graph" without materializing the graph's
// adjacency list. find() with path compression; union() by rank isn't
// needed at this scale (a few thousand courts).
function makeUnionFind(ids) {
  const parent = new Map(ids.map((id) => [id, id]));
  function find(id) {
    while (parent.get(id) !== id) {
      parent.set(id, parent.get(parent.get(id))); // path compression (halving)
      id = parent.get(id);
    }
    return id;
  }
  function union(a, b) {
    const rootA = find(a);
    const rootB = find(b);
    if (rootA !== rootB) parent.set(rootA, rootB);
  }
  return { find, union };
}

// True node-mesh graph: an edge between any two courts <=100m apart, a
// club = one connected component. Pairwise O(n^2) distance checks -- same
// cost class as the previous centroid-growing loop, fine at this dataset's
// scale (a few thousand rows per re-run).
function clusterCourts(courts) {
  const ids = courts.map((c) => c.id);
  const { find, union } = makeUnionFind(ids);

  for (let i = 0; i < courts.length; i += 1) {
    for (let j = i + 1; j < courts.length; j += 1) {
      if (haversineKm(courts[i].latitude, courts[i].longitude, courts[j].latitude, courts[j].longitude) <= CLUSTER_RADIUS_KM) {
        union(courts[i].id, courts[j].id);
      }
    }
  }

  const byRoot = new Map();
  for (const court of courts) {
    const root = find(court.id);
    if (!byRoot.has(root)) byRoot.set(root, []);
    byRoot.get(root).push(court);
  }
  return [...byRoot.values()].filter((c) => c.length >= 2);
}

function centroid(cluster) {
  return {
    lat: cluster.reduce((s, c) => s + c.latitude, 0) / cluster.length,
    lng: cluster.reduce((s, c) => s + c.longitude, 0) / cluster.length,
  };
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

async function reconcile(cluster) {
  const { lat, lng } = centroid(cluster);
  const derivedName = deriveName(cluster);
  const courtIds = cluster.map((c) => c.id);

  // Reuse an existing club if any of this cluster's courts already belong
  // to one -- keeps club_id (and therefore club_watches) stable across
  // re-runs instead of creating a duplicate club every time.
  const placeholders = courtIds.map(() => '?').join(',');
  const existing = db.prepare(
    `SELECT DISTINCT club_id FROM club_courts WHERE court_id IN (${placeholders})`
  ).all(...courtIds);

  let clubId;
  let finalName = derivedName;
  if (existing.length > 0) {
    // A re-cluster can MERGE two previously-distinct clubs into one (e.g. a
    // newly-seeded court bridges them into a single connected component) --
    // `existing` then has more than one row. Survivor = the oldest club id
    // (a stable, deterministic pick, not whatever order SQLite happened to
    // return) rather than the old `existing[0].club_id`, which picked
    // arbitrarily and then let deleteOrphanedClubs() below silently delete
    // every OTHER matched club (now orphaned, since every one of its courts
    // just got reassigned to clubId via the ON CONFLICT below) along with
    // its club_watches rows -- unsubscribing real users from a venue that,
    // from their point of view, still very much exists (it just merged into
    // the survivor). Migrate their watches onto the survivor instead.
    const clubIds = existing.map((e) => e.club_id);
    clubId = Math.min(...clubIds);
    const losingClubIds = clubIds.filter((id) => id !== clubId);
    if (losingClubIds.length > 0) {
      const losingPlaceholders = losingClubIds.map(() => '?').join(',');
      const watchers = db.prepare(
        `SELECT user_id FROM club_watches WHERE club_id IN (${losingPlaceholders})`
      ).all(...losingClubIds);
      // INSERT OR IGNORE -- a user already watching both the losing club
      // and the survivor would otherwise hit club_watches' UNIQUE(user_id,
      // club_id) constraint.
      const insertWatch = db.prepare('INSERT OR IGNORE INTO club_watches (user_id, club_id) VALUES (?, ?)');
      for (const { user_id: watcherId } of watchers) insertWatch.run(watcherId, clubId);
    }
    const club = db.prepare('SELECT name, name_source, postcode FROM clubs WHERE id = ?').get(clubId);
    // Once a crowd-submitted name exists (routes/courts.js's POST
    // /clubs/:id/name -- even before it reaches CONFIRMATION_THRESHOLD
    // confirmations), this script's own guess must stop overwriting it on
    // every future re-run. See db.js's clubs.name_source comment.
    if (club.name_source === 'derived') {
      db.prepare('UPDATE clubs SET name = ?, latitude = ?, longitude = ? WHERE id = ?')
        .run(derivedName, lat, lng, clubId);
    } else {
      db.prepare('UPDATE clubs SET latitude = ?, longitude = ? WHERE id = ?').run(lat, lng, clubId);
      finalName = club.name;
    }
    // Only looked up once per club (skipped once postcode is already set) --
    // this script re-runs over the same clubs repeatedly as new courts get
    // seeded nearby, and re-querying postcodes.io for a club whose centroid
    // barely moved would be pure waste.
    if (!club.postcode) {
      const postcode = await lookupPostcode(lat, lng);
      if (postcode) db.prepare('UPDATE clubs SET postcode = ? WHERE id = ?').run(postcode, clubId);
    }
  } else {
    const postcode = await lookupPostcode(lat, lng);
    const info = db.prepare('INSERT INTO clubs (name, latitude, longitude, postcode) VALUES (?, ?, ?, ?)')
      .run(derivedName, lat, lng, postcode);
    clubId = info.lastInsertRowid;
  }

  for (const courtId of courtIds) {
    db.prepare('INSERT INTO club_courts (club_id, court_id) VALUES (?, ?) ON CONFLICT(court_id) DO UPDATE SET club_id = excluded.club_id')
      .run(clubId, courtId);
  }
  return { clubId, name: finalName, courtCount: courtIds.length };
}

// A stricter clustering radius (or any re-run against changed court data)
// can leave an existing club with zero courts still pointing at it in
// club_courts -- e.g. every court that used to justify it moved to a
// different club_id via reconcile()'s ON CONFLICT above. An orphaned club
// like that isn't just dead data: its club_watches rows keep silently
// watching a venue that, as far as club_courts is concerned, no longer
// exists, so those users would never be notified again. Delete it and its
// watches together -- same ordering as every other cleanup in this app
// (children before the parent row), mirrored from auth.js's account-deletion
// cleanup.
function deleteOrphanedClubs() {
  const orphaned = db.prepare(`
    SELECT id FROM clubs WHERE id NOT IN (SELECT DISTINCT club_id FROM club_courts)
  `).all();
  for (const { id: clubId } of orphaned) {
    db.prepare('DELETE FROM club_watches WHERE club_id = ?').run(clubId);
    db.prepare('DELETE FROM clubs WHERE id = ?').run(clubId);
  }
  return orphaned.length;
}

async function main() {
  const courts = db.prepare('SELECT id, name, latitude, longitude FROM courts').all();
  const clusters = clusterCourts(courts);

  console.log(`${courts.length} courts, ${clusters.length} clusters of 2+ found`);
  // Sequential, not Promise.all -- each reconcile() may call postcodes.io,
  // and there's no reason to fire dozens of concurrent requests at a free
  // third-party API for what's already an offline, non-time-critical script.
  for (const cluster of clusters) {
    const { clubId, name, courtCount } = await reconcile(cluster);
    console.log(`  club ${clubId}: "${name}" (${courtCount} courts)`);
  }

  const removed = deleteOrphanedClubs();
  if (removed > 0) console.log(`Removed ${removed} club(s) left with no courts after this re-cluster`);
}

// Only run when invoked directly (`node scripts/clusterCourts.js`), not when
// require()'d by a test -- otherwise clusterCourts.test.js would hit the
// real DB the instant it imports this module's other exports.
if (require.main === module) {
  main().catch((err) => {
    console.error('clusterCourts failed:', err.message);
    process.exit(1);
  });
}

module.exports = { clusterCourts, deriveName, reconcile, deleteOrphanedClubs, CLUSTER_RADIUS_KM };
