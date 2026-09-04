// Regression test for a bug-sweep finding: when persistAndCrop() fails
// partway through (e.g. it successfully copies the original clip into
// USER_CLIPS_DIR/<uploadId>/ but then fails cropping it), the post-
// processing catch block in analyse.js only cleaned up the raw multer
// upload (cleanup()) -- it never removed the partially-written
// USER_CLIPS_DIR/<uploadId>/ directory itself, leaking an orphaned/partial
// file on every such failure. compareVideos.js already had the equivalent
// cleanup (fs.rmSync of its whole per-job directory) for the same failure
// shape; analyse.js did not.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const fs = require('fs');
const path = require('path');
const os = require('os');

// Jest hoists jest.mock() factories above regular const declarations, but
// allows referencing variables prefixed with `mock` (babel-plugin-jest-hoist's
// allowlist) -- hence the naming here instead of a plain DATA_DIR const.
const mockDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'analyse-data-'));
const USER_CLIPS_DIR = path.join(mockDataDir, 'runtime', 'user_clips');

jest.mock('../config/paths', () => {
  const actual = jest.requireActual('../config/paths');
  return { ...actual, DATA_DIR: mockDataDir };
});

jest.mock('../utils/runPythonJson', () => ({
  runPythonJson: jest.fn(async () => ({ shot_type: 'forehand', matches: [] })),
}));
jest.mock('../utils/videoCrop', () => ({
  persistAndCrop: jest.fn(async (srcPath, destDir) => {
    const fs2 = require('fs');
    const path2 = require('path');
    fs2.mkdirSync(destDir, { recursive: true });
    fs2.writeFileSync(path2.join(destDir, 'original.mp4'), 'partial');
    throw new Error('ENOSPC: no space left on device while cropping');
  }),
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

afterAll(() => {
  fs.rmSync(mockDataDir, { recursive: true, force: true });
});

describe('POST /analyse: persistAndCrop failing partway through', () => {
  test('removes the partially-written per-upload directory instead of leaking it', async () => {
    const { token } = makeUser('analyse-partial-persist@test.com');

    const res = await request(app)
      .post('/api/analyse')
      .set('Authorization', `Bearer ${token}`)
      .field('shotType', 'forehand')
      .attach('video', Buffer.from('not a real video'), 'swing.mp4');

    expect(res.status).toBe(500);

    expect(fs.existsSync(USER_CLIPS_DIR) ? fs.readdirSync(USER_CLIPS_DIR) : []).toEqual([]);
  });
});
