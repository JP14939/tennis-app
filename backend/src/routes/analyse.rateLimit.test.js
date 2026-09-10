// Regression test for the resource-exhaustion gap fixed alongside this test:
// FREE_DAILY_LIMIT only caps successful analyses (a failed one releases its
// reserved usage slot, by design, so a real user isn't charged for a request
// that errored through no fault of their own) -- which meant nothing capped
// the number of *attempts*. A user submitting videos engineered to fail
// (e.g. the bad contactTime case below, which never even reaches the Python
// subprocess) could hit this route an unlimited number of times. analyseLimiter
// closes that by capping total requests per user regardless of outcome.
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

function postInvalidAnalyse(token) {
  return request(app)
    .post('/api/analyse')
    .set('Authorization', `Bearer ${token}`)
    .field('shotType', 'forehand')
    .field('contactTime', 'not-a-number')
    .attach('video', Buffer.from('not a real video'), 'swing.mp4');
}

describe('POST /analyse rate limiting', () => {
  test('caps repeated requests from the same user regardless of outcome', async () => {
    const { token } = makeUser('analyse-ratelimit@test.com');

    // analyseLimiter's max is 30 per window -- every one of these requests
    // 400s on the bad contactTime before ever reaching the Python subprocess,
    // which is exactly the abuse shape being closed (a request that costs
    // real spawn/process work without ever counting against the daily
    // successful-analysis cap).
    let lastStatus;
    for (let i = 0; i < 31; i++) {
      // eslint-disable-next-line no-await-in-loop
      lastStatus = (await postInvalidAnalyse(token)).status;
    }
    expect(lastStatus).toBe(429);
  });

  test('does not rate limit a different user sharing no bucket with the first', async () => {
    const { token } = makeUser('analyse-ratelimit-other@test.com');
    const res = await postInvalidAnalyse(token);
    expect(res.status).toBe(400);
  });

  test('the coarser IP-keyed layer caps a single origin cycling through many accounts', async () => {
    // analyseIpLimiter's max is 80 per window, keyed by req.ip. Three fresh
    // accounts each stay well under the per-user max of 30, so nothing in the
    // per-user layer stops them -- but 81 requests from the one test-client IP
    // trips the IP layer. This is the account-rotation gap from
    // PRE_RELEASE_CHECK.md A1.
    const tokens = [0, 1, 2].map((n) => makeUser(`analyse-ip-rotate-${n}@test.com`).token);
    let lastStatus;
    for (let i = 0; i < 81; i++) {
      // eslint-disable-next-line no-await-in-loop
      lastStatus = (await postInvalidAnalyse(tokens[i % 3])).status;
    }
    expect(lastStatus).toBe(429);
  });
});
