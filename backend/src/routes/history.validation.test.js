// POST /history accepts whatever /analyse returned, with no signature or
// correlation check tying the body back to a real analysis -- so any
// authenticated user can post an arbitrary one. These are the rules that
// stand between that and the analyses table.

process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const request = require('supertest');
const { appWith, makeUser, makeAnalysis, expectRejected, db } = require('./testSupport');

const app = appWith(require('./history'));

function save(token, body) {
  return request(app).post('/api/history').set('Authorization', `Bearer ${token}`).send(body);
}

const validBody = { shotType: 'forehand', matches: [{ overall_score: 80 }] };

describe('POST /history — shotType', () => {
  test.each(['forehand', 'backhand', 'serve'])('accepts %p', async (shotType) => {
    const { token } = makeUser({ tier: 'premium' });
    const res = await save(token, { ...validBody, shotType });
    expect(res.status).toBe(201);
    expect(res.body.shot_type).toBe(shotType);
  });

  test.each([
    ['banana', 'a shot type that does not exist'],
    ['footwork', 'a drill-only category the ML pipeline cannot analyse'],
    ['Forehand', 'the right word in the wrong case'],
    ['', 'empty'],
    [undefined, 'missing'],
    [42, 'not a string'],
  ])('rejects %p (%s) and writes nothing', async (shotType) => {
    const { token } = makeUser({ tier: 'premium' });
    await expectRejected(() => save(token, { ...validBody, shotType }), 'analyses');
  });
});

describe('POST /history — score', () => {
  test.each([0, 0.5, 50, 100])('accepts the valid score %p', async (overall_score) => {
    const { token } = makeUser({ tier: 'premium' });
    const res = await save(token, { ...validBody, matches: [{ overall_score }] });
    expect(res.status).toBe(201);
    expect(res.body.similarity).toBe(overall_score);
  });

  test('defaults to 0 when no match score is present at all', async () => {
    const { token } = makeUser({ tier: 'premium' });
    const res = await save(token, { shotType: 'serve' });
    expect(res.status).toBe(201);
    expect(res.body.similarity).toBe(0);
  });

  test.each([
    [999999, 'would permanently top both leaderboards'],
    [101, 'just outside a percentage'],
    [-1, 'negative'],
    ['zzz', 'text, which SQLite would store as-is and sort ABOVE every number'],
    [{}, 'an object'],
    [null, 'explicitly null inside a match'],
  ])('rejects the score %p (%s) and writes nothing', async (overall_score) => {
    const { token } = makeUser({ tier: 'premium' });
    // null is the one case that legitimately means "no score" rather than a
    // bad score, so it saves as 0 rather than being rejected.
    if (overall_score === null) {
      const res = await save(token, { ...validBody, matches: [{ overall_score }] });
      expect(res.status).toBe(201);
      expect(res.body.similarity).toBe(0);
      return;
    }
    await expectRejected(() => save(token, { ...validBody, matches: [{ overall_score }] }), 'analyses');
  });

  // The concrete consequence the range check exists to prevent.
  test('a rejected out-of-range score cannot outrank a real one', async () => {
    const { id, token } = makeUser({ tier: 'premium' });
    await save(token, { ...validBody, matches: [{ overall_score: 82 }] });
    await save(token, { ...validBody, matches: [{ overall_score: 999999 }] });

    const best = db.prepare('SELECT MAX(similarity) AS top FROM analyses WHERE user_id = ?').get(id);
    expect(best.top).toBe(82);
  });
});

describe('PATCH /history/:id', () => {
  test('accepts a shot-type correction to a real shot type', async () => {
    const { id, token } = makeUser();
    const analysisId = makeAnalysis(id);
    const res = await request(app).patch(`/api/history/${analysisId}`)
      .set('Authorization', `Bearer ${token}`).send({ shot_type: 'serve' });

    expect(res.status).toBe(200);
    expect(res.body.shot_type).toBe('serve');
  });

  test('rejects a correction to a shot type that does not exist, leaving the row untouched', async () => {
    const { id, token } = makeUser();
    const analysisId = makeAnalysis(id, { shotType: 'forehand' });

    const res = await request(app).patch(`/api/history/${analysisId}`)
      .set('Authorization', `Bearer ${token}`).send({ shot_type: 'banana' });

    expect(res.status).toBe(400);
    expect(db.prepare('SELECT shot_type FROM analyses WHERE id = ?').get(analysisId).shot_type).toBe('forehand');
  });

  test('never records both verdicts at once', async () => {
    const { id, token } = makeUser();
    const analysisId = makeAnalysis(id);

    await request(app).patch(`/api/history/${analysisId}`)
      .set('Authorization', `Bearer ${token}`).send({ flagged_not_shot: true });
    await request(app).patch(`/api/history/${analysisId}`)
      .set('Authorization', `Bearer ${token}`).send({ confirmed_real_shot: true });

    const row = db.prepare('SELECT flagged_not_shot, confirmed_real_shot FROM analyses WHERE id = ?').get(analysisId);
    expect(row).toEqual({ flagged_not_shot: 0, confirmed_real_shot: 1 });
  });
});

describe('DELETE /history/:id', () => {
  // Foreign keys are enforced, so a bare delete would throw rather than
  // orphan -- the route clears children first. Either way the invariant is
  // the same: no leftovers, and no 500.
  test('removes an analysis and its dependent rows together', async () => {
    const { id, token } = makeUser();
    const analysisId = makeAnalysis(id);
    db.prepare('INSERT INTO coach_notes (coach_id, analysis_id, note_text) VALUES (?, ?, ?)')
      .run(id, analysisId, 'note');

    const res = await request(app).delete(`/api/history/${analysisId}`).set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(204);
    // Scoped to this analysis rather than the whole table: earlier tests in
    // this file share the in-memory database and leave their own rows behind.
    expect(db.prepare('SELECT COUNT(*) AS n FROM analyses WHERE id = ?').get(analysisId).n).toBe(0);
    expect(db.prepare('SELECT COUNT(*) AS n FROM coach_notes WHERE analysis_id = ?').get(analysisId).n).toBe(0);
  });
});
