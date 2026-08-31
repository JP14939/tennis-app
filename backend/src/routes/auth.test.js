// Regression tests for bug-sweep fixes to auth.js:
//  - non-string name/token/password fields used to reach bcrypt/crypto
//    unguarded and crash with a 500 instead of a clean 400.
//  - PATCH /auth/me used to read the full user row and write back its
//    stale snapshot for any field a request omitted, instead of leaving
//    that column untouched at the SQL level -- fixed via COALESCE.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');
const db = require('../db');
const authRouter = require('./auth');

const app = express();
app.use(express.json());
app.use('/api', authRouter);

function makeUser(email) {
  const id = db.prepare('INSERT INTO users (email, password_hash, name, username, notifications_enabled) VALUES (?, ?, ?, ?, ?)')
    .run(email, '$2a$10$invalidsaltinvalidsaltinvalidsaltuw', 'Test User', `user_${Date.now()}_${Math.floor(Math.random() * 1e6)}`, 1)
    .lastInsertRowid;
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

describe('POST /auth/signup input validation', () => {
  test('rejects a non-string name with 400, not a crash', async () => {
    const res = await request(app)
      .post('/api/auth/signup')
      .send({ email: 'nonstring-name@test.com', password: 'password123', name: 42 });
    expect(res.status).toBe(400);
  });

  test('rejects a non-string password with 400, not a crash', async () => {
    const res = await request(app)
      .post('/api/auth/signup')
      .send({ email: 'nonstring-pw@test.com', password: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'], name: 'A' });
    expect(res.status).toBe(400);
  });
});

describe('POST /auth/reset-password input validation', () => {
  test('rejects a non-string token with 400, not a crash', async () => {
    const res = await request(app)
      .post('/api/auth/reset-password')
      .send({ token: 12345, newPassword: 'password123' });
    expect(res.status).toBe(400);
  });
});

describe('PATCH /auth/me partial updates', () => {
  test('updating only name leaves username and notifications_enabled untouched', async () => {
    const { id, token } = makeUser('patchme1@test.com');
    const before = db.prepare('SELECT username, notifications_enabled FROM users WHERE id = ?').get(id);

    const res = await request(app)
      .patch('/api/auth/me')
      .set('Authorization', `Bearer ${token}`)
      .send({ name: 'New Name' });

    expect(res.status).toBe(200);
    expect(res.body.user.name).toBe('New Name');

    const after = db.prepare('SELECT username, notifications_enabled FROM users WHERE id = ?').get(id);
    expect(after.username).toBe(before.username);
    expect(after.notifications_enabled).toBe(before.notifications_enabled);
  });

  test('updating only notifications_enabled leaves name and username untouched', async () => {
    const { id, token } = makeUser('patchme2@test.com');
    const before = db.prepare('SELECT name, username FROM users WHERE id = ?').get(id);

    const res = await request(app)
      .patch('/api/auth/me')
      .set('Authorization', `Bearer ${token}`)
      .send({ notifications_enabled: false });

    expect(res.status).toBe(200);
    expect(res.body.user.notifications_enabled).toBe(false);

    const after = db.prepare('SELECT name, username FROM users WHERE id = ?').get(id);
    expect(after.name).toBe(before.name);
    expect(after.username).toBe(before.username);
  });
});

// Regression tests for the token_version fix: a JWT issued before a
// password change or account deletion used to keep working, unchecked, for
// the rest of its 30-day life -- requireAuth/optionalAuth never re-verified
// anything about the account after the initial signature check. See
// db.js's token_version comment for the full reasoning.
describe('token_version revocation', () => {
  function makeUserWithPassword(email, plaintextPassword) {
    const passwordHash = bcrypt.hashSync(plaintextPassword, 10);
    const id = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
      .run(email, passwordHash, 'Test User').lastInsertRowid;
    // tv: 0 explicitly, matching a real issueToken() call against a
    // freshly-created row (token_version defaults to 0).
    const token = jwt.sign({ id, tv: 0 }, process.env.JWT_SECRET);
    return { id, token };
  }

  test('PATCH /auth/password invalidates tokens issued before the change', async () => {
    const { token } = makeUserWithPassword('revoke-password@test.com', 'originalpass123');

    const changeRes = await request(app)
      .patch('/api/auth/password')
      .set('Authorization', `Bearer ${token}`)
      .send({ currentPassword: 'originalpass123', newPassword: 'newpassword456' });
    expect(changeRes.status).toBe(204);

    const staleRes = await request(app)
      .get('/api/auth/me')
      .set('Authorization', `Bearer ${token}`);
    expect(staleRes.status).toBe(401);
  });

  test('DELETE /auth/me invalidates tokens issued before the deletion', async () => {
    const { token } = makeUserWithPassword('revoke-delete@test.com', 'deletemepass123');

    const deleteRes = await request(app)
      .delete('/api/auth/me')
      .set('Authorization', `Bearer ${token}`)
      .send({ password: 'deletemepass123' });
    expect(deleteRes.status).toBe(204);

    const staleRes = await request(app)
      .get('/api/auth/me')
      .set('Authorization', `Bearer ${token}`);
    expect(staleRes.status).toBe(401);
  });

  test('a token signed before the token_version column existed (no tv claim) still works against a fresh row', async () => {
    const { id } = makeUserWithPassword('revoke-legacy@test.com', 'legacypass123');
    // Simulate a token minted by the pre-fix issueToken(), which never set tv.
    const legacyToken = jwt.sign({ id }, process.env.JWT_SECRET);

    const res = await request(app)
      .get('/api/auth/me')
      .set('Authorization', `Bearer ${legacyToken}`);
    expect(res.status).toBe(200);
  });
});
