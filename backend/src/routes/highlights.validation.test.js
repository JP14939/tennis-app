// PATCH /highlights/rallies/:id records a human review verdict, and both of
// its fields leave this app: outcome_tag drives profile.js's Player Type, and
// boundary_note is training data tune_rally_gap.py reads to tune the rally
// detector. Neither had any validation at all before.

process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const request = require('supertest');
const { appWith, makeUser, db } = require('./testSupport');

const app = appWith(require('./highlights'));

function makeClip(userId) {
  const jobId = db.prepare('INSERT INTO highlight_jobs (user_id, video_path) VALUES (?, ?)')
    .run(userId, '/tmp/v.mp4').lastInsertRowid;
  return db.prepare(
    `INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec)
     VALUES (?, ?, ?, 10, 25, 15)`
  ).run(jobId, userId, '/tmp/c.mp4').lastInsertRowid;
}

function review(token, clipId, body) {
  return request(app).patch(`/api/highlights/rallies/${clipId}`)
    .set('Authorization', `Bearer ${token}`).send(body);
}

function storedClip(clipId) {
  return db.prepare('SELECT outcome_tag, boundary_note FROM rally_clips WHERE id = ?').get(clipId);
}

describe('outcome_tag', () => {
  test.each(['ace', 'winner_this_side', 'winner_other_side', 'skip'])('accepts %p', async (outcome_tag) => {
    const { id, token } = makeUser();
    const clipId = makeClip(id);

    const res = await review(token, clipId, { outcome_tag });
    expect(res.status).toBe(200);
    expect(storedClip(clipId).outcome_tag).toBe(outcome_tag);
  });

  test.each([
    ['winner', 'the tag profile.js used to filter on but the app never writes'],
    ['error', 'the other tag profile.js used to filter on'],
    ['Ace', 'right value, wrong case'],
    ['', 'empty'],
    [7, 'not a string'],
  ])('rejects %p (%s) and leaves the clip untagged', async (outcome_tag) => {
    const { id, token } = makeUser();
    const clipId = makeClip(id);

    const res = await review(token, clipId, { outcome_tag });
    expect(res.status).toBe(400);
    expect(storedClip(clipId).outcome_tag).toBeNull();
  });

  test('omitting it leaves the existing tag alone rather than clearing it', async () => {
    const { id, token } = makeUser();
    const clipId = makeClip(id);

    await review(token, clipId, { outcome_tag: 'ace' });
    const res = await review(token, clipId, { archived: true });

    expect(res.status).toBe(200);
    expect(storedClip(clipId).outcome_tag).toBe('ace');
  });
});

describe('boundary_note', () => {
  test.each([
    ['ok', 'a single whole-clip verdict'],
    ['should_split', 'the other whole-clip verdict'],
    ['cut_off_early', 'one independent problem'],
    ['started_too_late,cut_off_early', 'both independent problems at once'],
    ['cut_off_early,started_too_late', 'the same pair in the other order'],
  ])('accepts %p (%s)', async (boundary_note) => {
    const { id, token } = makeUser();
    const clipId = makeClip(id);

    const res = await review(token, clipId, { boundary_note });
    expect(res.status).toBe(200);
    expect(storedClip(clipId).boundary_note).toBe(boundary_note);
  });

  test.each([
    ['ok,should_split', 'two contradictory verdicts on one clip'],
    ['ok,cut_off_early', "'ok' alongside a reported problem"],
    ['should_split,cut_off_early', "'should_split' must stand alone"],
    ['cut_off_early,cut_off_early', 'the same problem twice'],
    ['perfect', "the button's label instead of its value"],
    ['cut_off_early, started_too_late', 'a space after the comma'],
    [['cut_off_early'], 'an array instead of the comma-joined string'],
  ])('rejects %p (%s) so the training signal stays clean', async (boundary_note) => {
    const { id, token } = makeUser();
    const clipId = makeClip(id);

    const res = await review(token, clipId, { boundary_note });
    expect(res.status).toBe(400);
    expect(storedClip(clipId).boundary_note).toBeNull();
  });
});

describe('archived', () => {
  function storedArchived(clipId) {
    return db.prepare('SELECT archived FROM rally_clips WHERE id = ?').get(clipId).archived;
  }

  test.each([true, false])('accepts %p', async (archived) => {
    const { id, token } = makeUser();
    const clipId = makeClip(id);

    const res = await review(token, clipId, { archived });
    expect(res.status).toBe(200);
    expect(storedArchived(clipId)).toBe(archived ? 1 : 0);
  });

  // Was used raw (`archived ? 1 : 0`) with no type check -- any truthy
  // non-boolean coerced to archived=1 (or, for a falsy-but-wrong type,
  // silently to 0) with no 400 to flag the caller's mistake.
  test.each([
    ['true', 'the string "true" instead of the boolean'],
    ['false', 'the string "false" -- truthy, so it would have wrongly archived'],
    [1, 'a number instead of a boolean'],
    [0, 'zero instead of the boolean false'],
  ])('rejects %p (%s) and leaves archived unchanged', async (archived) => {
    const { id, token } = makeUser();
    const clipId = makeClip(id);

    const res = await review(token, clipId, { archived });
    expect(res.status).toBe(400);
    expect(storedArchived(clipId)).toBe(0);
  });
});

describe('a rejected review never partially applies', () => {
  test('a valid outcome_tag alongside a malformed boundary_note saves neither', async () => {
    const { id, token } = makeUser();
    const clipId = makeClip(id);

    const res = await review(token, clipId, { outcome_tag: 'ace', boundary_note: 'ok,should_split' });

    expect(res.status).toBe(400);
    expect(storedClip(clipId)).toEqual({ outcome_tag: null, boundary_note: null });
  });

  // Validation runs before the ownership lookup, so a bad body on someone
  // else's clip is a 400 rather than a 404 -- either way nothing is written,
  // and no information about the other user's clip leaks.
  test("another user's clip is never modified", async () => {
    const owner = makeUser();
    const stranger = makeUser();
    const clipId = makeClip(owner.id);

    const res = await review(stranger.token, clipId, { outcome_tag: 'ace' });

    expect(res.status).toBe(404);
    expect(storedClip(clipId).outcome_tag).toBeNull();
  });
});

describe('POST /push-token', () => {
  test('accepts a normal Expo push token', async () => {
    const { token } = makeUser();
    const res = await request(app).post('/api/push-token')
      .set('Authorization', `Bearer ${token}`).send({ token: 'ExponentPushToken[abc123]' });
    expect(res.status).toBe(204);
  });

  test.each([
    ['x'.repeat(201), 'longer than any real token'],
    ['', 'empty'],
    [12345, 'not a string'],
    [undefined, 'missing'],
  ])('rejects %p (%s)', async (pushToken) => {
    const { token } = makeUser();
    const before = db.prepare('SELECT COUNT(*) AS n FROM push_tokens').get().n;

    const res = await request(app).post('/api/push-token')
      .set('Authorization', `Bearer ${token}`).send({ token: pushToken });

    expect(res.status).toBe(400);
    expect(db.prepare('SELECT COUNT(*) AS n FROM push_tokens').get().n).toBe(before);
  });
});
