// Regression test: POST /highlights/jobs/:id/reel used to only require auth,
// not premium, unlike its sibling /highlights/upload -- a non-premium user
// (or one who downgraded after a job was created) could still trigger
// resource-intensive reel-stitching. requirePremium must reject BEFORE the
// handler ever looks up the job/spawns anything, so this is testable without
// mocking the Python subprocess.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const highlightsRouter = require('./highlights');

const app = express();
app.use(express.json());
app.use('/api', highlightsRouter);

function makeUser(email, tier = 'free') {
  const id = db.prepare('INSERT INTO users (email, password_hash, name, tier) VALUES (?, ?, ?, ?)')
    .run(email, 'x', 'Test User', tier).lastInsertRowid;
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

describe('POST /highlights/jobs/:id/reel premium gate', () => {
  test('a free-tier user is rejected with PREMIUM_REQUIRED before any job lookup', async () => {
    const { token } = makeUser('reel_free@test.com', 'free');
    const res = await request(app)
      .post('/api/highlights/jobs/999999/reel')
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(403);
    expect(res.body.code).toBe('PREMIUM_REQUIRED');
  });

  test('a premium user with a nonexistent job gets a 404 (passes the gate, fails later)', async () => {
    const { token } = makeUser('reel_premium@test.com', 'premium');
    const res = await request(app)
      .post('/api/highlights/jobs/999999/reel')
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(404);
  });

  test('rejects a non-integer rallyIds element with 400 instead of a 500 crash', async () => {
    // Binding a non-integer element (e.g. an object) straight into the SQL
    // '?' placeholders used to throw a RangeError deep in better-sqlite3.
    const { id: userId, token } = makeUser('reel_badids@test.com', 'premium');
    const jobId = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, 'x', 'done')`)
      .run(userId).lastInsertRowid;
    const res = await request(app)
      .post(`/api/highlights/jobs/${jobId}/reel`)
      .set('Authorization', `Bearer ${token}`)
      .send({ rallyIds: [1, {}, 3] });
    expect(res.status).toBe(400);
  });

  // Regression test: an explicit `rallyIds: []` (every rally deselected in
  // the picker UI) used to fall through to the `else` branch and silently
  // build a reel from the top-3-by-duration default instead -- the caller's
  // explicit "none of these" was overridden rather than honored or rejected.
  test('an explicit empty rallyIds array is rejected with 400, not silently defaulted to top-3', async () => {
    const { id: userId, token } = makeUser('reel_emptyids@test.com', 'premium');
    const jobId = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, 'x', 'done')`)
      .run(userId).lastInsertRowid;
    db.prepare(`
      INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
      VALUES (?, ?, 'clip.mp4', 0, 5, 5, 1)
    `).run(jobId, userId);

    const res = await request(app)
      .post(`/api/highlights/jobs/${jobId}/reel`)
      .set('Authorization', `Bearer ${token}`)
      .send({ rallyIds: [] });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/rallyIds cannot be empty/);
  });

  test('omitting rallyIds entirely still uses the top-N default', async () => {
    const { id: userId, token } = makeUser('reel_omitids@test.com', 'premium');
    const jobId = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, 'x', 'done')`)
      .run(userId).lastInsertRowid;
    db.prepare(`
      INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
      VALUES (?, ?, 'clip.mp4', 0, 5, 5, 1)
    `).run(jobId, userId);

    const res = await request(app)
      .post(`/api/highlights/jobs/${jobId}/reel`)
      .set('Authorization', `Bearer ${token}`)
      .send({});
    expect(res.status).toBe(202);
  });
});

describe('GET /highlights/jobs/:id rally shots', () => {
  test('each rally carries its persisted shots, ordered by shot_index; a rally with none gets shots: []', async () => {
    const { id: userId, token } = makeUser('shots_get@test.com', 'free');
    const jobId = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, 'x', 'done')`)
      .run(userId).lastInsertRowid;
    const withShotsId = db.prepare(`
      INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
      VALUES (?, ?, 'clip_a.mp4', 0, 10, 10, 2)
    `).run(jobId, userId).lastInsertRowid;
    const noShotsId = db.prepare(`
      INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
      VALUES (?, ?, 'clip_b.mp4', 20, 25, 5, 1)
    `).run(jobId, userId).lastInsertRowid;
    // Inserted out of order to confirm the query orders by shot_index itself.
    db.prepare(`INSERT INTO rally_shots (rally_clip_id, shot_index, shot_type, contact_time_sec) VALUES (?, 1, 'backhand', 4.5)`).run(withShotsId);
    db.prepare(`INSERT INTO rally_shots (rally_clip_id, shot_index, shot_type, contact_time_sec) VALUES (?, 0, 'forehand', 1.2)`).run(withShotsId);

    const res = await request(app)
      .get(`/api/highlights/jobs/${jobId}`)
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
    const withShots = res.body.rallies.find((r) => r.id === withShotsId);
    const noShots = res.body.rallies.find((r) => r.id === noShotsId);
    expect(withShots.shots).toEqual([
      { shot_index: 0, shot_type: 'forehand', contact_time_sec: 1.2 },
      { shot_index: 1, shot_type: 'backhand', contact_time_sec: 4.5 },
    ]);
    expect(noShots.shots).toEqual([]);
  });
});

describe('POST /highlights/rallies/:id/shots/:shotIndex/analyze', () => {
  test('rejects a non-integer shotIndex with 400 before any lookup', async () => {
    const { token } = makeUser('shots_badindex@test.com', 'free');
    const res = await request(app)
      .post('/api/highlights/rallies/1/shots/not-a-number/analyze')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(400);
  });

  test('a nonexistent rally clip is a 404', async () => {
    const { token } = makeUser('shots_noclip@test.com', 'free');
    const res = await request(app)
      .post('/api/highlights/rallies/999999/shots/0/analyze')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(404);
  });

  test("another user's rally clip is a 404, not exposed via ownership leak", async () => {
    const { id: ownerId } = makeUser('shots_owner@test.com', 'free');
    const { token: otherToken } = makeUser('shots_other@test.com', 'free');
    const jobId = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, 'x', 'done')`)
      .run(ownerId).lastInsertRowid;
    const clipId = db.prepare(`
      INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
      VALUES (?, ?, 'clip.mp4', 0, 5, 5, 1)
    `).run(jobId, ownerId).lastInsertRowid;
    db.prepare(`INSERT INTO rally_shots (rally_clip_id, shot_index, shot_type, contact_time_sec) VALUES (?, 0, 'forehand', 1.0)`).run(clipId);

    const res = await request(app)
      .post(`/api/highlights/rallies/${clipId}/shots/0/analyze`)
      .set('Authorization', `Bearer ${otherToken}`);
    expect(res.status).toBe(404);
  });

  test('a rally clip with no shot at that index is a 404', async () => {
    const { id: userId, token } = makeUser('shots_missingindex@test.com', 'free');
    const jobId = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, 'x', 'done')`)
      .run(userId).lastInsertRowid;
    const clipId = db.prepare(`
      INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
      VALUES (?, ?, 'clip.mp4', 0, 5, 5, 0)
    `).run(jobId, userId).lastInsertRowid;

    const res = await request(app)
      .post(`/api/highlights/rallies/${clipId}/shots/0/analyze`)
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(404);
  });
});

describe('PATCH /highlights/rallies/:id field validation', () => {
  test('rejects a non-string outcome_tag with 400 instead of a 500 crash', async () => {
    const { id: userId, token } = makeUser('rally_badtag@test.com', 'free');
    const jobId = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, 'x', 'done')`)
      .run(userId).lastInsertRowid;
    const clipId = db.prepare(`
      INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count)
      VALUES (?, ?, 'clip.mp4', 0, 1, 1, 1)
    `).run(jobId, userId).lastInsertRowid;

    const res = await request(app)
      .patch(`/api/highlights/rallies/${clipId}`)
      .set('Authorization', `Bearer ${token}`)
      .send({ outcome_tag: { bogus: true } });
    expect(res.status).toBe(400);
  });

  // Regression test: `?? clip.boundary_note` used to treat an OMITTED
  // boundary_note key the same as "leave it unchanged" -- there was no way
  // to actually clear a previously-set note (an explicit '' is what the
  // frontend now sends when every box gets unchecked). Also confirms an
  // omitted key really does leave an existing note untouched, so the fix
  // doesn't regress that legitimate case.
  test('an explicit empty boundary_note clears a previously-set note', async () => {
    const { id: userId, token } = makeUser('rally_clearnote@test.com', 'free');
    const jobId = db.prepare(`INSERT INTO highlight_jobs (user_id, video_path, status) VALUES (?, 'x', 'done')`)
      .run(userId).lastInsertRowid;
    const clipId = db.prepare(`
      INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count, boundary_note)
      VALUES (?, ?, 'clip.mp4', 0, 1, 1, 1, 'started_too_late')
    `).run(jobId, userId).lastInsertRowid;

    const cleared = await request(app)
      .patch(`/api/highlights/rallies/${clipId}`)
      .set('Authorization', `Bearer ${token}`)
      .send({ outcome_tag: 'winner_this_side', boundary_note: '' });
    expect(cleared.status).toBe(200);
    expect(cleared.body.boundary_note).toBeFalsy();

    const untouched = await request(app)
      .patch(`/api/highlights/rallies/${clipId}`)
      .set('Authorization', `Bearer ${token}`)
      .send({ outcome_tag: 'winner_other_side' });
    expect(untouched.status).toBe(200);
    expect(untouched.body.boundary_note).toBeFalsy();
  });
});
