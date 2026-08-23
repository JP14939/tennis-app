// annotations.js had no test file at all before this session's validation
// pass added the stroke-array size cap and the id guards -- every other
// route touched this session got dedicated coverage; this closes the same
// gap here. Scoped to what changed today (validation + id guards), not a
// full route test suite -- CLAUDE.md is explicit that most route files
// having zero coverage is a known, tracked gap, not something to fix at
// scale in passing.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const annotationsRouter = require('./annotations');

const app = express();
app.use(express.json());
app.use('/api', annotationsRouter);

let userCounter = 0;
function makeUser() {
  userCounter += 1;
  const id = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(`user${userCounter}@test.com`, 'x', 'Test User').lastInsertRowid;
  return { id, token: jwt.sign({ id }, process.env.JWT_SECRET) };
}

function makeAnalysis(userId) {
  return db.prepare(
    "INSERT INTO analyses (user_id, shot_type, similarity, result_json) VALUES (?, 'forehand', 80, '{}')"
  ).run(userId).lastInsertRowid;
}

function putAnnotations(token, analysisId, body) {
  return request(app).put(`/api/analyses/${analysisId}/annotations`).set('Authorization', `Bearer ${token}`).send(body);
}

const validBody = { paneAStrokes: [{ tool: 'pen', color: '#000', points: [{ x: 1, y: 1 }] }], paneBStrokes: [] };

describe('PUT /analyses/:analysisId/annotations — analysisId param', () => {
  test.each(['abc', '1.5', '0', '-1'])('rejects %p with a clean 400', async (analysisId) => {
    const { token } = makeUser();
    const res = await putAnnotations(token, analysisId, validBody);
    expect(res.status).toBe(400);
  });
});

describe('PUT /analyses/:analysisId/annotations — stroke arrays', () => {
  test('saves a normal annotation for the owner', async () => {
    const { id, token } = makeUser();
    const analysisId = makeAnalysis(id);
    const res = await putAnnotations(token, analysisId, validBody);
    expect(res.status).toBe(200);
    expect(db.prepare('SELECT COUNT(*) AS n FROM swing_annotations WHERE analysis_id = ?').get(analysisId).n).toBe(1);
  });

  test.each([
    [{ paneAStrokes: 'not-an-array' }, 'a string instead of an array'],
    [{ paneAStrokes: { tool: 'pen' } }, 'an object instead of an array'],
    [{ paneAStrokes: undefined }, 'missing entirely'],
  ])('rejects paneAStrokes as %p (%s)', async (override) => {
    const { id, token } = makeUser();
    const analysisId = makeAnalysis(id);
    const res = await putAnnotations(token, analysisId, { ...validBody, ...override });
    expect(res.status).toBe(400);
    expect(db.prepare('SELECT COUNT(*) AS n FROM swing_annotations WHERE analysis_id = ?').get(analysisId).n).toBe(0);
  });

  test('rejects a stroke array that serializes over the 40KB field cap', async () => {
    const { id, token } = makeUser();
    const analysisId = makeAnalysis(id);
    // Sized to land between the 40KB field cap and express.json()'s 100KB
    // whole-body limit -- big enough to trip the field-level check this
    // test targets, small enough to actually reach the route (a payload
    // over 100KB would 413 at the body parser instead, testing a different
    // thing entirely -- confirmed the hard way, see invariants.js's
    // annotationStrokesJson comment for why the cap itself was lowered).
    const stroke = { tool: 'pen', color: '#000', points: Array.from({ length: 3500 }, (_, i) => ({ x: i + 1000, y: i + 1000 })) };

    const res = await putAnnotations(token, analysisId, { paneAStrokes: [stroke], paneBStrokes: [] });
    expect(res.status).toBe(400);
    expect(db.prepare('SELECT COUNT(*) AS n FROM swing_annotations WHERE analysis_id = ?').get(analysisId).n).toBe(0);
  });

  test('a save overwrites the same author\'s previous save rather than duplicating', async () => {
    const { id, token } = makeUser();
    const analysisId = makeAnalysis(id);
    await putAnnotations(token, analysisId, validBody);
    await putAnnotations(token, analysisId, { paneAStrokes: [], paneBStrokes: [] });

    expect(db.prepare('SELECT COUNT(*) AS n FROM swing_annotations WHERE analysis_id = ?').get(analysisId).n).toBe(1);
  });

  test('still refuses to save on an analysis you cannot access', async () => {
    const { token } = makeUser();
    const stranger = makeUser();
    const analysisId = makeAnalysis(stranger.id);

    const res = await putAnnotations(token, analysisId, validBody);
    expect(res.status).toBe(403);
  });
});

describe('GET /analyses/:analysisId/annotations — analysisId param', () => {
  test.each(['abc', '0'])('rejects %p with a clean 400', async (analysisId) => {
    const { token } = makeUser();
    const res = await request(app).get(`/api/analyses/${analysisId}/annotations`).set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(400);
  });
});
