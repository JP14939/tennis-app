// Regression test for the free-tier daily-analysis-limit race condition
// (backend/src/routes/analyse.js): the count-check and the usage INSERT
// used to happen minutes apart (separated by a Python subprocess spawn),
// letting concurrent requests all pass the check before any of them
// recorded usage. reserveDailyUsageSlot() does both atomically.
process.env.DB_PATH = ':memory:';
const db = require('../db');
const { reserveDailyUsageSlot, releaseUsageSlot, LIMIT_EXCEEDED } = require('./usageLimit');

function makeUser(email) {
  return db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(email, 'x', 'Test User').lastInsertRowid;
}

describe('reserveDailyUsageSlot', () => {
  test('allows up to the limit, then rejects', () => {
    const userId = makeUser('limit1@test.com');
    expect(reserveDailyUsageSlot(db, userId, 2)).not.toBe(LIMIT_EXCEEDED);
    expect(reserveDailyUsageSlot(db, userId, 2)).not.toBe(LIMIT_EXCEEDED);
    expect(reserveDailyUsageSlot(db, userId, 2)).toBe(LIMIT_EXCEEDED);
  });

  test('simulated concurrent reservations never exceed the limit', () => {
    // Simulates what used to break: many "requests" all calling the
    // check-and-reserve step before any of them would have finished the
    // (formerly separate, now-eliminated) async gap. Since reservation is
    // now a single synchronous transaction, calling it N times in a tight
    // loop is a faithful stand-in for N concurrent requests racing.
    const userId = makeUser('limit2@test.com');
    const results = Array.from({ length: 10 }, () => reserveDailyUsageSlot(db, userId, 2));
    const granted = results.filter((r) => r !== LIMIT_EXCEEDED);
    expect(granted).toHaveLength(2);
  });

  test('releaseUsageSlot lets the slot be reused (failed analyses do not count)', () => {
    const userId = makeUser('limit3@test.com');
    const first = reserveDailyUsageSlot(db, userId, 1);
    expect(first).not.toBe(LIMIT_EXCEEDED);
    expect(reserveDailyUsageSlot(db, userId, 1)).toBe(LIMIT_EXCEEDED);

    releaseUsageSlot(db, first);
    expect(reserveDailyUsageSlot(db, userId, 1)).not.toBe(LIMIT_EXCEEDED);
  });

  test('does not affect a different user\'s limit', () => {
    const userA = makeUser('limitA@test.com');
    const userB = makeUser('limitB@test.com');
    expect(reserveDailyUsageSlot(db, userA, 1)).not.toBe(LIMIT_EXCEEDED);
    expect(reserveDailyUsageSlot(db, userA, 1)).toBe(LIMIT_EXCEEDED);
    expect(reserveDailyUsageSlot(db, userB, 1)).not.toBe(LIMIT_EXCEEDED);
  });
});
