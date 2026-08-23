// Regression test for a usage-slot leak: reserveDailyUsageSlot() ran before
// contactTime was validated, and the early-return on invalid contactTime
// didn't call releaseUsageSlot() (every other failure path in this route
// does). A free-tier user sending a malformed contactTime burned one of
// their FREE_DAILY_LIMIT slots for a request that did zero analysis work.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const analyseRouter = require('./analyse');

const app = express();
app.use(express.json());
app.use('/api', analyseRouter);

function makeUser(email) {
  const id = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(email, 'x', 'Test User').lastInsertRowid;
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

function postAnalyse(token, { contactTime } = {}) {
  const req = request(app)
    .post('/api/analyse')
    .set('Authorization', `Bearer ${token}`)
    .field('shotType', 'forehand')
    .attach('video', Buffer.from('not a real video'), 'swing.mp4');
  if (contactTime !== undefined) req.field('contactTime', contactTime);
  return req;
}

describe('POST /analyse invalid contactTime', () => {
  test('does not consume a free-tier daily usage slot', async () => {
    const { id, token } = makeUser('analyse-leak@test.com');

    // FREE_DAILY_LIMIT is 2 -- send more invalid-contactTime requests than
    // that. If the slot were being leaked, one of these would flip from 400
    // (bad contactTime) to 403 DAILY_LIMIT before ever reaching the limit
    // for real analysis attempts.
    for (let i = 0; i < 3; i++) {
      const res = await postAnalyse(token, { contactTime: 'not-a-number' });
      expect(res.status).toBe(400);
      expect(res.body.error).toMatch(/contactTime must be a number/);
    }

    const { count } = db.prepare(
      `SELECT COUNT(*) AS count FROM analysis_usage WHERE user_id = ? AND date(created_at) = date('now')`
    ).get(id);
    expect(count).toBe(0);
  });

  test('rejects a non-finite contactTime (Infinity) with 400', async () => {
    const { token } = makeUser('analyse-infinity@test.com');
    const res = await postAnalyse(token, { contactTime: 'Infinity' });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/contactTime must be a number/);
  });
});
