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
