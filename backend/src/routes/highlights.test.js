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

  test('rejects a non-integer rallyIds element with 400 instead of a 500 crash', async () => {
    // Binding a non-integer element (e.g. an object) straight into the SQL
    // '?' placeholders used to throw a RangeError deep in better-sqlite3.
    const { id: userId, token } = makeUser('reel_badids@test.com', 'premium');
    const jobId = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, 'x', 'done')`)
      .run(userId).lastInsertRowid;
    const res = await request(app)
      .post(`/api/highlights/jobs/${jobId}/reel`)
      .set('Authorization', `Bearer ${token}`)
      .send({ rallyIds: [1, {}, 3] });
    expect(res.status).toBe(400);
  });
});

describe('PATCH /highlights/rallies/:id field validation', () => {
  test('rejects a non-string outcome_tag with 400 instead of a 500 crash', async () => {
    const { id: userId, token } = makeUser('rally_badtag@test.com', 'free');
    const jobId = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, 'x', 'done')`)
      .run(userId).lastInsertRowid;
    const clipId = db.prepare(`
      INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
      VALUES (?, ?, 'clip.mp4', 0, 1, 1, 1)
    `).run(jobId, userId).lastInsertRowid;

    const res = await request(app)
      .patch(`/api/highlights/rallies/${clipId}`)
      .set('Authorization', `Bearer ${token}`)
      .send({ outcome_tag: { bogus: true } });
    expect(res.status).toBe(400);
  });
});
