// auth.js had no test file at all before this session added a length cap
// to `name` (previously truthy/trim-only, so an unbounded name string was
// accepted). Scoped strictly to that one change, matching the same
// "close the gap this session's own work created" reasoning as
// annotations.validation.test.js -- not an attempt at full auth coverage,
// which CLAUDE.md tracks as a known, separate gap.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const authRouter = require('./auth');

const app = express();
app.use(express.json());
app.use('/api', authRouter);

let counter = 0;
function signupBody(overrides = {}) {
  counter += 1;
  return { email: `user${counter}@test.com`, password: 'password123', name: 'A Name', ...overrides };
}

describe('POST /auth/signup — name length cap', () => {
  test('accepts a name exactly at the cap (80 chars)', async () => {
    const res = await request(app).post('/api/auth/signup').send(signupBody({ name: 'x'.repeat(80) }));
    expect(res.status).toBe(201);
  });

  test('rejects a name over the cap and creates no account', async () => {
    const before = db.prepare('SELECT COUNT(*) AS n FROM users').get().n;
    const res = await request(app).post('/api/auth/signup').send(signupBody({ name: 'x'.repeat(81) }));
    expect(res.status).toBe(400);
    expect(db.prepare('SELECT COUNT(*) AS n FROM users').get().n).toBe(before);
  });

  test('still rejects an empty/whitespace-only name', async () => {
    const res = await request(app).post('/api/auth/signup').send(signupBody({ name: '   ' }));
    expect(res.status).toBe(400);
  });
});

describe('PATCH /auth/me — name length cap', () => {
  async function makeAuthedUser() {
    const signup = await request(app).post('/api/auth/signup').send(signupBody());
    return signup.body.token;
  }

  test('accepts an update within the cap', async () => {
    const token = await makeAuthedUser();
    const res = await request(app).patch('/api/auth/me').set('Authorization', `Bearer ${token}`).send({ name: 'New Name' });
    expect(res.status).toBe(200);
    expect(res.body.user.name).toBe('New Name');
  });

  test('rejects an update over the cap, leaving the stored name unchanged', async () => {
    const token = await makeAuthedUser();
    const before = await request(app).get('/api/auth/me').set('Authorization', `Bearer ${token}`);

    const res = await request(app).patch('/api/auth/me').set('Authorization', `Bearer ${token}`).send({ name: 'x'.repeat(81) });
    expect(res.status).toBe(400);

    const after = await request(app).get('/api/auth/me').set('Authorization', `Bearer ${token}`);
    expect(after.body.user.name).toBe(before.body.user.name);
  });
});
