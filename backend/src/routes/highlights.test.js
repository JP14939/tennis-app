// Regression test: POST /highlights/jobs/:id/reel used to only require auth,
// not premium, unlike its sibling /highlights/upload -- a non-premium user
// (or one who downgraded after a job was created) could still trigger
// resource-intensive reel-stitching. requirePremium must reject BEFORE the
// handler ever looks up the job/spawns anything, so this is testable without
// mocking the Python subprocess.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const highlightsRouter = require('./highlights');

const app = express();
app.use(express.json());
app.use('/api', highlightsRouter);

function makeUser(email, tier = 'free') {
  const id = db.prepare('INSERT INTO users (email, password_hash, name, tier) VALUES (?, ?, ?, ?)')
    .run(email, 'x', 'Test User', tier).lastInsertRowid;
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

describe('POST /highlights/jobs/:id/reel premium gate', () => {
  test('a free-tier user is rejected with PREMIUM_REQUIRED before any job lookup', async () => {
    const { token } = makeUser('reel_free@test.com', 'free');
    const res = await request(app)
      .post('/api/highlights/jobs/999999/reel')
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(403);
    expect(res.body.code).toBe('PREMIUM_REQUIRED');
  });

  test('a premium user with a nonexistent job gets a 404 (passes the gate, fails later)', async () => {
    const { token } = makeUser('reel_premium@test.com', 'premium');
    const res = await request(app)
      .post('/api/highlights/jobs/999999/reel')
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(404);
  });
});
