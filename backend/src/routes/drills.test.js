// Coverage for the Drills & Lessons user-facing listing/detail/practice
// endpoints -- the newest routes in the app and, until now, the only ones
// with no regression test. Same DB_PATH=':memory:' + supertest pattern as
// history.test.js/highlights.test.js.
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

function makeUser(email, tier = 'free') {
  const id = db.prepare('INSERT INTO users (email, password_hash, name, tier) VALUES (?, ?, ?, ?)')
    .run(email, 'x', 'Test User', tier).lastInsertRowid;
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

function makeDrillItem({ kind = 'drill', isPremium = 0 } = {}) {
  return db.prepare(`
    INSERT INTO drill_items (kind, shot_type, title, explanation, emphasis, is_premium)
    VALUES (?, 'forehand', 'Test title', 'Test explanation', 'Test emphasis', ?)
  `).run(kind, isPremium).lastInsertRowid;
}

function makeStep(drillItemId, order = 0) {
  return db.prepare(`
    INSERT INTO drill_routine_steps (drill_item_id, step_order, label, shot_type, target_reps)
    VALUES (?, ?, 'Step label', 'forehand', 10)
  `).run(drillItemId, order).lastInsertRowid;
}

describe('GET /drills', () => {
  test('a free drill is fully visible to an anonymous request', async () => {
    makeDrillItem({ kind: 'drill', isPremium: 0 });
    const res = await request(app).get('/api/drills?kind=drill');
    expect(res.status).toBe(200);
    expect(res.body.items).toHaveLength(1);
    expect(res.body.items[0].locked).toBe(false);
    expect(res.body.items[0].explanation).toBe('Test explanation');
  });

  test('a premium lesson lists as locked with content stripped for a free user', async () => {
    makeDrillItem({ kind: 'lesson', isPremium: 1 });
    const { token } = makeUser('free@test.com', 'free');
    const res = await request(app).get('/api/drills?kind=lesson').set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
    expect(res.body.items[0].locked).toBe(true);
    expect(res.body.items[0].explanation).toBeNull();
    expect(res.body.items[0].emphasis).toBeNull();
    expect(res.body.items[0].video_url).toBeNull();
  });

  test('a premium lesson lists as fully unlocked for a premium user', async () => {
    makeDrillItem({ kind: 'lesson', isPremium: 1 });
    const { token } = makeUser('premium@test.com', 'premium');
    const res = await request(app).get('/api/drills?kind=lesson').set('Authorization', `Bearer ${token}`);
    expect(res.body.items[0].locked).toBe(false);
    expect(res.body.items[0].explanation).toBe('Test explanation');
  });

  test('rejects an invalid kind value', async () => {
    const res = await request(app).get('/api/drills?kind=bogus');
    expect(res.status).toBe(400);
  });

  test('rejects a repeated shot_type query param instead of crashing', async () => {
    // qs parses ?shot_type=a&shot_type=b into an array -- binding that
    // straight into the '?' placeholder used to throw a RangeError deep in
    // better-sqlite3 ("Too many parameter values were provided"), surfacing
    // as a bare 500 instead of a validation error.
    const res = await request(app).get('/api/drills?shot_type=forehand&shot_type=backhand');
    expect(res.status).toBe(400);
  });

  test('archived items never appear', async () => {
    // The in-memory DB is shared across every test in this file (no reset
    // between tests), so assert this specific item is absent rather than
    // asserting the whole list is empty -- other tests' rows are still there.
    const id = makeDrillItem();
    db.prepare('UPDATE drill_items SET archived = 1 WHERE id = ?').run(id);
    const res = await request(app).get('/api/drills?kind=drill');
    expect(res.body.items.some((item) => item.id === id)).toBe(false);
  });
});

describe('GET /drills/:id', () => {
  test('404s for a nonexistent item', async () => {
    const res = await request(app).get('/api/drills/999999');
    expect(res.status).toBe(404);
  });

  test('403s with PREMIUM_REQUIRED for a locked lesson, anonymous', async () => {
    const id = makeDrillItem({ kind: 'lesson', isPremium: 1 });
    const res = await request(app).get(`/api/drills/${id}`);
    expect(res.status).toBe(403);
    expect(res.body.code).toBe('PREMIUM_REQUIRED');
  });

  test('403s for a locked lesson even when logged in as free tier', async () => {
    const id = makeDrillItem({ kind: 'lesson', isPremium: 1 });
    const { token } = makeUser('free2@test.com', 'free');
    const res = await request(app).get(`/api/drills/${id}`).set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(403);
  });

  test('returns full detail with steps for a premium user', async () => {
    const id = makeDrillItem({ kind: 'lesson', isPremium: 1 });
    makeStep(id, 0);
    makeStep(id, 1);
    const { token } = makeUser('premium2@test.com', 'premium');
    const res = await request(app).get(`/api/drills/${id}`).set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
    expect(res.body.steps).toHaveLength(2);
    expect(res.body.steps[0].attempt_count).toBe(0);
  });
});

describe('POST /drills/:stepId/practice', () => {
  test('requires auth', async () => {
    const id = makeDrillItem({ kind: 'lesson' });
    const stepId = makeStep(id);
    const res = await request(app).post(`/api/drills/${stepId}/practice`).send({});
    expect(res.status).toBe(401);
  });

  test('404s for a nonexistent step', async () => {
    const { token } = makeUser('practice1@test.com');
    const res = await request(app)
      .post('/api/drills/999999/practice')
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(404);
  });

  test('403s when the analysisId does not belong to the caller', async () => {
    const owner = makeUser('owner@test.com');
    const other = makeUser('other@test.com');
    const analysisId = db.prepare(
      "INSERT INTO analyses (user_id, shot_type, similarity, result_json) VALUES (?, 'forehand', 80, '{}')"
    ).run(owner.id).lastInsertRowid;

    const drillId = makeDrillItem({ kind: 'lesson' });
    const stepId = makeStep(drillId);

    const res = await request(app)
      .post(`/api/drills/${stepId}/practice`)
      .set('Authorization', `Bearer ${other.token}`)
      .send({ analysisId });
    expect(res.status).toBe(403);
  });

  test('links a valid analysis and increments attempt_count', async () => {
    const { id: userId, token } = makeUser('practice2@test.com');
    const analysisId = db.prepare(
      "INSERT INTO analyses (user_id, shot_type, similarity, result_json) VALUES (?, 'forehand', 80, '{}')"
    ).run(userId).lastInsertRowid;

    const drillId = makeDrillItem({ kind: 'lesson' });
    const stepId = makeStep(drillId);

    const res = await request(app)
      .post(`/api/drills/${stepId}/practice`)
      .set('Authorization', `Bearer ${token}`)
      .send({ analysisId });
    expect(res.status).toBe(200);
    expect(res.body.attempt_count).toBe(1);

    const again = await request(app)
      .post(`/api/drills/${stepId}/practice`)
      .set('Authorization', `Bearer ${token}`)
      .send({ analysisId });
    expect(again.body.attempt_count).toBe(2);
  });

  test('works with no analysisId at all', async () => {
    const { token } = makeUser('practice3@test.com');
    const drillId = makeDrillItem({ kind: 'lesson' });
    const stepId = makeStep(drillId);
    const res = await request(app)
      .post(`/api/drills/${stepId}/practice`)
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(200);
    expect(res.body.attempt_count).toBe(1);
  });

  test('403s a free user recording an attempt against a step from a locked premium lesson', async () => {
    // GET /drills/:id 403s for a locked lesson and strips its steps, but this
    // endpoint used to look up the step directly by id with no check against
    // its parent drill_item's premium lock -- a free user who knows/enumerates
    // a stepId (sequential auto-increment) could bypass the paywall's usage
    // gate even though they can never view the step's real content.
    const { token } = makeUser('practice-locked@test.com', 'free');
    const drillId = makeDrillItem({ kind: 'lesson', isPremium: 1 });
    const stepId = makeStep(drillId);
    const res = await request(app)
      .post(`/api/drills/${stepId}/practice`)
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(403);
    expect(res.body.code).toBe('PREMIUM_REQUIRED');
  });

  test('allows a premium user to record an attempt against a locked-for-others lesson', async () => {
    const { token } = makeUser('practice-premium@test.com', 'premium');
    const drillId = makeDrillItem({ kind: 'lesson', isPremium: 1 });
    const stepId = makeStep(drillId);
    const res = await request(app)
      .post(`/api/drills/${stepId}/practice`)
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(200);
    expect(res.body.attempt_count).toBe(1);
  });
});
