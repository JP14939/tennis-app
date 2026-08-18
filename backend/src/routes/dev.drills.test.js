// Coverage for the Dev Page's Drills & Lessons editor CRUD -- previously
// untested. Includes a regression test for a real bug found in this
// session's DB audit: editing a lesson used to wholesale-delete and
// reinsert its routine steps (new ids every save), silently orphaning any
// drill_practice_attempts.step_id pointing at the old ids since SQLite FK
// constraints aren't enforced in this app. Steps are now reconciled by id
// instead (see routes/dev.js's POST /dev/drills).
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';
process.env.ADMIN_EMAILS = 'admin@test.com';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const devRouter = require('./dev');
const drillsRouter = require('./drills');

const app = express();
app.use(express.json());
app.use('/api', devRouter);
app.use('/api', drillsRouter);

function makeUser(email) {
  const id = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(email, 'x', 'Test User').lastInsertRowid;
  const token = jwt.sign({ id, email }, process.env.JWT_SECRET);
  return { id, token };
}

// The in-memory DB is shared across every test in this file (no reset
// between tests) -- create each fixed-email user exactly once and reuse it,
// rather than re-inserting the same email per test (which would violate
// users.email's UNIQUE constraint on the second call).
const adminUser = makeUser('admin@test.com');
const admin = () => adminUser;
const nonAdmin = () => makeUser('notadmin@test.com');

describe('requireAdmin gate', () => {
  test('a non-admin authenticated user gets 403 on every /dev/drills route', async () => {
    const { token } = nonAdmin();
    const get = await request(app).get('/api/dev/drills').set('Authorization', `Bearer ${token}`);
    expect(get.status).toBe(403);

    const post = await request(app)
      .post('/api/dev/drills')
      .set('Authorization', `Bearer ${token}`)
      .field('kind', 'drill').field('shot_type', 'forehand').field('title', 't').field('explanation', 'e');
    expect(post.status).toBe(403);

    const del = await request(app).delete('/api/dev/drills/1').set('Authorization', `Bearer ${token}`);
    expect(del.status).toBe(403);
  });
});

describe('POST /dev/drills create/update', () => {
  test('creates a drill with no steps', async () => {
    const { token } = admin();
    const res = await request(app)
      .post('/api/dev/drills')
      .set('Authorization', `Bearer ${token}`)
      .field('kind', 'drill').field('shot_type', 'forehand')
      .field('title', 'My drill').field('explanation', 'Explanation text')
      .field('steps', '[]');
    expect(res.status).toBe(200);
    expect(res.body.id).toBeDefined();
  });

  test('rejects missing required fields', async () => {
    const { token } = admin();
    const res = await request(app)
      .post('/api/dev/drills')
      .set('Authorization', `Bearer ${token}`)
      .field('kind', 'drill');
    expect(res.status).toBe(400);
  });

  test('editing a lesson preserves existing step ids and practice-attempt history', async () => {
    const { token } = admin();

    // Create a lesson with 2 steps.
    const create = await request(app)
      .post('/api/dev/drills')
      .set('Authorization', `Bearer ${token}`)
      .field('kind', 'lesson').field('shot_type', 'forehand')
      .field('title', 'Original title').field('explanation', 'Explanation')
      .field('steps', JSON.stringify([
        { label: 'Step A', shot_type: 'forehand', target_reps: 10 },
        { label: 'Step B', shot_type: 'forehand', target_reps: 10 },
      ]));
    const itemId = create.body.id;

    const before = await request(app).get('/api/dev/drills').set('Authorization', `Bearer ${token}`);
    const beforeSteps = before.body.items.find((i) => i.id === itemId).steps;
    expect(beforeSteps).toHaveLength(2);
    const stepAId = beforeSteps.find((s) => s.label === 'Step A').id;

    // Log a practice attempt against Step A.
    const practicingUserId = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
      .run('practicer@test.com', 'x', 'Practicer').lastInsertRowid;
    db.prepare('INSERT INTO drill_practice_attempts (user_id, step_id) VALUES (?, ?)').run(practicingUserId, stepAId);

    // Edit the lesson -- change only the title, resubmit both steps with
    // their existing ids (as the real editor screen now does).
    const edit = await request(app)
      .post('/api/dev/drills')
      .set('Authorization', `Bearer ${token}`)
      .field('id', String(itemId))
      .field('kind', 'lesson').field('shot_type', 'forehand')
      .field('title', 'Edited title').field('explanation', 'Explanation')
      .field('steps', JSON.stringify([
        { id: stepAId, label: 'Step A', shot_type: 'forehand', target_reps: 10 },
        { id: beforeSteps.find((s) => s.label === 'Step B').id, label: 'Step B renamed', shot_type: 'forehand', target_reps: 12 },
      ]));
    expect(edit.status).toBe(200);

    const after = await request(app).get('/api/dev/drills').set('Authorization', `Bearer ${token}`);
    const afterItem = after.body.items.find((i) => i.id === itemId);
    expect(afterItem.title).toBe('Edited title');
    const afterStepA = afterItem.steps.find((s) => s.label === 'Step A');
    expect(afterStepA.id).toBe(stepAId); // same id preserved, not a new row

    // The practice attempt logged against the old step id must still exist
    // and still resolve to this step -- this is the actual regression check.
    const survivingAttempt = db.prepare('SELECT * FROM drill_practice_attempts WHERE step_id = ? AND user_id = ?')
      .get(stepAId, practicingUserId);
    expect(survivingAttempt).toBeDefined();
  });

  test('a step omitted from an edit is actually removed', async () => {
    const { token } = admin();
    const create = await request(app)
      .post('/api/dev/drills')
      .set('Authorization', `Bearer ${token}`)
      .field('kind', 'lesson').field('shot_type', 'forehand')
      .field('title', 'T').field('explanation', 'E')
      .field('steps', JSON.stringify([
        { label: 'Keep me', shot_type: 'forehand', target_reps: 10 },
        { label: 'Drop me', shot_type: 'forehand', target_reps: 10 },
      ]));
    const itemId = create.body.id;
    const before = await request(app).get('/api/dev/drills').set('Authorization', `Bearer ${token}`);
    const keepStep = before.body.items.find((i) => i.id === itemId).steps.find((s) => s.label === 'Keep me');

    await request(app)
      .post('/api/dev/drills')
      .set('Authorization', `Bearer ${token}`)
      .field('id', String(itemId))
      .field('kind', 'lesson').field('shot_type', 'forehand')
      .field('title', 'T').field('explanation', 'E')
      .field('steps', JSON.stringify([{ id: keepStep.id, label: 'Keep me', shot_type: 'forehand', target_reps: 10 }]));

    const after = await request(app).get('/api/dev/drills').set('Authorization', `Bearer ${token}`);
    const afterSteps = after.body.items.find((i) => i.id === itemId).steps;
    expect(afterSteps).toHaveLength(1);
    expect(afterSteps[0].label).toBe('Keep me');
  });
});

describe('DELETE /dev/drills/:id', () => {
  test('archives instead of hard-deleting, and archived items are hidden from GET /drills but visible in GET /dev/drills', async () => {
    const { token } = admin();
    const create = await request(app)
      .post('/api/dev/drills')
      .set('Authorization', `Bearer ${token}`)
      .field('kind', 'drill').field('shot_type', 'forehand')
      .field('title', 'To archive').field('explanation', 'E').field('steps', '[]');
    const itemId = create.body.id;

    const del = await request(app).delete(`/api/dev/drills/${itemId}`).set('Authorization', `Bearer ${token}`);
    expect(del.status).toBe(200);

    const row = db.prepare('SELECT archived FROM drill_items WHERE id = ?').get(itemId);
    expect(row.archived).toBe(1);

    const devList = await request(app).get('/api/dev/drills').set('Authorization', `Bearer ${token}`);
    expect(devList.body.items.some((i) => i.id === itemId)).toBe(true);

    const publicList = await request(app).get('/api/drills?kind=drill');
    expect(publicList.body.items.some((i) => i.id === itemId)).toBe(false);
  });

  test('404s for a nonexistent id', async () => {
    const { token } = admin();
    const res = await request(app).delete('/api/dev/drills/999999').set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(404);
  });
});
