// courts is a SHARED table (~33k rows in production) that every user's map
// reads, and availability posts are broadcast by push notification to every
// watcher -- so bad input here is not confined to the account that sent it.

process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const request = require('supertest');
const { appWith, makeUser, expectRejected, db } = require('./testSupport');

// POST /courts and POST /courts/area-watch both do a best-effort postcode
// lookup (utils/postcodeLookup.js -- a real network call to postcodes.io)
// before writing. Mocked here so these tests don't depend on network access
// and don't bind `undefined` into better-sqlite3 (a jest auto-mock's default
// return value, which better-sqlite3 rejects as a param -- unlike the real
// function's own null-on-failure contract).
jest.mock('../utils/postcodeLookup');
require('../utils/postcodeLookup').lookupPostcode.mockResolvedValue(null);

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

describe('POST /courts — postcode lookup', () => {
  afterEach(() => require('../utils/postcodeLookup').lookupPostcode.mockReset().mockResolvedValue(null));

  test('stores the resolved postcode on the new court', async () => {
    require('../utils/postcodeLookup').lookupPostcode.mockResolvedValue('SW1A 1AA');
    const { token } = makeUser();
    const res = await addCourt(token, validCourt);
    expect(res.status).toBe(201);
    expect(res.body.court.postcode).toBe('SW1A 1AA');
  });

  test('a failed lookup leaves postcode null instead of failing the whole write', async () => {
    require('../utils/postcodeLookup').lookupPostcode.mockResolvedValue(null);
    const { token } = makeUser();
    const res = await addCourt(token, validCourt);
    expect(res.status).toBe(201);
    expect(res.body.court.postcode).toBeNull();
  });
});

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

describe('POST /courts/area-watch', () => {
  function postAreaWatch(token, body) {
    return request(app).post('/api/courts/area-watch').set('Authorization', `Bearer ${token}`).send(body);
  }

  const validArea = { name: 'Near work', latitude: 51.5, longitude: -0.12, radius_km: 5 };

  test('accepts a valid area and returns it', async () => {
    const { token } = makeUser();
    const res = await postAreaWatch(token, validArea);
    expect(res.status).toBe(201);
    expect(res.body.area).toMatchObject({ name: 'Near work', latitude: 51.5, longitude: -0.12, radius_km: 5 });
  });

  test('stores the resolved postcode on the new area watch', async () => {
    require('../utils/postcodeLookup').lookupPostcode.mockResolvedValueOnce('SW1A 1AA');
    const { token } = makeUser();
    const res = await postAreaWatch(token, validArea);
    expect(res.status).toBe(201);
    expect(res.body.area.postcode).toBe('SW1A 1AA');
  });

  test('accepts an area with no name', async () => {
    const { token } = makeUser();
    const { name, ...withoutName } = validArea;
    const res = await postAreaWatch(token, withoutName);
    expect(res.status).toBe(201);
    expect(res.body.area.name).toBeNull();
  });

  test.each([
    ['a wildly out-of-range latitude', { latitude: 5000 }],
    ['a longitude past the antimeridian', { longitude: 180.0001 }],
    ['a zero radius', { radius_km: 0 }],
    ['a negative radius', { radius_km: -5 }],
    ['a radius far bigger than a real area watch', { radius_km: 500 }],
    ['a stringified radius', { radius_km: '5' }],
    ['a name over the length cap', { name: 'x'.repeat(81) }],
  ])('rejects %s and adds no area watch', async (_label, overrides) => {
    const { token } = makeUser();
    await expectRejected(() => postAreaWatch(token, { ...validArea, ...overrides }), 'area_watches');
  });
});

describe('DELETE /courts/club-watch/:clubId', () => {
  test('unwatches a club by id directly, without needing a court id', async () => {
    const { token, id: userId } = makeUser();
    const clubId = db.prepare("INSERT INTO clubs (name, latitude, longitude) VALUES ('Club', 51.5, -0.12)")
      .run().lastInsertRowid;
    db.prepare('INSERT INTO club_watches (user_id, club_id) VALUES (?, ?)').run(userId, clubId);

    const res = await request(app)
      .delete(`/api/courts/club-watch/${clubId}`)
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(204);
    expect(db.prepare('SELECT 1 FROM club_watches WHERE user_id = ? AND club_id = ?').get(userId, clubId)).toBeUndefined();
  });

  test('only unwatches the requesting user\'s own club watch', async () => {
    const owner = makeUser();
    const other = makeUser();
    const clubId = db.prepare("INSERT INTO clubs (name, latitude, longitude) VALUES ('Club', 51.5, -0.12)")
      .run().lastInsertRowid;
    db.prepare('INSERT INTO club_watches (user_id, club_id) VALUES (?, ?)').run(owner.id, clubId);

    const res = await request(app)
      .delete(`/api/courts/club-watch/${clubId}`)
      .set('Authorization', `Bearer ${other.token}`);
    expect(res.status).toBe(204);
    expect(db.prepare('SELECT 1 FROM club_watches WHERE user_id = ? AND club_id = ?').get(owner.id, clubId)).toBeTruthy();
  });
});

function makeClub(overrides = {}) {
  const { name = 'Old Name', latitude = 51.5, longitude = -0.12 } = overrides;
  return db.prepare('INSERT INTO clubs (name, latitude, longitude) VALUES (?, ?, ?)')
    .run(name, latitude, longitude).lastInsertRowid;
}

describe('POST /clubs/:id/name', () => {
  test('proposing a new name updates it, sets name_source to user, and resets verification', async () => {
    const { token, id: userId } = makeUser();
    const clubId = makeClub();

    const res = await request(app)
      .post(`/api/clubs/${clubId}/name`)
      .set('Authorization', `Bearer ${token}`)
      .send({ name: 'Riverside Tennis Club' });

    expect(res.status).toBe(200);
    expect(res.body.club).toMatchObject({
      name: 'Riverside Tennis Club', name_source: 'user', name_submitted_by: userId, name_verified: 0,
    });
  });

  test('a new proposal clears any confirmations the previous name had', async () => {
    const { token: proposerToken } = makeUser();
    const { token: confirmerToken } = makeUser();
    const clubId = makeClub();

    await request(app).post(`/api/clubs/${clubId}/name`).set('Authorization', `Bearer ${proposerToken}`).send({ name: 'First Name' });
    await request(app).post(`/api/clubs/${clubId}/name/confirm`).set('Authorization', `Bearer ${confirmerToken}`);
    expect(db.prepare('SELECT COUNT(*) AS n FROM club_name_confirmations WHERE club_id = ?').get(clubId).n).toBe(1);

    await request(app).post(`/api/clubs/${clubId}/name`).set('Authorization', `Bearer ${proposerToken}`).send({ name: 'Second Name' });
    expect(db.prepare('SELECT COUNT(*) AS n FROM club_name_confirmations WHERE club_id = ?').get(clubId).n).toBe(0);
  });

  test('resubmitting the exact current name does not reset existing confirmations', async () => {
    const { token: proposerToken } = makeUser();
    const { token: confirmerToken } = makeUser();
    const clubId = makeClub();

    await request(app).post(`/api/clubs/${clubId}/name`).set('Authorization', `Bearer ${proposerToken}`).send({ name: 'Riverside Tennis Club' });
    await request(app).post(`/api/clubs/${clubId}/name/confirm`).set('Authorization', `Bearer ${confirmerToken}`);

    const res = await request(app)
      .post(`/api/clubs/${clubId}/name`)
      .set('Authorization', `Bearer ${proposerToken}`)
      .send({ name: 'Riverside Tennis Club' });

    expect(res.status).toBe(200);
    expect(db.prepare('SELECT COUNT(*) AS n FROM club_name_confirmations WHERE club_id = ?').get(clubId).n).toBe(1);
  });

  test('404s for a nonexistent club', async () => {
    const { token } = makeUser();
    const res = await request(app).post('/api/clubs/999999/name').set('Authorization', `Bearer ${token}`).send({ name: 'X' });
    expect(res.status).toBe(404);
  });

  test.each([
    ['empty', ''],
    ['whitespace only', '   '],
    ['over the length cap', 'x'.repeat(121)],
    ['not a string', { nested: true }],
  ])('rejects a name that is %s', async (_label, name) => {
    const { token } = makeUser();
    const clubId = makeClub();
    const res = await request(app).post(`/api/clubs/${clubId}/name`).set('Authorization', `Bearer ${token}`).send({ name });
    expect(res.status).toBe(400);
    expect(db.prepare('SELECT name FROM clubs WHERE id = ?').get(clubId).name).toBe('Old Name');
  });
});

describe('POST /clubs/:id/name/confirm', () => {
  test('flips name_verified once CONFIRMATION_THRESHOLD distinct users confirm', async () => {
    const { token: proposerToken } = makeUser();
    const clubId = makeClub();
    await request(app).post(`/api/clubs/${clubId}/name`).set('Authorization', `Bearer ${proposerToken}`).send({ name: 'Riverside Tennis Club' });

    const { token: confirmer1 } = makeUser();
    const first = await request(app).post(`/api/clubs/${clubId}/name/confirm`).set('Authorization', `Bearer ${confirmer1}`);
    expect(first.status).toBe(200);
    expect(first.body.club.name_verified).toBe(0);

    const { token: confirmer2 } = makeUser();
    const second = await request(app).post(`/api/clubs/${clubId}/name/confirm`).set('Authorization', `Bearer ${confirmer2}`);
    expect(second.body.club.name_verified).toBe(1);
  });

  test('rejects confirming a name you proposed yourself', async () => {
    const { token } = makeUser();
    const clubId = makeClub();
    await request(app).post(`/api/clubs/${clubId}/name`).set('Authorization', `Bearer ${token}`).send({ name: 'Riverside Tennis Club' });

    const res = await request(app).post(`/api/clubs/${clubId}/name/confirm`).set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(400);
  });

  test('rejects confirming a club with no user-proposed name yet', async () => {
    const { token } = makeUser();
    const clubId = makeClub();
    const res = await request(app).post(`/api/clubs/${clubId}/name/confirm`).set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(400);
  });

  test('404s for a nonexistent club', async () => {
    const { token } = makeUser();
    const res = await request(app).post('/api/clubs/999999/name/confirm').set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(404);
  });
});

describe('DELETE /courts/area-watch/:id', () => {
  test('only deletes the requesting user\'s own area watch', async () => {
    const owner = makeUser();
    const other = makeUser();
    const info = db.prepare(
      'INSERT INTO area_watches (user_id, latitude, longitude, radius_km) VALUES (?, ?, ?, ?)'
    ).run(owner.id, 51.5, -0.12, 5);

    const res = await request(app)
      .delete(`/api/courts/area-watch/${info.lastInsertRowid}`)
      .set('Authorization', `Bearer ${other.token}`);
    expect(res.status).toBe(204);
    // Deletes 0 rows silently rather than 404ing (same shape as the existing
    // per-court/per-club unwatch endpoints) -- still owned by `owner`.
    expect(db.prepare('SELECT user_id FROM area_watches WHERE id = ?').get(info.lastInsertRowid).user_id).toBe(owner.id);
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
