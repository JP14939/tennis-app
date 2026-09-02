// Regression test for a sweep finding: the old single try/catch around both
// the Python matcher call AND the post-processing (persistAndCrop, pro clip
// URL resolution) released the free-tier daily usage slot on ANY failure in
// that block -- including one after the actual (expensive) analysis had
// already succeeded. A transient local failure in the cheap post-processing
// step (e.g. a full disk copying the user's clip into permanent storage)
// would silently refund the slot, letting a persistent infra issue give
// free users unlimited real analyses for as long as it lasted.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

jest.mock('../utils/runPythonJson', () => ({
  runPythonJson: jest.fn(async () => ({ shot_type: 'forehand', matches: [] })),
}));
jest.mock('../utils/videoCrop', () => ({
  persistAndCrop: jest.fn(async () => { throw new Error('ENOSPC: no space left on device'); }),
  croppedProClipPath: jest.fn(async () => null),
  toUrl: jest.fn(() => '/user-clips/fake'),
  PRO_CLIPS_DIR: '/tmp/pro-clips',
  PRO_CLIPS_CROPPED_DIR: '/tmp/pro-clips-cropped',
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
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

function postAnalyse(token) {
  return request(app)
    .post('/api/analyse')
    .set('Authorization', `Bearer ${token}`)
    .field('shotType', 'forehand')
    .attach('video', Buffer.from('not a real video'), 'swing.mp4');
}

describe('POST /analyse: a post-processing failure after a successful analysis', () => {
  test('does not refund the free-tier usage slot', async () => {
    const { id, token } = makeUser('analyse-postproc@test.com');

    const res = await postAnalyse(token);
    expect(res.status).toBe(500);

    const { count } = db.prepare(
      `SELECT COUNT(*) AS count FROM analysis_usage WHERE user_id = ? AND date(created_at) = date('now')`
    ).get(id);
    expect(count).toBe(1);
  });
});
