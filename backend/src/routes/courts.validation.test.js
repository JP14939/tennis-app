// courts is a SHARED table (~33k rows in production) that every user's map
// reads, and availability posts are broadcast by push notification to every
// watcher -- so bad input here is not confined to the account that sent it.

process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const request = require('supertest');
const { appWith, makeUser, expectRejected, db } = require('./testSupport');

const app = appWith(require('./courts'));

function addCourt(token, body) {
  return request(app).post('/api/courts').set('Authorization', `Bearer ${token}`).send(body);
}

function seedCourt() {
  return db.prepare(
    "INSERT INTO courts (name, latitude, longitude, source) VALUES ('Seeded', 51.5, -0.12, 'osm')"
  ).run().lastInsertRowid;
}

const validCourt = { name: 'Victoria Park Courts', latitude: 51.5362, longitude: -0.0398 };

describe('POST /courts — coordinates', () => {
  test.each([
    ['the extremes of both ranges', { latitude: 90, longitude: 180 }],
    ['the opposite extremes', { latitude: -90, longitude: -180 }],
    ['null island', { latitude: 0, longitude: 0 }],
  ])('accepts %s', async (_label, coords) => {
    const { token } = makeUser();
    const res = await addCourt(token, { ...validCourt, ...coords });
    expect(res.status).toBe(201);
  });

  test.each([
    ['a latitude past the pole', { latitude: 90.0001 }],
    ['a wildly out-of-range latitude', { latitude: 5000 }],
    ['a longitude past the antimeridian', { longitude: 180.0001 }],
    ['a longitude in degrees-times-two', { longitude: 360 }],
    ['a stringified coordinate', { latitude: '51.5' }],
    ['a missing coordinate', { longitude: undefined }],
    ['NaN', { latitude: Number.NaN }],
  ])('rejects %s and adds no court', async (_label, coords) => {
    const { token } = makeUser();
    await expectRejected(() => addCourt(token, { ...validCourt, ...coords }), 'courts');
  });
});

describe('GET /courts — coordinates', () => {
  function get(token, query) {
    return request(app).get('/api/courts').query(query).set('Authorization', `Bearer ${token}`);
  }

  test('accepts valid coordinates near a seeded court', async () => {
    const { token } = makeUser();
    seedCourt();
    const res = await get(token, { lat: 51.5, lng: -0.12 });
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body.courts)).toBe(true);
  });

  // Unlike POST /courts, this route used to only check for NaN -- an
  // out-of-range value fed straight into the bounding-box arithmetic and,
  // on a cache miss, into a live Overpass API call with a nonsensical box.
  test.each([
    ['a latitude past the pole', { lat: 5000, lng: 0 }],
    ['a longitude past the antimeridian', { lat: 0, lng: 400 }],
    ['both wildly out of range', { lat: -9999, lng: 9999 }],
  ])('rejects %s with a 400, not a lookup', async (_label, coords) => {
    const { token } = makeUser();
    const res = await get(token, coords);
    expect(res.status).toBe(400);
  });
});

describe('POST /courts — name', () => {
  test.each([
    ['', 'empty'],
    ['   ', 'whitespace only'],
    ['x'.repeat(121), 'over the length cap'],
    [{ nested: 'object' }, 'not a string'],
  ])('rejects %p (%s)', async (name) => {
    const { token } = makeUser();
    await expectRejected(() => addCourt(token, { ...validCourt, name }), 'courts');
  });

  test('stores the name trimmed', async () => {
    const { token } = makeUser();
    const res = await addCourt(token, { ...validCourt, name: '  Riverside  ' });
    expect(res.status).toBe(201);
    expect(res.body.court.name).toBe('Riverside');
  });
});

describe('POST /courts/:id/availability', () => {
  function post(token, courtId, body) {
    return request(app).post(`/api/courts/${courtId}/availability`)
      .set('Authorization', `Bearer ${token}`).send(body);
  }

  test('accepts a well-formed window', async () => {
    const { token } = makeUser();
    const res = await post(token, seedCourt(), {
      start_time: '2026-08-22T10:00:00Z',
      end_time: '2026-08-22T12:00:00Z',
      note: 'Doubles, all welcome',
    });
    expect(res.status).toBe(201);
  });

  test('accepts an open-ended post with no end time', async () => {
    const { token } = makeUser();
    const res = await post(token, seedCourt(), { start_time: '2026-08-22T10:00:00Z' });
    expect(res.status).toBe(201);
  });

  test.each([
    ['tomorrow afternoon', 'an unparseable date — it is both a sort key and a rendered date'],
    ['', 'empty'],
    [undefined, 'missing'],
    ['3000-01-01', 'implausibly far in the future, which would sort to the top forever'],
  ])('rejects the start_time %p (%s)', async (start_time) => {
    const { token } = makeUser();
    const courtId = seedCourt();
    await expectRejected(() => post(token, courtId, { start_time }), 'availability_posts');
  });

  test('rejects a session that ends before it starts', async () => {
    const { token } = makeUser();
    const courtId = seedCourt();
    await expectRejected(
      () => post(token, courtId, { start_time: '2026-08-22T12:00:00Z', end_time: '2026-08-22T10:00:00Z' }),
      'availability_posts',
    );
  });

  test('rejects a session that ends exactly when it starts', async () => {
    const { token } = makeUser();
    const courtId = seedCourt();
    await expectRejected(
      () => post(token, courtId, { start_time: '2026-08-22T10:00:00Z', end_time: '2026-08-22T10:00:00Z' }),
      'availability_posts',
    );
  });

  test('rejects an over-long note', async () => {
    const { token } = makeUser();
    const courtId = seedCourt();
    await expectRejected(
      () => post(token, courtId, { start_time: '2026-08-22T10:00:00Z', note: 'x'.repeat(301) }),
      'availability_posts',
    );
  });
});

describe('PATCH /courts/:id/cost', () => {
  function patchCost(token, courtId, body) {
    return request(app).patch(`/api/courts/${courtId}/cost`)
      .set('Authorization', `Bearer ${token}`).send(body);
  }

  test('accepts a normal price note, and clearing it', async () => {
    const { token } = makeUser();
    const courtId = seedCourt();

    expect((await patchCost(token, courtId, { cost_info: '£8/hour' })).status).toBe(200);
    expect((await patchCost(token, courtId, { cost_info: null })).status).toBe(200);
    expect(db.prepare('SELECT cost_info FROM courts WHERE id = ?').get(courtId).cost_info).toBeNull();
  });

  test.each([
    [{ nested: 'object' }, 'not a string — this used to throw inside better-sqlite3 as a 500'],
    ['x'.repeat(501), 'over the length cap'],
  ])('rejects %p (%s) without touching the court', async (cost_info) => {
    const { token } = makeUser();
    const courtId = seedCourt();

    const res = await patchCost(token, courtId, { cost_info });
    expect(res.status).toBe(400);
    expect(db.prepare('SELECT cost_info FROM courts WHERE id = ?').get(courtId).cost_info).toBeNull();
  });
});
