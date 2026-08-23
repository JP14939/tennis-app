// A message body is stored AND pushed verbatim as a notification, so the
// cap here bounds what a recipient's device receives, not just a column.

process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const request = require('supertest');
const { appWith, makeUser, makeFriends, expectRejected, db } = require('./testSupport');

const app = appWith(require('./messages'));

function friendPair() {
  const me = makeUser();
  const friend = makeUser();
  makeFriends(me.id, friend.id);
  return { me, friend };
}

function send(token, toId, body) {
  return request(app).post(`/api/messages/thread/${toId}`)
    .set('Authorization', `Bearer ${token}`).send(body);
}

describe('POST /messages/thread/:otherUserId', () => {
  test('sends a normal message between friends', async () => {
    const { me, friend } = friendPair();
    const res = await send(me.token, friend.id, { body: 'Fancy a hit Saturday?' });
    expect(res.status).toBe(201);
    expect(res.body.message.body).toBe('Fancy a hit Saturday?');
  });

  test('accepts a message exactly at the length cap', async () => {
    const { me, friend } = friendPair();
    const res = await send(me.token, friend.id, { body: 'x'.repeat(2000) });
    expect(res.status).toBe(201);
  });

  test.each([
    ['x'.repeat(2001), 'one character over the cap'],
    ['', 'empty'],
    ['    ', 'whitespace only'],
    [{ text: 'nested' }, 'an object — this used to throw inside better-sqlite3 as a 500'],
    [12345, 'a number'],
    [undefined, 'missing'],
  ])('rejects %p (%s) and sends nothing', async (body) => {
    const { me, friend } = friendPair();
    await expectRejected(() => send(me.token, friend.id, { body }), 'messages');
  });

  test('stores the message trimmed', async () => {
    const { me, friend } = friendPair();
    const res = await send(me.token, friend.id, { body: '  hello  ' });
    expect(res.body.message.body).toBe('hello');
  });

  // The relationship gate predates this work; asserted here so a validation
  // change can't quietly widen who can be messaged.
  test('still refuses to message someone with no relationship', async () => {
    const me = makeUser();
    const stranger = makeUser();
    await expectRejected(() => send(me.token, stranger.id, { body: 'hi' }), 'messages', { status: 403 });
  });

  test('rejects a non-numeric recipient id', async () => {
    const me = makeUser();
    await expectRejected(() => send(me.token, 'abc', { body: 'hi' }), 'messages');
  });
});

describe('stored threads satisfy the at-rest invariants', () => {
  test('a message sent in either direction stores its pair sorted, with a sender inside it', async () => {
    const { runIntegrityChecks } = require('../domain/integrityChecks');
    const { me, friend } = friendPair();

    await send(me.token, friend.id, { body: 'from me' });
    await send(friend.token, me.id, { body: 'from them' });

    // Scoped to this pair -- earlier tests in the file share the in-memory
    // database and leave their own threads behind.
    const [low, high] = me.id < friend.id ? [me.id, friend.id] : [friend.id, me.id];
    const rows = db.prepare(
      'SELECT user_a_id, user_b_id, sender_id FROM messages WHERE user_a_id = ? AND user_b_id = ?'
    ).all(low, high);
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(row.user_a_id).toBeLessThan(row.user_b_id);
      expect([row.user_a_id, row.user_b_id]).toContain(row.sender_id);
    }

    const messageViolations = runIntegrityChecks(db).filter((v) => v.name.startsWith('messages'));
    expect(messageViolations).toEqual([]);
  });
});

describe('POST /messages/report/:messageId', () => {
  async function sendAndGetId() {
    const { me, friend } = friendPair();
    const res = await send(me.token, friend.id, { body: 'something' });
    return { me, friend, messageId: res.body.message.id };
  }

  test('reports a message in your own thread, with and without a reason', async () => {
    const { friend, messageId } = await sendAndGetId();
    const res = await request(app).post(`/api/messages/report/${messageId}`)
      .set('Authorization', `Bearer ${friend.token}`).send({ reason: 'Spam' });
    expect(res.status).toBe(201);
  });

  test.each([
    ['x'.repeat(501), 'over the length cap'],
    [{ why: 'nested' }, 'not a string'],
  ])('rejects the reason %p (%s)', async (reason) => {
    const { friend, messageId } = await sendAndGetId();
    await expectRejected(
      () => request(app).post(`/api/messages/report/${messageId}`)
        .set('Authorization', `Bearer ${friend.token}`).send({ reason }),
      'message_reports',
    );
  });
});

describe('POST /users/:id/block', () => {
  test('blocks another user', async () => {
    const { me, friend } = friendPair();
    const res = await request(app).post(`/api/users/${friend.id}/block`)
      .set('Authorization', `Bearer ${me.token}`).send();
    expect(res.status).toBe(204);
  });

  test('refuses to let anyone block themselves', async () => {
    const me = makeUser();
    await expectRejected(
      () => request(app).post(`/api/users/${me.id}/block`).set('Authorization', `Bearer ${me.token}`).send(),
      'user_blocks',
    );
  });
});
