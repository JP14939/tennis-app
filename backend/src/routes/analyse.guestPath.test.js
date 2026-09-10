// The onboarding flow lets a logged-out user run their first analysis and see
// the score BEFORE being asked to sign up (docs/plans/onboarding_plan.md,
// "gate at the reveal"). /analyse is optionalAuth for that reason.
//
// This locks in that a guest request is *accepted* past the auth layer (400 on
// bad input, not 401). The guest-specific per-IP cap is consumed inside the
// handler only once a request is about to spawn Python -- so it can't be
// exercised here without a real MediaPipe run; its check-and-consume core
// (tryConsume) is unit-tested in middleware/rateLimit.test.js instead.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const analyseRouter = require('./analyse');

const app = express();
app.use(express.json());
app.use('/api', analyseRouter);

describe('POST /analyse guest path', () => {
  test('accepts an unauthenticated request (400 on bad input, not 401)', async () => {
    const res = await request(app)
      .post('/api/analyse')
      // no Authorization header -- this is the guest path
      .field('shotType', 'forehand')
      .field('contactTime', 'not-a-number') // 400s before the guest slot is spent or Python spawns
      .attach('video', Buffer.from('not a real video'), 'swing.mp4');
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/contactTime/i);
  });
});
