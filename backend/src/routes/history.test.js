// Regression test for the free-tier saved-shot limit (FREE_TIER_LIMIT = 3):
// the count-check and the INSERT are now one synchronous transaction
// (see history.js's insertAnalysis), closing the same class of race the
// analyse.js daily-limit fix addresses.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const historyRouter = require('./history');

const app = express();
app.use(express.json());
app.use('/api', historyRouter);

function makeUser(email) {
  const id = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(email, 'x', 'Test User').lastInsertRowid;
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

function saveShot(token) {
  return request(app)
    .post('/api/history')
    .set('Authorization', `Bearer ${token}`)
    .send({ shotType: 'forehand', matches: [{ overall_score: 80 }] });
}

describe('POST /history free-tier limit', () => {
  test('allows up to FREE_TIER_LIMIT (3) saves, then rejects with HISTORY_LIMIT', async () => {
    const { token } = makeUser('history1@test.com');
    for (let i = 0; i < 3; i++) {
      const res = await saveShot(token);
      expect(res.status).toBe(201);
    }
    const fourth = await saveShot(token);
    expect(fourth.status).toBe(403);
    expect(fourth.body.code).toBe('HISTORY_LIMIT');
  });

  test('a premium user is not capped', async () => {
    const { id, token } = makeUser('history2@test.com');
    db.prepare('UPDATE users SET tier = ? WHERE id = ?').run('premium', id);
    for (let i = 0; i < 5; i++) {
      const res = await saveShot(token);
      expect(res.status).toBe(201);
    }
  });
});

describe('PATCH /history/:id mutually-exclusive verdict flags', () => {
  test('rejects a request setting both flagged_not_shot and confirmed_real_shot to true', async () => {
    const { token } = makeUser('history3@test.com');
    const saved = await saveShot(token);
    expect(saved.status).toBe(201);
    const id = saved.body.id;

    const res = await request(app)
      .patch(`/api/history/${id}`)
      .set('Authorization', `Bearer ${token}`)
      .send({ flagged_not_shot: true, confirmed_real_shot: true });
    expect(res.status).toBe(400);

    const row = db.prepare('SELECT flagged_not_shot, confirmed_real_shot FROM analyses WHERE id = ?').get(id);
    expect(!!row.flagged_not_shot && !!row.confirmed_real_shot).toBe(false);
  });
});

// Regression test: pro_id/angle_label/tip_text used to have no type check at
// all -- a non-string value bound straight into the INSERT threw a
// TypeError out of better-sqlite3, surfacing as a bare 500 instead of the
// app's normal 400 shape (see history.js's comment on the same validate()
// call).
describe('POST /history rejects non-string pro_id/angle_label/tip_text', () => {
  test('an object pro_id is rejected with 400, not a 500', async () => {
    const { token } = makeUser('history4@test.com');
    const res = await request(app)
      .post('/api/history')
      .set('Authorization', `Bearer ${token}`)
      .send({ shotType: 'forehand', matches: [{ overall_score: 80, pro_id: { x: 1 } }] });
    expect(res.status).toBe(400);
    expect(res.body.field).toBe('matches[0] pro_id');
  });

  test('an array angle_label is rejected with 400, not a 500', async () => {
    const { token } = makeUser('history5@test.com');
    const res = await request(app)
      .post('/api/history')
      .set('Authorization', `Bearer ${token}`)
      .send({ shotType: 'forehand', angle_label: ['side'], matches: [{ overall_score: 80 }] });
    expect(res.status).toBe(400);
    expect(res.body.field).toBe('angle_label');
  });

  test('a boolean tip_text is rejected with 400, not a 500', async () => {
    const { token } = makeUser('history6@test.com');
    const res = await request(app)
      .post('/api/history')
      .set('Authorization', `Bearer ${token}`)
      .send({ shotType: 'forehand', matches: [{ overall_score: 80, tips: [{ tip_text: true }] }] });
    expect(res.status).toBe(400);
    expect(res.body.field).toBe('matches[0] tips[0].tip_text');
  });

  test('a valid string pro_id/angle_label/tip_text still saves fine', async () => {
    const { token } = makeUser('history7@test.com');
    const res = await request(app)
      .post('/api/history')
      .set('Authorization', `Bearer ${token}`)
      .send({
        shotType: 'forehand',
        angle_label: 'Semi-front',
        matches: [{ overall_score: 80, pro_id: 'forehand_0042', tips: [{ tip_text: 'Rotate your hips more.' }] }],
      });
    expect(res.status).toBe(201);
  });
});

// Regression test for a sweep finding: POST /history only validates
// matches[0] -- a null/non-object entry elsewhere in `matches` (or a
// non-array `matches` altogether) saved fine, since result_json is stored
// verbatim. GET /history's stripHeavyOverlays() then destructured every
// match entry unconditionally, so a single such row crashed the ENTIRE list
// with a TypeError, not just that row.
describe('GET /history survives a stored row with a malformed matches entry', () => {
  test('a null entry in matches (past index 0) does not take down the whole list', async () => {
    const { token } = makeUser('history8@test.com');
    const saveRes = await request(app)
      .post('/api/history')
      .set('Authorization', `Bearer ${token}`)
      .send({ shotType: 'forehand', matches: [{ overall_score: 80 }, null] });
    expect(saveRes.status).toBe(201);

    const listRes = await request(app).get('/api/history').set('Authorization', `Bearer ${token}`);
    expect(listRes.status).toBe(200);
    expect(listRes.body.analyses).toHaveLength(1);
  });

  test('a non-array matches does not take down the whole list', async () => {
    const { id } = makeUser('history9@test.com');
    const token = jwt.sign({ id }, process.env.JWT_SECRET);
    // Simulate a row that predates/bypassed matches[0]-only validation --
    // insert directly rather than via POST, since POST itself would 400 on
    // an object matches today; the point is GET must survive whatever is
    // already stored.
    db.prepare(
      `INSERT INTO analyses (user_id, shot_type, similarity, result_json) VALUES (?, 'forehand', 80, ?)`
    ).run(id, JSON.stringify({ shotType: 'forehand', matches: { not: 'an array' } }));

    const listRes = await request(app).get('/api/history').set('Authorization', `Bearer ${token}`);
    expect(listRes.status).toBe(200);
    expect(listRes.body.analyses).toHaveLength(1);
    expect(listRes.body.analyses[0].result.matches).toEqual([]);
  });
});
