// Coverage for the id-validation guards added to POST /drills/:stepId/practice
// this session -- drills.test.js already covers this route's happy path and
// ownership check, but not the actual validation branches that were added
// (Invalid step id / analysisId must be a valid analysis id).
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const drillsRouter = require('./drills');

const app = express();
app.use(express.json());
app.use('/api', drillsRouter);

// Every test in this file shares one in-memory DB with no reset between
// tests (matches the rest of this session's route test files) -- a counter
// keeps each call's email unique rather than colliding on users.email's
// UNIQUE constraint.
let userCounter = 0;
function makeUser() {
  userCounter += 1;
  const id = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(`user${userCounter}@test.com`, 'x', 'Test User').lastInsertRowid;
  return { id, token: jwt.sign({ id }, process.env.JWT_SECRET) };
}

function makeStep() {
  const itemId = db.prepare(
    "INSERT INTO drill_items (kind, shot_type, title, explanation) VALUES ('drill', 'forehand', 'T', 'E')"
  ).run().lastInsertRowid;
  return db.prepare(
    "INSERT INTO drill_routine_steps (drill_item_id, step_order, label) VALUES (?, 0, 'Step')"
  ).run(itemId).lastInsertRowid;
}

function practice(token, stepId, body) {
  return request(app).post(`/api/drills/${stepId}/practice`).set('Authorization', `Bearer ${token}`).send(body);
}

describe('POST /drills/:stepId/practice — stepId', () => {
  test('accepts a real step id', async () => {
    const { token } = makeUser();
    const stepId = makeStep();
    const res = await practice(token, stepId, {});
    expect(res.status).toBe(200);
  });

  test.each(['abc', '1.5', '0', '-1'])('rejects the stepId param %p with a clean 400', async (stepId) => {
    const { token } = makeUser();
    const before = db.prepare('SELECT COUNT(*) AS n FROM drill_practice_attempts').get().n;
    const res = await practice(token, stepId, {});
    expect(res.status).toBe(400);
    expect(db.prepare('SELECT COUNT(*) AS n FROM drill_practice_attempts').get().n).toBe(before);
  });
});

describe('POST /drills/:stepId/practice — analysisId', () => {
  test('omitting analysisId is fine -- practice without a linked analysis', async () => {
    const { token } = makeUser();
    const stepId = makeStep();
    const res = await practice(token, stepId, {});
    expect(res.status).toBe(200);
    expect(res.body.attempt_count).toBe(1);
  });

  test.each([
    ['abc', 'not a number'],
    [0, 'not a real row id'],
    [{}, 'an object'],
  ])('rejects analysisId %p (%s)', async (analysisId) => {
    const { token } = makeUser();
    const stepId = makeStep();
    const before = db.prepare('SELECT COUNT(*) AS n FROM drill_practice_attempts').get().n;

    const res = await practice(token, stepId, { analysisId });
    expect(res.status).toBe(400);
    expect(db.prepare('SELECT COUNT(*) AS n FROM drill_practice_attempts').get().n).toBe(before);
  });

  test('still refuses an analysisId that is well-formed but belongs to someone else', async () => {
    const { token } = makeUser();
    const stranger = makeUser();
    const strangerAnalysisId = db.prepare(
      "INSERT INTO analyses (user_id, shot_type, similarity, result_json) VALUES (?, 'forehand', 80, '{}')"
    ).run(stranger.id).lastInsertRowid;
    const stepId = makeStep();

    const res = await practice(token, stepId, { analysisId: strangerAnalysisId });
    expect(res.status).toBe(403);
  });
});
