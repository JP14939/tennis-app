// clusterCourts.js used to run main() unconditionally at module load (a
// bare call at the bottom of the file), so it couldn't be require()'d by a
// test without immediately hitting the real DB. Guarded behind
// `require.main === module` so these exports are testable in isolation
// against an in-memory DB instead.
process.env.DB_PATH = ':memory:';

const db = require('../src/db');

// reconcile() does a best-effort postcode lookup (utils/postcodeLookup.js --
// a real network call to postcodes.io) for any club without one yet.
// Mocked so these tests don't depend on network access.
jest.mock('../src/utils/postcodeLookup');
const { lookupPostcode } = require('../src/utils/postcodeLookup');

const { clusterCourts, reconcile, deleteOrphanedClubs } = require('./clusterCourts');

function makeCourt(name, latitude, longitude) {
  return db.prepare('INSERT INTO courts (name, latitude, longitude, source) VALUES (?, ?, ?, \'osm\')')
    .run(name, latitude, longitude).lastInsertRowid;
}

// ~0.0009 degrees of latitude is ~100m -- used throughout to place courts a
// known real-world distance apart without relying on a second haversine
// implementation in the test itself.
const DEG_PER_90M = 0.0009 * 0.9;
const DEG_PER_150M = 0.0009 * 1.5;

beforeEach(() => lookupPostcode.mockReset().mockResolvedValue(null));

describe('clusterCourts', () => {
  test('a mesh chain clusters as one club even though the ends are far apart', () => {
    // 4 courts, each ~90m from the next (well under the 100m edge
    // threshold), forming one straight line. The two ends are ~270m apart --
    // this is the exact behavior confirmed with the product owner: a mesh
    // of near neighbours is one club, regardless of the cluster's overall
    // span.
    const courts = [0, 1, 2, 3].map((i) => ({
      id: i + 1, name: 'Tennis Court', latitude: 51.5 + i * DEG_PER_90M, longitude: -0.12,
    }));

    const clusters = clusterCourts(courts);

    expect(clusters).toHaveLength(1);
    expect(clusters[0].map((c) => c.id).sort()).toEqual([1, 2, 3, 4]);
  });

  test('two courts 150m apart do not cluster', () => {
    const courts = [
      { id: 1, name: 'Court A', latitude: 51.5, longitude: -0.12 },
      { id: 2, name: 'Court B', latitude: 51.5 + DEG_PER_150M, longitude: -0.12 },
    ];

    expect(clusterCourts(courts)).toHaveLength(0);
  });

  test('a single standalone court never forms a cluster of its own', () => {
    const courts = [{ id: 1, name: 'Lone Court', latitude: 51.5, longitude: -0.12 }];
    expect(clusterCourts(courts)).toHaveLength(0);
  });
});

describe('reconcile', () => {
  test('preserves an existing club_id (and its watches) across a re-run', async () => {
    const courtA = makeCourt('Court A', 51.5, -0.12);
    const courtB = makeCourt('Court B', 51.5 + DEG_PER_90M, -0.12);
    const user = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
      .run('a@test.com', 'x', 'A').lastInsertRowid;

    const first = await reconcile([
      { id: courtA, name: 'Court A', latitude: 51.5, longitude: -0.12 },
      { id: courtB, name: 'Court B', latitude: 51.5 + DEG_PER_90M, longitude: -0.12 },
    ]);
    db.prepare('INSERT INTO club_watches (user_id, club_id) VALUES (?, ?)').run(user, first.clubId);

    // Re-run against the same two courts (simulating clusterCourts.js being
    // run again later, e.g. after new courts were seeded elsewhere).
    const second = await reconcile([
      { id: courtA, name: 'Court A', latitude: 51.5, longitude: -0.12 },
      { id: courtB, name: 'Court B', latitude: 51.5 + DEG_PER_90M, longitude: -0.12 },
    ]);

    expect(second.clubId).toBe(first.clubId);
    const watchStillThere = db.prepare('SELECT 1 FROM club_watches WHERE user_id = ? AND club_id = ?')
      .get(user, first.clubId);
    expect(watchStillThere).toBeTruthy();
  });

  test('looks up a postcode for a newly created club', async () => {
    lookupPostcode.mockResolvedValue('SW1A 1AA');
    const courtA = makeCourt('Court A', 51.5, -0.12);

    const { clubId } = await reconcile([{ id: courtA, name: 'Court A', latitude: 51.5, longitude: -0.12 }]);

    expect(db.prepare('SELECT postcode FROM clubs WHERE id = ?').get(clubId).postcode).toBe('SW1A 1AA');
  });

  test('does not re-look-up a postcode a club already has', async () => {
    const courtA = makeCourt('Court A', 51.5, -0.12);
    const courtB = makeCourt('Court B', 51.5 + DEG_PER_90M, -0.12);
    lookupPostcode.mockResolvedValue('SW1A 1AA');
    const first = await reconcile([{ id: courtA, name: 'Court A', latitude: 51.5, longitude: -0.12 }]);
    expect(lookupPostcode).toHaveBeenCalledTimes(1);

    // Re-run with an extra court joining the same club -- the club already
    // has a postcode from the first run, so this shouldn't call out again.
    await reconcile([
      { id: courtA, name: 'Court A', latitude: 51.5, longitude: -0.12 },
      { id: courtB, name: 'Court B', latitude: 51.5 + DEG_PER_90M, longitude: -0.12 },
    ]);

    expect(lookupPostcode).toHaveBeenCalledTimes(1);
    expect(db.prepare('SELECT postcode FROM clubs WHERE id = ?').get(first.clubId).postcode).toBe('SW1A 1AA');
  });

  test('merging two previously-distinct clubs migrates the losing club\'s watches onto the survivor', async () => {
    // Two courts far enough apart to start as separate clubs (each with its
    // own second court to actually form a club, since clusterCourts()
    // requires 2+ courts).
    const courtA1 = makeCourt('Club A Court 1', 51.5, -0.12);
    const courtA2 = makeCourt('Club A Court 2', 51.5 + DEG_PER_90M, -0.12);
    const courtB1 = makeCourt('Club B Court 1', 51.6, -0.12);
    const courtB2 = makeCourt('Club B Court 2', 51.6 + DEG_PER_90M, -0.12);

    const clubA = await reconcile([
      { id: courtA1, name: 'Club A Court 1', latitude: 51.5, longitude: -0.12 },
      { id: courtA2, name: 'Club A Court 2', latitude: 51.5 + DEG_PER_90M, longitude: -0.12 },
    ]);
    const clubB = await reconcile([
      { id: courtB1, name: 'Club B Court 1', latitude: 51.6, longitude: -0.12 },
      { id: courtB2, name: 'Club B Court 2', latitude: 51.6 + DEG_PER_90M, longitude: -0.12 },
    ]);
    expect(clubA.clubId).not.toBe(clubB.clubId);

    const watcherA = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
      .run('watcherA@test.com', 'x', 'Watcher A').lastInsertRowid;
    const watcherB = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
      .run('watcherB@test.com', 'x', 'Watcher B').lastInsertRowid;
    db.prepare('INSERT INTO club_watches (user_id, club_id) VALUES (?, ?)').run(watcherA, clubA.clubId);
    db.prepare('INSERT INTO club_watches (user_id, club_id) VALUES (?, ?)').run(watcherB, clubB.clubId);

    // Simulates a newly-seeded court bridging the two into one connected
    // component -- reconcile() is called with all 4 original courts as one
    // cluster, the same shape clusterCourts() itself would produce.
    const merged = await reconcile([
      { id: courtA1, name: 'Club A Court 1', latitude: 51.5, longitude: -0.12 },
      { id: courtA2, name: 'Club A Court 2', latitude: 51.5 + DEG_PER_90M, longitude: -0.12 },
      { id: courtB1, name: 'Club B Court 1', latitude: 51.6, longitude: -0.12 },
      { id: courtB2, name: 'Club B Court 2', latitude: 51.6 + DEG_PER_90M, longitude: -0.12 },
    ]);
    const survivorId = Math.min(clubA.clubId, clubB.clubId);
    const loserId = Math.max(clubA.clubId, clubB.clubId);
    expect(merged.clubId).toBe(survivorId);

    deleteOrphanedClubs(); // the losing club now has zero courts in club_courts

    // Both original watchers must still be watching something real --
    // neither watch silently vanished with the merge.
    expect(db.prepare('SELECT 1 FROM club_watches WHERE user_id = ? AND club_id = ?').get(watcherA, survivorId)).toBeTruthy();
    expect(db.prepare('SELECT 1 FROM club_watches WHERE user_id = ? AND club_id = ?').get(watcherB, survivorId)).toBeTruthy();
    expect(db.prepare('SELECT 1 FROM club_watches WHERE club_id = ?').get(loserId)).toBeUndefined();
  });

  test('a derived name is overwritten on re-run, but a user-proposed name is left alone', async () => {
    const courtA = makeCourt('Court A', 51.5, -0.12);
    const courtB = makeCourt('Court B', 51.5 + DEG_PER_90M, -0.12);
    const cluster = [
      { id: courtA, name: 'Court A', latitude: 51.5, longitude: -0.12 },
      { id: courtB, name: 'Court B', latitude: 51.5 + DEG_PER_90M, longitude: -0.12 },
    ];

    const first = await reconcile(cluster);
    // Simulates routes/courts.js's POST /clubs/:id/name having been called --
    // a real user proposed a name, which flips name_source to 'user'.
    db.prepare("UPDATE clubs SET name = 'Riverside Tennis Club', name_source = 'user' WHERE id = ?")
      .run(first.clubId);

    const second = await reconcile(cluster);

    expect(second.name).toBe('Riverside Tennis Club');
    expect(db.prepare('SELECT name FROM clubs WHERE id = ?').get(first.clubId).name).toBe('Riverside Tennis Club');
  });
});

describe('deleteOrphanedClubs', () => {
  test('removes a club with no courts left in club_courts, and its watches', async () => {
    // Simulates the real scenario a stricter re-cluster can produce: every
    // court that used to justify this club moved to a different club_id via
    // reconcile()'s ON CONFLICT(court_id), leaving this clubs row with zero
    // matching club_courts rows. Constructed directly here rather than via
    // two reconcile() calls, since reconcile() itself always reuses an
    // existing club_id when a cluster still contains any of that club's
    // courts -- the orphaning only happens once NONE of a club's original
    // courts are in the new cluster at all, which is what this sets up.
    const orphanClub = db.prepare('INSERT INTO clubs (name, latitude, longitude) VALUES (?, ?, ?)')
      .run('Old Club', 51.5, -0.12).lastInsertRowid;
    const user = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
      .run('b@test.com', 'x', 'B').lastInsertRowid;
    db.prepare('INSERT INTO club_watches (user_id, club_id) VALUES (?, ?)').run(user, orphanClub);

    // A different, healthy club that still has a court -- proves the
    // cleanup is targeted, not a blanket wipe.
    const courtA = makeCourt('Court A', 51.5, -0.12);
    const healthy = await reconcile([{ id: courtA, name: 'Court A', latitude: 51.5, longitude: -0.12 }]);

    const removed = deleteOrphanedClubs();

    expect(removed).toBe(1);
    expect(db.prepare('SELECT 1 FROM clubs WHERE id = ?').get(orphanClub)).toBeUndefined();
    expect(db.prepare('SELECT 1 FROM club_watches WHERE club_id = ?').get(orphanClub)).toBeUndefined();
    expect(db.prepare('SELECT 1 FROM clubs WHERE id = ?').get(healthy.clubId)).toBeTruthy();
  });

  test('does nothing when every club still has courts', async () => {
    const courtA = makeCourt('Court A', 51.5, -0.12);
    const courtB = makeCourt('Court B', 51.5 + DEG_PER_90M, -0.12);
    await reconcile([
      { id: courtA, name: 'Court A', latitude: 51.5, longitude: -0.12 },
      { id: courtB, name: 'Court B', latitude: 51.5 + DEG_PER_90M, longitude: -0.12 },
    ]);

    expect(deleteOrphanedClubs()).toBe(0);
  });
});
