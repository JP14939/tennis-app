// The Python matcher rejects a video that isn't a usable behind-the-baseline
// shot (view gate, roadmap 1a) by exiting non-zero with
// {error, code: 'VIEW_NOT_USABLE'} on stdout. The route must forward that
// `code` in the 500 body so the app can show a 'check your camera setup'
// screen instead of a generic 'analysis failed'.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

jest.mock('../utils/runPythonJson', () => ({
  runPythonJson: jest.fn(async () => {
    const err = new Error('pro_matcher.py exited with code 1');
    err.kind = 'nonzero_exit';
    err.stdout = JSON.stringify({
      error: 'The net runs out of the frame -- move back behind the baseline so both net posts are visible.',
      code: 'VIEW_NOT_USABLE',
    });
    throw err;
  }),
}));

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
  return { id, token: jwt.sign({ id }, process.env.JWT_SECRET) };
}

function postAnalyse(token) {
  return request(app)
    .post('/api/analyse')
    .set('Authorization', `Bearer ${token}`)
    .field('shotType', 'forehand')
    .attach('video', Buffer.from('not a real video'), 'swing.mp4');
}

describe('POST /analyse: view-gate rejection', () => {
  test('500 body carries the VIEW_NOT_USABLE code and the message', async () => {
    const { id, token } = makeUser('analyse-viewgate@test.com');

    const res = await postAnalyse(token);
    expect(res.status).toBe(500);
    expect(res.body.code).toBe('VIEW_NOT_USABLE');
    expect(res.body.error).toMatch(/behind the baseline/);

    // the matcher never produced a result -- the free-tier slot is refunded
    const { count } = db.prepare(
      `SELECT COUNT(*) AS count FROM analysis_usage WHERE user_id = ? AND date(created_at) = date('now')`
    ).get(id);
    expect(count).toBe(0);
  });
});
