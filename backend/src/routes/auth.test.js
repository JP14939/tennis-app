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

describe('DELETE /auth/me', () => {
  // Regression test for a logic-review fix: drill_practice_attempts.analysis_id
  // references analyses(id), and FK enforcement is on by default, so the
  // transaction must delete drill_practice_attempts before analyses -- it used
  // to run the other way round, which threw SQLITE_CONSTRAINT_FOREIGNKEY (a 500)
  // for any user who had practiced a drill/lesson step against their own analysis.
  test('deletes an account that has a drill practice attempt linked to its own analysis', async () => {
    const email = 'deleteme-drills@test.com';
    const password = 'password123';
    const passwordHash = await bcrypt.hash(password, 10);
    const userId = db.prepare('INSERT INTO users (email, password_hash, name, username, notifications_enabled) VALUES (?, ?, ?, ?, ?)')
      .run(email, passwordHash, 'Delete Me', `user_${Date.now()}_${Math.floor(Math.random() * 1e6)}`, 1)
      .lastInsertRowid;
    const token = jwt.sign({ id: userId }, process.env.JWT_SECRET);

    const analysisId = db.prepare(
      "INSERT INTO analyses (user_id, shot_type, similarity, result_json) VALUES (?, 'forehand', 80, '{}')"
    ).run(userId).lastInsertRowid;
    const drillItemId = db.prepare(
      "INSERT INTO drill_items (kind, shot_type, title, explanation) VALUES ('drill', 'forehand', 'T', 'E')"
    ).run().lastInsertRowid;
    const stepId = db.prepare(
      'INSERT INTO drill_routine_steps (drill_item_id, step_order, label) VALUES (?, 0, ?)'
    ).run(drillItemId, 'Step').lastInsertRowid;
    db.prepare(
      'INSERT INTO drill_practice_attempts (user_id, step_id, analysis_id) VALUES (?, ?, ?)'
    ).run(userId, stepId, analysisId);

    const res = await request(app)
      .delete('/api/auth/me')
      .set('Authorization', `Bearer ${token}`)
      .send({ password });

    expect(res.status).toBe(204);
    expect(db.prepare('SELECT * FROM analyses WHERE user_id = ?').get(userId)).toBeUndefined();
    expect(db.prepare('SELECT * FROM drill_practice_attempts WHERE user_id = ?').get(userId)).toBeUndefined();
  });
});
