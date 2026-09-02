// Regression test for a bug found in the 2026-08-31 sweep: POST /billing/sync
// races RevenueCat's own webhook delivery for the SAME purchase (see
// routes/webhooks.js). Both fire moments after a checkout completes, and
// RevenueCat's read API can still show "no active entitlements" for a
// purchase whose webhook has already landed. The old code unconditionally
// wrote tier='free' whenever RevenueCat's read looked empty/404, silently
// clobbering a correct webhook-driven 'premium' grant. /billing/sync must be
// upgrade-only: it may promote to premium, but never write 'free' itself.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';
process.env.REVENUECAT_PROJECT_ID = 'proj_test';
process.env.REVENUECAT_SECRET_API_KEY = 'sk_test';

const express = require('express');
const request = require('supertest');
const jwt = require('jsonwebtoken');
const db = require('../db');
const billingRouter = require('./billing');

const app = express();
app.use(express.json());
app.use('/api', billingRouter);

function makeUser(tier = 'free') {
  const email = `billing_${Date.now()}_${Math.random()}@test.com`;
  const id = db.prepare('INSERT INTO users (email, password_hash, name, tier) VALUES (?, ?, ?, ?)')
    .run(email, 'x', 'Test User', tier).lastInsertRowid;
  const token = jwt.sign({ id }, process.env.JWT_SECRET);
  return { id, token };
}

function tierOf(id) {
  return db.prepare('SELECT tier FROM users WHERE id = ?').get(id).tier;
}

describe('POST /billing/sync', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  test('does not downgrade a user the webhook already made premium, on a RevenueCat 404', async () => {
    const { id, token } = makeUser('premium');
    global.fetch = jest.fn(async () => ({
      status: 404,
      ok: false,
      json: async () => ({ error: { type: 'resource_missing' } }),
    }));

    const res = await request(app).post('/api/billing/sync').set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.tier).toBe('premium');
    expect(tierOf(id)).toBe('premium');
  });

  test('does not downgrade a user the webhook already made premium, on an empty active_entitlements list', async () => {
    const { id, token } = makeUser('premium');
    global.fetch = jest.fn(async () => ({
      status: 200,
      ok: true,
      json: async () => ({ active_entitlements: { items: [] } }),
    }));

    const res = await request(app).post('/api/billing/sync').set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.tier).toBe('premium');
    expect(tierOf(id)).toBe('premium');
  });

  test('still promotes a free user to premium when RevenueCat confirms an active entitlement', async () => {
    const { id, token } = makeUser('free');
    global.fetch = jest.fn(async () => ({
      status: 200,
      ok: true,
      json: async () => ({ active_entitlements: { items: [{ entitlement_id: 'entlee4b5ca9dd' }] } }),
    }));

    const res = await request(app).post('/api/billing/sync').set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.tier).toBe('premium');
    expect(tierOf(id)).toBe('premium');
  });

  test('a free user with genuinely no purchases stays free', async () => {
    const { id, token } = makeUser('free');
    global.fetch = jest.fn(async () => ({
      status: 404,
      ok: false,
      json: async () => ({ error: { type: 'resource_missing' } }),
    }));

    const res = await request(app).post('/api/billing/sync').set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.tier).toBe('free');
    expect(tierOf(id)).toBe('free');
  });
});
