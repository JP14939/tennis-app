// POST /coach/notes bound noteText and timestampSec straight into the INSERT
// with only a truthy check between them and better-sqlite3 -- so a non-string
// note or a non-numeric timestamp threw inside the driver and surfaced as a
// 500. These tests assert a clean 400 specifically, not merely "not a 2xx".

process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const request = require('supertest');
const { appWith, makeUser, makeAnalysis, expectRejected, db } = require('./testSupport');

const app = appWith(require('./coach'));

// A coach may annotate a student's analysis once linked.
function coachAndStudent() {
  const coach = makeUser();
  const student = makeUser();
  db.prepare('INSERT INTO coach_links (coach_id, student_id) VALUES (?, ?)').run(coach.id, student.id);
  return { coach, student, analysisId: makeAnalysis(student.id) };
}

function addNote(token, body) {
  return request(app).post('/api/coach/notes').set('Authorization', `Bearer ${token}`).send(body);
}

describe('POST /coach/notes — noteText', () => {
  test('accepts a general note with no phase or timestamp', async () => {
    const { coach, analysisId } = coachAndStudent();
    const res = await addNote(coach.token, { analysisId, noteText: 'Watch your follow-through.' });
    expect(res.status).toBe(201);
    expect(res.body.note_text).toBe('Watch your follow-through.');
  });

  test.each([
    [{ text: 'nested' }, 'an object — this used to throw inside better-sqlite3 as a 500'],
    [['array'], 'an array'],
    [42, 'a number'],
    ['', 'empty'],
    ['   ', 'whitespace only'],
    ['x'.repeat(2001), 'over the length cap'],
    [undefined, 'missing'],
  ])('rejects %p (%s) with a 400 and writes no note', async (noteText) => {
    const { coach, analysisId } = coachAndStudent();
    await expectRejected(() => addNote(coach.token, { analysisId, noteText }), 'coach_notes');
  });
});

describe('POST /coach/notes — timestampSec', () => {
  test.each([0, 12.5, 3600])('accepts the video offset %p', async (timestampSec) => {
    const { coach, analysisId } = coachAndStudent();
    const res = await addNote(coach.token, { analysisId, noteText: 'Here.', timestampSec });
    expect(res.status).toBe(201);
    expect(res.body.timestamp_sec).toBe(timestampSec);
  });

  test.each([
    ['abc', 'not a number'],
    [-1, 'negative — a video offset cannot be'],
    [{}, 'an object'],
    [999999, 'longer than any real uploaded video'],
  ])('rejects %p (%s)', async (timestampSec) => {
    const { coach, analysisId } = coachAndStudent();
    await expectRejected(
      () => addNote(coach.token, { analysisId, noteText: 'Here.', timestampSec }),
      'coach_notes',
    );
  });

  // NaN has no JSON representation -- JSON.stringify turns it into null, so
  // it arrives as "no timestamp given" rather than as a bad number. Asserted
  // rather than assumed, since the predicate rejects NaN and it would be easy
  // to believe this path was covered when the value never reaches it.
  test('NaN arrives as null over JSON and is treated as no timestamp', async () => {
    const { coach, analysisId } = coachAndStudent();
    const res = await addNote(coach.token, { analysisId, noteText: 'Here.', timestampSec: Number.NaN });
    expect(res.status).toBe(201);
    expect(res.body.timestamp_sec).toBeNull();
  });
});

describe('POST /coach/notes — phaseKey and analysisId', () => {
  test.each(['backswing', 'contact', 'follow_through', 'body_rotation'])('accepts the phase %p', async (phaseKey) => {
    const { coach, analysisId } = coachAndStudent();
    const res = await addNote(coach.token, { analysisId, noteText: 'Note', phaseKey });
    expect(res.status).toBe(201);
  });

  test.each([
    ['followthrough', 'a near-miss of a real phase'],
    ['Contact', 'right phase, wrong case'],
    ['finish', 'a phase the results screen has no card for'],
  ])('rejects the phase %p (%s)', async (phaseKey) => {
    const { coach, analysisId } = coachAndStudent();
    await expectRejected(() => addNote(coach.token, { analysisId, noteText: 'Note', phaseKey }), 'coach_notes');
  });

  test.each([
    [{}, 'an object'],
    ['abc', 'not a number'],
    [0, 'not a real row id'],
    [undefined, 'missing'],
  ])('rejects the analysisId %p (%s)', async (analysisId) => {
    const { coach } = coachAndStudent();
    await expectRejected(() => addNote(coach.token, { analysisId, noteText: 'Note' }), 'coach_notes');
  });

  // The route's own comment and db.js's schema comment both call these two
  // mutually exclusive, but each was only validated independently -- a request
  // setting both stored a note pinned to a phase AND a timestamp at once,
  // which ResultsScreen and SyncCompareScreen each filter on and neither can
  // render coherently.
  test('rejects a note pinned to both a phase and a timestamp', async () => {
    const { coach, analysisId } = coachAndStudent();
    await expectRejected(
      () => addNote(coach.token, { analysisId, noteText: 'Note', phaseKey: 'contact', timestampSec: 5 }),
      'coach_notes',
    );
  });

  test('still accepts each of the two pinnings on its own', async () => {
    const { coach, analysisId } = coachAndStudent();
    expect((await addNote(coach.token, { analysisId, noteText: 'A', phaseKey: 'contact' })).status).toBe(201);
    expect((await addNote(coach.token, { analysisId, noteText: 'B', timestampSec: 5 })).status).toBe(201);
  });

  test('still refuses to annotate an analysis you are not the coach for', async () => {
    const { coach } = coachAndStudent();
    const stranger = makeUser();
    await expectRejected(
      () => addNote(coach.token, { analysisId: makeAnalysis(stranger.id), noteText: 'Note' }),
      'coach_notes',
      { status: 403 },
    );
  });
});

describe('GET /coach/notes', () => {
  test('rejects an analysisId that Number() would silently accept', async () => {
    const { coach } = coachAndStudent();
    for (const analysisId of ['1.5', '1e3', 'abc', '']) {
      const res = await request(app).get(`/api/coach/notes?analysisId=${analysisId}`)
        .set('Authorization', `Bearer ${coach.token}`);
      expect({ analysisId, status: res.status }).toEqual({ analysisId, status: 400 });
    }
  });

  test('returns the notes on an analysis to both the coach and the student', async () => {
    const { coach, student, analysisId } = coachAndStudent();
    await addNote(coach.token, { analysisId, noteText: 'Keep your head still.' });

    for (const token of [coach.token, student.token]) {
      const res = await request(app).get(`/api/coach/notes?analysisId=${analysisId}`)
        .set('Authorization', `Bearer ${token}`);
      expect(res.status).toBe(200);
      expect(res.body.notes).toHaveLength(1);
    }
  });
});
