// A logged match is written by one player but shown to BOTH, and feeds
// computeRecord()'s win/loss tally on each side -- so nonsense here corrupts
// the other person's view of their own record, not just the sender's.

process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const request = require('supertest');
const { appWith, makeUser, makeAnalysis, makeFriends, expectRejected, db } = require('./testSupport');

const app = appWith(require('./friends'));

function logMatch(token, friendId, body) {
  return request(app).post(`/api/friends/${friendId}/matches`)
    .set('Authorization', `Bearer ${token}`).send(body);
}

function friendPair() {
  const me = makeUser();
  const friend = makeUser();
  makeFriends(me.id, friend.id);
  return { me, friend };
}

const validMatch = { playedAt: '2026-08-01', setsWon: 2, setsLost: 1 };

describe('POST /friends/:userId/matches — set counts', () => {
  test.each([
    [0, 2, 'a straight-sets loss'],
    [2, 0, 'a straight-sets win'],
    [3, 2, 'a five-setter'],
    [7, 0, 'the documented ceiling'],
  ])('accepts %p-%p (%s)', async (setsWon, setsLost) => {
    const { me, friend } = friendPair();
    const res = await logMatch(me.token, friend.id, { ...validMatch, setsWon, setsLost });
    expect(res.status).toBe(201);
  });

  test.each([
    [-1, 2, 'negative sets would corrupt both players\' records'],
    [2, -5, 'negative sets on the other side'],
    [8, 0, 'more sets than any format contains'],
    [1e9, 0, 'an absurd value the old integer-only check allowed'],
    [2.5, 1, 'a fractional set'],
    ['2', '1', 'stringified counts'],
    [undefined, 1, 'missing'],
  ])('rejects %p-%p (%s) and logs no match', async (setsWon, setsLost) => {
    const { me, friend } = friendPair();
    await expectRejected(() => logMatch(me.token, friend.id, { ...validMatch, setsWon, setsLost }), 'friend_matches');
  });
});

describe('POST /friends/:userId/matches — playedAt', () => {
  test.each(['2026-08-01', '2026-08-01T14:30:00Z'])('accepts %p', async (playedAt) => {
    const { me, friend } = friendPair();
    expect((await logMatch(me.token, friend.id, { ...validMatch, playedAt })).status).toBe(201);
  });

  test.each([
    ['last tuesday', 'unparseable — it is the ORDER BY key and a rendered date'],
    ['', 'empty'],
    [undefined, 'missing'],
    ['1970-01-01', 'implausibly early'],
    ['3000-01-01', 'implausibly late'],
    [1754006400000, 'an epoch number rather than a date string'],
  ])('rejects %p (%s)', async (playedAt) => {
    const { me, friend } = friendPair();
    await expectRejected(() => logMatch(me.token, friend.id, { ...validMatch, playedAt }), 'friend_matches');
  });
});

describe('POST /friends/:userId/matches — relationship and scoreDetail', () => {
  test('still refuses to log a match against someone who is not a friend', async () => {
    const me = makeUser();
    const stranger = makeUser();
    await expectRejected(
      () => logMatch(me.token, stranger.id, validMatch),
      'friend_matches',
      { status: 403 },
    );
  });

  test('rejects an over-long score detail', async () => {
    const { me, friend } = friendPair();
    await expectRejected(
      () => logMatch(me.token, friend.id, { ...validMatch, scoreDetail: 'x'.repeat(101) }),
      'friend_matches',
    );
  });

  test('a valid match reads back correctly from both sides', async () => {
    const { me, friend } = friendPair();
    await logMatch(me.token, friend.id, { ...validMatch, setsWon: 2, setsLost: 1 });

    const mine = await request(app).get(`/api/friends/${friend.id}/matches`)
      .set('Authorization', `Bearer ${me.token}`);
    const theirs = await request(app).get(`/api/friends/${me.id}/matches`)
      .set('Authorization', `Bearer ${friend.token}`);

    expect(mine.body.matches[0]).toMatchObject({ my_sets: 2, their_sets: 1 });
    expect(theirs.body.matches[0]).toMatchObject({ my_sets: 1, their_sets: 2 });
  });
});

describe('POST /friends/:userId/share', () => {
  function share(token, friendId, body) {
    return request(app).post(`/api/friends/${friendId}/share`)
      .set('Authorization', `Bearer ${token}`).send(body);
  }

  test('shares an analysis you own with a friend', async () => {
    const { me, friend } = friendPair();
    const res = await share(me.token, friend.id, { analysisId: makeAnalysis(me.id) });
    expect(res.status).toBe(201);
  });

  test('rejects a non-numeric user id with a 400 rather than a misleading 403', async () => {
    const me = makeUser();
    const res = await share(me.token, 'abc', { analysisId: makeAnalysis(me.id) });
    expect(res.status).toBe(400);
  });

  test.each([
    [undefined, 'missing'],
    [{}, 'an object'],
    ['abc', 'not a number'],
    [0, 'not a real row id'],
  ])('rejects the analysisId %p (%s) and shares nothing', async (analysisId) => {
    const { me, friend } = friendPair();
    await expectRejected(() => share(me.token, friend.id, { analysisId }), 'shared_analyses');
  });

  // isPositiveIntegerId explicitly accepts a numeric string, but a redundant
  // `!Number.isInteger(analysisId)` re-check further down used to reject
  // that exact shape after it had already passed validation.
  test('accepts a numeric-string analysisId, the same shape its own validator allows', async () => {
    const { me, friend } = friendPair();
    const res = await share(me.token, friend.id, { analysisId: String(makeAnalysis(me.id)) });
    expect(res.status).toBe(201);
  });

  test("still refuses to share an analysis you do not own", async () => {
    const { me, friend } = friendPair();
    const stranger = makeUser();
    await expectRejected(
      () => share(me.token, friend.id, { analysisId: makeAnalysis(stranger.id) }),
      'shared_analyses',
      { status: 404 },
    );
  });
});

describe('stored matches satisfy the at-rest invariants', () => {
  test('every row written through the route passes the integrity checker', async () => {
    const { runIntegrityChecks } = require('../domain/integrityChecks');
    const { me, friend } = friendPair();

    await logMatch(me.token, friend.id, { ...validMatch, setsWon: 3, setsLost: 2 });
    await logMatch(friend.token, me.id, { ...validMatch, setsWon: 0, setsLost: 2 });

    const matchViolations = runIntegrityChecks(db).filter((v) => v.name.startsWith('friend_matches'));
    expect(matchViolations).toEqual([]);
  });
});
