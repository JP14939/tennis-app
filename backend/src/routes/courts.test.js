// Regression tests for two GET /courts bugs found in this sweep:
//
// 1. (severe, unconditional) queryNearbyCourts()'s WHERE clause referenced
//    `latitude`/`longitude` unqualified after LEFT JOINing `clubs` -- which
//    also has latitude/longitude columns -- so SQLite rejected every single
//    query with "ambiguous column name: latitude", regardless of radiusKm.
//    GET /courts 500'd on every call. Fixed by qualifying both columns as
//    c.latitude/c.longitude (the courts table, which is what's meant to be
//    filtered by proximity).
// 2. a radiusKm <= 0 (e.g. negative) made latDelta/lngDelta negative,
//    producing an inverted `BETWEEN low AND high` clause that always matched
//    zero rows -- courts silently came back empty regardless of what was
//    actually in the DB nearby, and (since the empty result always
//    re-triggers the Overpass self-heal seed) it re-hit the external
//    Overpass API on every single request for that lat/lng instead of
//    caching normally.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const courtsRouter = require('./courts');

const app = express();
app.use(express.json());
app.use('/api', courtsRouter);

function makeUser(email) {
  const id = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(email, 'x', 'Test User').lastInsertRowid;
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

describe('GET /courts', () => {
  test('a plain valid request succeeds instead of 500ing on "ambiguous column name: latitude"', async () => {
    const { token } = makeUser('courts0@test.com');
    db.prepare(`INSERT INTO courts (name, latitude, longitude, source) VALUES (?, ?, ?, 'osm')`)
      .run('Plain Court', 40.71, -74.0);

    const res = await request(app)
      .get('/api/courts')
      .query({ lat: 40.7, lng: -74.0, radiusKm: 20 })
      .set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.courts.some((c) => c.name === 'Plain Court')).toBe(true);
  });

  test('a negative radiusKm falls back to the default radius instead of always returning empty', async () => {
    const { token } = makeUser('courts1@test.com');
    // A court 1km from the query point -- well within DEFAULT_RADIUS_KM (20km).
    db.prepare(`INSERT INTO courts (name, latitude, longitude, source) VALUES (?, ?, ?, 'osm')`)
      .run('Test Court', 40.71, -74.0);

    const res = await request(app)
      .get('/api/courts')
      .query({ lat: 40.7, lng: -74.0, radiusKm: -5 })
      .set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.courts.some((c) => c.name === 'Test Court')).toBe(true);
  });

  test('a radiusKm of 0 also falls back to the default radius', async () => {
    const { token } = makeUser('courts2@test.com');
    db.prepare(`INSERT INTO courts (name, latitude, longitude, source) VALUES (?, ?, ?, 'osm')`)
      .run('Zero Radius Court', 51.51, -0.11);

    const res = await request(app)
      .get('/api/courts')
      .query({ lat: 51.5, lng: -0.1, radiusKm: 0 })
      .set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.courts.some((c) => c.name === 'Zero Radius Court')).toBe(true);
  });

  // A genuinely court-less area (no rows in the DB nearby, and Overpass also
  // has nothing) always looks like "never queried before" to the self-heal
  // check, so without a negative cache every single request for that area
  // re-hits the live Overpass API -- risking rate-limiting/a ban on this
  // backend's shared IP, which would degrade court search for every user.
  describe('repeated empty results for a court-less area', () => {
    const originalFetch = global.fetch;

    beforeEach(() => {
      global.fetch = jest.fn(async () => ({ ok: true, json: async () => ({ elements: [] }) }));
    });

    afterEach(() => {
      global.fetch = originalFetch;
    });

    test('only calls Overpass once across repeated queries for the same area', async () => {
      const { token } = makeUser('courts3@test.com');
      // Middle of the ocean -- guaranteed no courts in the seeded test DB.
      const query = { lat: 0.0001, lng: 0.0002, radiusKm: 5 };

      const first = await request(app).get('/api/courts').query(query).set('Authorization', `Bearer ${token}`);
      const second = await request(app).get('/api/courts').query(query).set('Authorization', `Bearer ${token}`);

      expect(first.status).toBe(200);
      expect(second.status).toBe(200);
      expect(first.body.courts).toEqual([]);
      expect(second.body.courts).toEqual([]);
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    // Regression test: wasRecentlySeededEmpty() used to only ever READ an
    // entry's staleness, never remove it -- the fix prunes on read (and via a
    // periodic sweep). This confirms that pruning doesn't break the TTL
    // itself: once an entry is old enough, the area is treated as
    // never-seeded again and Overpass is re-queried.
    test('re-queries Overpass once the negative-cache TTL has expired', async () => {
      const { token } = makeUser('courts3b@test.com');
      const query = { lat: 10.0001, lng: 10.0002, radiusKm: 5 };

      const nowSpy = jest.spyOn(Date, 'now');
      nowSpy.mockReturnValue(1_000_000);
      const first = await request(app).get('/api/courts').query(query).set('Authorization', `Bearer ${token}`);
      expect(first.status).toBe(200);
      expect(global.fetch).toHaveBeenCalledTimes(1);

      // Still within the TTL -- no second Overpass call.
      nowSpy.mockReturnValue(1_000_000 + 60 * 60 * 1000 - 1);
      await request(app).get('/api/courts').query(query).set('Authorization', `Bearer ${token}`);
      expect(global.fetch).toHaveBeenCalledTimes(1);

      // Past the TTL -- treated as never-seeded again.
      nowSpy.mockReturnValue(1_000_000 + 60 * 60 * 1000 + 1);
      const third = await request(app).get('/api/courts').query(query).set('Authorization', `Bearer ${token}`);
      expect(third.status).toBe(200);
      expect(global.fetch).toHaveBeenCalledTimes(2);

      nowSpy.mockRestore();
    });
  });

  // Regression test: two concurrent requests for the same never-before-seen
  // area each saw zero local courts and no negative-cache entry yet (neither
  // had finished seeding), so each independently kicked off its own live
  // Overpass call for the same area instead of sharing one in-flight request.
  test('concurrent requests for the same brand-new area only trigger one Overpass call', async () => {
    const { token } = makeUser('courts4@test.com');
    const originalFetch = global.fetch;
    let resolveFetch;
    const fetchPromise = new Promise((resolve) => { resolveFetch = resolve; });
    global.fetch = jest.fn(() => fetchPromise.then(() => ({ ok: true, json: async () => ({ elements: [] }) })));

    try {
      const query = { lat: 20.0001, lng: 20.0002, radiusKm: 5 };
      const first = request(app).get('/api/courts').query(query).set('Authorization', `Bearer ${token}`);
      const second = request(app).get('/api/courts').query(query).set('Authorization', `Bearer ${token}`);

      // Let both requests reach the seed call before letting Overpass "respond".
      await new Promise((resolve) => setTimeout(resolve, 20));
      resolveFetch();

      const [resA, resB] = await Promise.all([first, second]);
      expect(resA.status).toBe(200);
      expect(resB.status).toBe(200);
      expect(global.fetch).toHaveBeenCalledTimes(1);
    } finally {
      global.fetch = originalFetch;
    }
  });

  // Regression test: radiusKm had a `> 0` floor but no ceiling, so a caller
  // could force an arbitrarily large (continent-scale) bounding box into the
  // query and into a live Overpass call.
  test('an excessive radiusKm is capped instead of matching courts far outside any sane search radius', async () => {
    const { token } = makeUser('courts5@test.com');
    // ~150km from the query point -- well outside the 100km cap, but well
    // within the naive 1,000,000km radius requested below.
    db.prepare(`INSERT INTO courts (name, latitude, longitude, source) VALUES (?, ?, ?, 'osm')`)
      .run('Far Away Court', 41.35, -74.0);

    const res = await request(app)
      .get('/api/courts')
      .query({ lat: 40.0, lng: -74.0, radiusKm: 1000000 })
      .set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.courts.some((c) => c.name === 'Far Away Court')).toBe(false);
  });
});
