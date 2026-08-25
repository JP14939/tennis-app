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
