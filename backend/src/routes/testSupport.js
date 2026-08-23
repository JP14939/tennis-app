// Shared bootstrap for the *.validation.test.js files.
//
// Not a test file itself (no `.test.` in the name, so jest won't collect it).
// Each validation suite mounts one router against an in-memory database and
// asserts the same two things about every rejection: the status is a clean
// 400, and nothing was written. The "nothing was written" half is the part
// worth sharing -- it's easy to write a validation test that only checks the
// status code and would still pass if the route rejected the request AFTER
// inserting the row.
//
// Callers MUST set process.env.DB_PATH = ':memory:' before requiring this,
// because requiring it loads ../db (same constraint the existing
// history.test.js bootstrap has).

const express = require('express');
const jwt = require('jsonwebtoken');
const db = require('../db');

// Builds an express app with `router` mounted at /api, matching how
// server.js mounts every route file.
function appWith(router) {
  const app = express();
  app.use(express.json());
  app.use('/api', router);
  // Mirrors server.js's global error handler so a route that throws surfaces
  // as a 500 here too -- otherwise Express's default HTML error page makes a
  // "did this 400 or 500?" assertion ambiguous.
  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    res.status(500).json({ error: 'Internal server error' });
  });
  return app;
}

let userCounter = 0;

function makeUser({ tier = 'free', name = 'Test User' } = {}) {
  userCounter += 1;
  const email = `user${userCounter}@test.com`;
  const id = db.prepare('INSERT INTO users (email, password_hash, name, tier) VALUES (?, ?, ?, ?)')
    .run(email, 'hash', name, tier).lastInsertRowid;
  return { id, email, token: jwt.sign({ id }, process.env.JWT_SECRET) };
}

function makeAnalysis(userId, { shotType = 'forehand', similarity = 80 } = {}) {
  return db.prepare(
    'INSERT INTO analyses (user_id, shot_type, similarity, result_json) VALUES (?, ?, ?, ?)'
  ).run(userId, shotType, similarity, '{}').lastInsertRowid;
}

// Friendship is stored as a sorted pair (see friends.js's sortedPair).
function makeFriends(idA, idB) {
  const [a, b] = idA < idB ? [idA, idB] : [idB, idA];
  db.prepare('INSERT OR IGNORE INTO friend_links (user_a_id, user_b_id) VALUES (?, ?)').run(a, b);
}

function rowCount(table) {
  return db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n;
}

// The assertion that actually matters. `send` performs the request; `table` is
// what must not grow. A 500 fails this too: an unvalidated field reaching
// better-sqlite3 and throwing is the exact failure mode being closed here, so
// "rejected with a 500" is not an acceptable pass.
async function expectRejected(send, table, { status = 400 } = {}) {
  const before = rowCount(table);
  const res = await send();

  expect({ status: res.status, body: res.body }).toEqual({
    status,
    body: expect.objectContaining({ error: expect.any(String) }),
  });
  expect(rowCount(table)).toBe(before);

  return res;
}

module.exports = { appWith, makeUser, makeAnalysis, makeFriends, rowCount, expectRejected, db };
