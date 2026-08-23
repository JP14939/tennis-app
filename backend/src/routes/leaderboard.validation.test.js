// Curated celebrity scores are merged into the SAME sorted list as real user
// scores by GET /leaderboard/worldwide, so they obey the same 0-100 rule --
// admin-only is not a reason to skip the range check, it just means the bad
// value would come from a typo rather than an attacker.

process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';
process.env.ADMIN_EMAILS = 'admin@test.com';

const request = require('supertest');
const jwt = require('jsonwebtoken');
const { appWith, makeUser, makeAnalysis, expectRejected } = require('./testSupport');

const app = appWith(require('./leaderboard'));

// requireAdmin reads the email off the JWT claim, not from the users row, so
// the admin token just needs to carry an allowlisted email. The row itself
// keeps its generated unique email -- it only has to exist, because
// celebrity_scores.added_by is a foreign key to it.
function makeAdmin() {
  const user = makeUser();
  return { id: user.id, token: jwt.sign({ id: user.id, email: 'admin@test.com' }, process.env.JWT_SECRET) };
}

function addCelebrity(token, body) {
  return request(app).post('/api/leaderboard/celebrities')
    .set('Authorization', `Bearer ${token}`).send(body);
}

const validCelebrity = { name: 'Roger Federer', shotType: 'forehand', score: 97 };

describe('POST /leaderboard/celebrities', () => {
  test('accepts a well-formed entry', async () => {
    const admin = makeAdmin();
    const res = await addCelebrity(admin.token, validCelebrity);
    expect(res.status).toBe(201);
    expect(res.body.celebrity).toMatchObject({ name: 'Roger Federer', score: 97 });
  });

  test.each([0, 100])('accepts the boundary score %p', async (score) => {
    const admin = makeAdmin();
    expect((await addCelebrity(admin.token, { ...validCelebrity, score })).status).toBe(201);
  });

  test.each([
    [101, 'just outside a percentage'],
    [150, 'well outside'],
    [-1, 'negative'],
    ['97', 'a numeric-looking string SQLite would store as text'],
    [undefined, 'missing'],
  ])('rejects the score %p (%s) and adds no entry', async (score) => {
    const admin = makeAdmin();
    await expectRejected(() => addCelebrity(admin.token, { ...validCelebrity, score }), 'celebrity_scores');
  });

  test.each([
    ['', 'empty'],
    ['x'.repeat(81), 'over the length cap'],
    [{ first: 'Roger' }, 'not a string'],
  ])('rejects the name %p (%s)', async (name) => {
    const admin = makeAdmin();
    await expectRejected(() => addCelebrity(admin.token, { ...validCelebrity, name }), 'celebrity_scores');
  });

  test.each(['volley', 'Forehand', '', undefined])('rejects the shot type %p', async (shotType) => {
    const admin = makeAdmin();
    await expectRejected(() => addCelebrity(admin.token, { ...validCelebrity, shotType }), 'celebrity_scores');
  });

  test('still refuses a non-admin', async () => {
    const { token } = makeUser();
    await expectRejected(() => addCelebrity(token, validCelebrity), 'celebrity_scores', { status: 403 });
  });
});

describe('leaderboard queries', () => {
  test.each(['volley', 'Forehand', '', undefined])('reject the shot type %p', async (shotType) => {
    const { token } = makeUser();
    const res = await request(app).get(`/api/leaderboard/friends?shotType=${shotType ?? ''}`)
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(400);
  });

  // The concrete consequence of the range check: a validated score cannot be
  // displaced from the top by an out-of-range one.
  test('a rejected out-of-range celebrity score never appears above a real score', async () => {
    const admin = makeAdmin();
    makeAnalysis(admin.id, { shotType: 'serve', similarity: 88 });

    await addCelebrity(admin.token, { name: 'Typo', shotType: 'serve', score: 9999 });

    const res = await request(app).get('/api/leaderboard/worldwide?shotType=serve')
      .set('Authorization', `Bearer ${admin.token}`);

    expect(res.status).toBe(200);
    expect(res.body.leaderboard.every((row) => row.score <= 100)).toBe(true);
    expect(res.body.leaderboard.map((row) => row.name)).not.toContain('Typo');
  });
});
