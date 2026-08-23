// Coverage for the validation added to POST /dev/drills this session --
// dev.drills.test.js already covers the CRUD/step-reconciliation behavior,
// but only ever sends well-formed bodies. Nothing exercised the actual
// validation branches (kind/shot_type/title/explanation/emphasis, or the
// per-step label/shot_type/target_reps checks), which is exactly the gap
// every other route touched this session got closed for.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';
process.env.ADMIN_EMAILS = 'admin@test.com';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const devRouter = require('./dev');

const app = express();
app.use(express.json());
app.use('/api', devRouter);

function makeAdmin() {
  const id = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(`admin${Math.random()}@test.com`, 'x', 'Admin').lastInsertRowid;
  return { id, token: jwt.sign({ id, email: 'admin@test.com' }, process.env.JWT_SECRET) };
}

function post(token, fields) {
  let req = request(app).post('/api/dev/drills').set('Authorization', `Bearer ${token}`);
  for (const [key, value] of Object.entries(fields)) req = req.field(key, value);
  return req;
}

const validFields = { kind: 'drill', shot_type: 'forehand', title: 'T', explanation: 'E', steps: '[]' };

describe('POST /dev/drills — kind', () => {
  test.each(['drill', 'lesson'])('accepts %p', async (kind) => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, kind });
    expect(res.status).toBe(200);
  });

  test.each(['routine', 'Drill', '', 'footwork'])('rejects %p and creates nothing', async (kind) => {
    const { token } = makeAdmin();
    const before = db.prepare('SELECT COUNT(*) AS n FROM drill_items').get().n;
    const res = await post(token, { ...validFields, kind });
    expect(res.status).toBe(400);
    expect(db.prepare('SELECT COUNT(*) AS n FROM drill_items').get().n).toBe(before);
  });
});

describe('POST /dev/drills — shot_type', () => {
  // Drills cover one category the ML pipeline's own SHOT_TYPES doesn't:
  // 'footwork' has no swing to analyse, so it's valid HERE specifically.
  test.each(['forehand', 'backhand', 'serve', 'footwork'])('accepts %p', async (shot_type) => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, shot_type });
    expect(res.status).toBe(200);
  });

  test.each(['volley', 'Forehand', ''])('rejects %p', async (shot_type) => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, shot_type });
    expect(res.status).toBe(400);
  });
});

describe('POST /dev/drills — title / explanation / emphasis length caps', () => {
  test('rejects an empty title', async () => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, title: '' });
    expect(res.status).toBe(400);
  });

  test('rejects a title over the cap', async () => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, title: 'x'.repeat(201) });
    expect(res.status).toBe(400);
  });

  test('rejects an empty explanation', async () => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, explanation: '' });
    expect(res.status).toBe(400);
  });

  test('emphasis is optional but still capped when present', async () => {
    const { token } = makeAdmin();
    const okRes = await post(token, { ...validFields, emphasis: 'fine' });
    expect(okRes.status).toBe(200);
    const badRes = await post(token, { ...validFields, emphasis: 'x'.repeat(5001) });
    expect(badRes.status).toBe(400);
  });
});

describe('POST /dev/drills — steps', () => {
  test('rejects malformed JSON in steps', async () => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, steps: '{not json' });
    expect(res.status).toBe(400);
  });

  test('rejects steps that parse but are not an array', async () => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, steps: '{"label":"x"}' });
    expect(res.status).toBe(400);
  });

  test('rejects a step with no label', async () => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, steps: JSON.stringify([{ shot_type: 'forehand' }]) });
    expect(res.status).toBe(400);
  });

  test('rejects a step whose shot_type is not in the drill vocabulary', async () => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, steps: JSON.stringify([{ label: 'L', shot_type: 'volley' }]) });
    expect(res.status).toBe(400);
  });

  test('rejects a non-positive target_reps', async () => {
    const { token } = makeAdmin();
    const res = await post(token, { ...validFields, steps: JSON.stringify([{ label: 'L', target_reps: 0 }]) });
    expect(res.status).toBe(400);
  });

  test('accepts a well-formed step, including one with no shot_type/target_reps at all', async () => {
    const { token } = makeAdmin();
    const res = await post(token, {
      ...validFields,
      steps: JSON.stringify([{ label: 'Rest between reps' }, { label: 'Forehand drill', shot_type: 'forehand', target_reps: 10 }]),
    });
    expect(res.status).toBe(200);
  });

  test('a rejected step-level error leaves the whole save uncommitted', async () => {
    const { token } = makeAdmin();
    const before = db.prepare('SELECT COUNT(*) AS n FROM drill_items').get().n;
    const res = await post(token, {
      ...validFields,
      steps: JSON.stringify([{ label: 'Good step' }, { label: '' }]),
    });
    expect(res.status).toBe(400);
    expect(db.prepare('SELECT COUNT(*) AS n FROM drill_items').get().n).toBe(before);
  });
});
