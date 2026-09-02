const express = require('express');
const crypto = require('crypto');
const db = require('../db');
const { isPositiveIntegerId } = require('../domain/invariants');

const router = express.Router();

// Event types that mean "this user currently has active premium access" --
// per RevenueCat's semantics, CANCELLATION alone does NOT mean immediate
// loss of access (the subscriber keeps access until the period actually
// ends, which arrives later as EXPIRATION), so it's deliberately not in
// this list.
const GRANT_EVENTS = new Set([
  'INITIAL_PURCHASE', 'RENEWAL', 'PRODUCT_CHANGE', 'UNCANCELLATION',
  'NON_RENEWING_PURCHASE', 'SUBSCRIPTION_EXTENDED',
]);
const REVOKE_EVENTS = new Set(['EXPIRATION']);

const ENTITLEMENT_ID = process.env.REVENUECAT_ENTITLEMENT_ID || 'premium';

// RevenueCat's webhook docs: https://www.revenuecat.com/docs/integrations/webhooks
// Auth is a custom Authorization header value you set in the RevenueCat
// dashboard and here -- simpler than HMAC signature verification, and
// sufficient given this is the only thing that ever calls this route.
// Constant-time comparison so a byte-by-byte timing side-channel can't help
// an attacker brute-force REVENUECAT_WEBHOOK_SECRET. timingSafeEqual throws
// on mismatched buffer lengths rather than returning false, so that has to
// be checked first (a length mismatch is safe to reveal -- it's the
// content match that must be constant-time).
function safeEqual(a, b) {
  const bufA = Buffer.from(a, 'utf8');
  const bufB = Buffer.from(b, 'utf8');
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

router.post('/webhooks/revenuecat', (req, res) => {
  const expected = process.env.REVENUECAT_WEBHOOK_SECRET;
  const provided = req.headers.authorization;
  if (!expected || typeof provided !== 'string' || !safeEqual(provided, expected)) {
    return res.status(401).json({ error: 'Invalid webhook authorization' });
  }

  const event = req.body?.event;
  // event.type needs a type check, not just a truthy one: a non-string
  // truthy value (true, {}, []) passed the old guard and then threw inside
  // better-sqlite3's bind on the payment_events INSERT below, turning a
  // malformed delivery into an uncaught 500 instead of this clean 400.
  if (!event || !event.app_user_id || typeof event.type !== 'string' || !event.type) {
    return res.status(400).json({ error: 'Malformed webhook payload' });
  }

  // app_user_id is set to our own users.id as a string when the frontend
  // identifies the shopper (see PremiumCheckout.web.js) -- maps straight
  // back with no lookup table needed. RevenueCat also delivers events for
  // customers it generated its own (non-numeric) anonymous id for, and
  // sandbox/test deliveries can send arbitrary strings -- parseInt() would
  // silently truncate a digit-prefixed one of those (e.g. a UUID-shaped id
  // starting "12345678-...") into a small integer that could collide with a
  // real, unrelated user's id and flip THEIR tier instead of ack'ing a
  // delivery this app can't attribute. isPositiveIntegerId requires the
  // whole string to be digits, so anything else maps to "no matching user".
  const userId = isPositiveIntegerId(event.app_user_id) ? Number(event.app_user_id) : null;
  const user = userId !== null ? db.prepare('SELECT id FROM users WHERE id = ?').get(userId) : null;

  db.prepare(
    'INSERT INTO payment_events (user_id, event_type, raw_payload) VALUES (?, ?, ?)'
  ).run(user ? user.id : null, event.type, JSON.stringify(req.body));

  if (!user) {
    // Logged above for debugging, but nothing to update -- ack anyway so
    // RevenueCat doesn't keep retrying a delivery we can't act on.
    return res.status(200).json({ ok: true, note: 'user not found, event logged only' });
  }

  // entitlement_ids needs the same type check as event.type above: a
  // truthy non-array (e.g. {}) would make `.length` undefined, skip the
  // `=== 0` short-circuit, and throw inside `.includes()` below -- after
  // the payment_events INSERT above already ran, so a malformed delivery
  // would permanently fail to apply while RevenueCat keeps retrying and
  // logging duplicate rows.
  const entitlementIds = Array.isArray(event.entitlement_ids) ? event.entitlement_ids : [];
  const affectsOurEntitlement = entitlementIds.length === 0 || entitlementIds.includes(ENTITLEMENT_ID);

  if (affectsOurEntitlement && GRANT_EVENTS.has(event.type)) {
    db.prepare("UPDATE users SET tier = 'premium' WHERE id = ?").run(user.id);
  } else if (affectsOurEntitlement && REVOKE_EVENTS.has(event.type)) {
    db.prepare("UPDATE users SET tier = 'free' WHERE id = ?").run(user.id);
  }

  res.status(200).json({ ok: true });
});

module.exports = router;
