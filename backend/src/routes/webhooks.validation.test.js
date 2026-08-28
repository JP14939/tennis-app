// POST /webhooks/revenuecat guarded event.type with only a truthy check, so a
// non-string truthy value (true, {}, []) passed validation and then threw
// inside better-sqlite3's bind on the payment_events INSERT -- turning a
// malformed but authenticated delivery into an uncaught 500 instead of a clean
// 400. These tests assert the 400 and that no payment_events row is written.

process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';
process.env.REVENUECAT_WEBHOOK_SECRET = 'test-webhook-secret';

const request = require('supertest');
const { appWith, makeUser, rowCount, db } = require('./testSupport');

const app = appWith(require('./webhooks'));

const SECRET = process.env.REVENUECAT_WEBHOOK_SECRET;

function post(body, auth = SECRET) {
  const req = request(app).post('/api/webhooks/revenuecat');
  if (auth !== null) req.set('Authorization', auth);
  return req.send(body);
}

describe('POST /webhooks/revenuecat auth', () => {
  test('rejects a request with no/incorrect secret and writes nothing', async () => {
    const before = rowCount('payment_events');
    expect((await post({ event: { app_user_id: '1', type: 'INITIAL_PURCHASE' } }, null)).status).toBe(401);
    expect((await post({ event: { app_user_id: '1', type: 'INITIAL_PURCHASE' } }, 'wrong')).status).toBe(401);
    expect(rowCount('payment_events')).toBe(before);
  });
});

describe('POST /webhooks/revenuecat payload validation', () => {
  test.each([
    [true, 'a boolean — this used to throw inside better-sqlite3 as a 500'],
    [{ nested: 'obj' }, 'an object'],
    [['array'], 'an array'],
  ])('rejects event.type %p (%s) with a 400 and logs nothing', async (type) => {
    const before = rowCount('payment_events');
    const res = await post({ event: { app_user_id: '1', type } });
    expect(res.status).toBe(400);
    expect(rowCount('payment_events')).toBe(before);
  });

  test.each([
    [{}, 'no event'],
    [{ event: { type: 'INITIAL_PURCHASE' } }, 'no app_user_id'],
    [{ event: { app_user_id: '1' } }, 'no type'],
  ])('rejects %p (%s)', async (body) => {
    expect((await post(body)).status).toBe(400);
  });

  test('accepts a well-formed grant event and flips the user to premium', async () => {
    const user = makeUser();
    const before = rowCount('payment_events');
    const res = await post({ event: { app_user_id: String(user.id), type: 'INITIAL_PURCHASE' } });
    expect(res.status).toBe(200);
    expect(rowCount('payment_events')).toBe(before + 1);
    expect(db.prepare('SELECT tier FROM users WHERE id = ?').get(user.id).tier).toBe('premium');
  });

  // app_user_id used to go through parseInt(), which stops at the first
  // non-digit instead of requiring the whole string to be numeric -- a
  // digit-prefixed non-numeric id (RevenueCat sends UUID-shaped ids for
  // anonymous customers) could truncate to a real, unrelated user's id and
  // flip THEIR tier instead of being treated as unattributable.
  test('a digit-prefixed non-numeric app_user_id does not collide with an existing user id', async () => {
    const user = makeUser(); // gets some real integer id, e.g. 1
    const before = rowCount('payment_events');
    const res = await post({
      event: { app_user_id: `${user.id}23-e29b-41d4-a716-446655440000`, type: 'INITIAL_PURCHASE' },
    });
    expect(res.status).toBe(200);
    expect(rowCount('payment_events')).toBe(before + 1);
    // The event is logged for debugging but must NOT be applied to `user`.
    expect(db.prepare('SELECT tier FROM users WHERE id = ?').get(user.id).tier).toBe('free');
  });

  // entitlement_ids had the same gap event.type used to have: `|| []` only
  // guards against a falsy value, so a truthy non-array (e.g. {}) made
  // entitlementIds.length undefined, skipped the `=== 0` short-circuit, and
  // threw inside .includes() below -- after the payment_events INSERT above
  // had already run. Assert this now 200s (doesn't crash) and still applies
  // the tier change, since a non-array entitlement_ids shouldn't block an
  // otherwise well-formed event from being processed.
  test('a non-array truthy entitlement_ids does not crash and still grants premium', async () => {
    const user = makeUser();
    const res = await post({
      event: { app_user_id: String(user.id), type: 'INITIAL_PURCHASE', entitlement_ids: {} },
    });
    expect(res.status).toBe(200);
    expect(db.prepare('SELECT tier FROM users WHERE id = ?').get(user.id).tier).toBe('premium');
  });
});
