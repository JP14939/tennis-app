// Regression tests: several friends.js endpoints bound a request-body field
// directly into a SQL '?' placeholder with no type check. A non-primitive
// value (e.g. an object/array) throws a RangeError deep in better-sqlite3
// ("Too few/many parameter values were provided") which server.js's global
// error handler turns into a bare 500, instead of a clean 400.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const friendsRouter = require('./friends');

const app = express();
app.use(express.json());
app.use('/api', friendsRouter);

function makeUser(email) {
  const id = db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(email, 'x', 'Test User').lastInsertRowid;
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

function makeFriends(idA, idB) {
  const [a, b] = idA < idB ? [idA, idB] : [idB, idA];
  db.prepare('INSERT INTO friend_links (user_a_id, user_b_id) VALUES (?, ?)').run(a, b);
}

describe('POST /friends/:userId/share', () => {
  test('rejects a non-integer analysisId with 400 instead of a 500 crash', async () => {
    const a = makeUser('share-a@test.com');
    const b = makeUser('share-b@test.com');
    makeFriends(a.id, b.id);

    const res = await request(app)
      .post(`/api/friends/${b.id}/share`)
      .set('Authorization', `Bearer ${a.token}`)
      .send({ analysisId: { bogus: true } });
    expect(res.status).toBe(400);
  });
});

describe('POST /friends/:userId/matches', () => {
  test('rejects a non-primitive playedAt with 400 instead of a 500 crash', async () => {
    const a = makeUser('match-a@test.com');
    const b = makeUser('match-b@test.com');
    makeFriends(a.id, b.id);

    const res = await request(app)
      .post(`/api/friends/${b.id}/matches`)
      .set('Authorization', `Bearer ${a.token}`)
      .send({ playedAt: {}, setsWon: 2, setsLost: 1 });
    expect(res.status).toBe(400);
  });

  test('rejects a non-string scoreDetail with 400 instead of a 500 crash', async () => {
    const a = makeUser('match-c@test.com');
    const b = makeUser('match-d@test.com');
    makeFriends(a.id, b.id);

    const res = await request(app)
      .post(`/api/friends/${b.id}/matches`)
      .set('Authorization', `Bearer ${a.token}`)
      .send({ playedAt: '2026-08-23', setsWon: 2, setsLost: 1, scoreDetail: { bogus: true } });
    expect(res.status).toBe(400);
  });

  test('accepts a valid match log', async () => {
    const a = makeUser('match-e@test.com');
    const b = makeUser('match-f@test.com');
    makeFriends(a.id, b.id);

    const res = await request(app)
      .post(`/api/friends/${b.id}/matches`)
      .set('Authorization', `Bearer ${a.token}`)
      .send({ playedAt: '2026-08-23', setsWon: 2, setsLost: 1, scoreDetail: '6-4, 6-3' });
    expect(res.status).toBe(201);
  });
});
