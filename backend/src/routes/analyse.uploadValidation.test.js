// Regression test for the video-upload extension check added to
// utils/videoUpload.js -- every upload route used to build its stored
// filename straight from the client-supplied original filename's extension
// with no allowlist at all, so a non-video extension (e.g. ".html") on a
// file that later gets persisted and served back through a static mount
// (server.js's /user-clips etc.) would be served with a browser-guessed
// Content-Type matching that extension instead of a video one.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const multer = require('multer');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const analyseRouter = require('./analyse');
const { UnsupportedFileTypeError } = require('../utils/videoUpload');

const app = express();
app.use(express.json());
app.use('/api', analyseRouter);
// Mirrors server.js's global error handler for the two upload-rejection
// shapes multer/videoFileFilter can produce -- without this, an app that
// only mounts the router (like this test) can't observe the clean 400 a
// real deployment returns; the raw error would otherwise propagate as an
// uncaught rejection.
// eslint-disable-next-line no-unused-vars
app.use((err, req, res, next) => {
  if (err instanceof multer.MulterError) {
    return res.status(400).json({ error: err.message });
  }
  if (err instanceof UnsupportedFileTypeError) {
    return res.status(400).json({ error: err.message });
  }
  res.status(500).json({ error: 'Internal server error' });
});

function makeUser(email) {
  const id = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(email, 'x', 'Test User').lastInsertRowid;
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

describe('POST /analyse rejects non-video upload extensions', () => {
  test('rejects a .html upload with a clean 400, before any usage slot is reserved', async () => {
    const { id, token } = makeUser('upload-ext@test.com');

    const res = await request(app)
      .post('/api/analyse')
      .set('Authorization', `Bearer ${token}`)
      .field('shotType', 'forehand')
      .attach('video', Buffer.from('<script>alert(1)</script>'), 'shell.html');

    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/Unsupported file type/);

    const { count } = db.prepare(
      `SELECT COUNT(*) AS count FROM analysis_usage WHERE user_id = ? AND date(created_at) = date('now')`
    ).get(id);
    expect(count).toBe(0);
  });

  test('still accepts a .mp4 upload past the file-type check', async () => {
    const { token } = makeUser('upload-ext-ok@test.com');

    // Not a real video, so this will fail later (bad shotType/pipeline) --
    // the point here is only that it gets PAST the file-type filter rather
    // than being rejected as an unsupported type.
    const res = await request(app)
      .post('/api/analyse')
      .set('Authorization', `Bearer ${token}`)
      .field('shotType', 'forehand')
      .attach('video', Buffer.from('not a real video'), 'swing.mp4');

    expect(res.body.error).not.toMatch(/Unsupported file type/);
  });
});
