const express = require('express');
const crypto = require('crypto');
const db = require('../db');

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
  // back with no lookup table needed.
  const userId = parseInt(event.app_user_id, 10);
  const user = Number.isInteger(userId) ? db.prepare('SELECT id FROM users WHERE id = ?').get(userId) : null;

  db.prepare(
    'INSERT INTO payment_events (user_id, event_type, raw_payload) VALUES (?, ?, ?)'
  ).run(user ? user.id : null, event.type, JSON.stringify(req.body));

  if (!user) {
    // Logged above for debugging, but nothing to update -- ack anyway so
    // RevenueCat doesn't keep retrying a delivery we can't act on.
    return res.status(200).json({ ok: true, note: 'user not found, event logged only' });
  }

  const entitlementIds = event.entitlement_ids || [];
  const affectsOurEntitlement = entitlementIds.length === 0 || entitlementIds.includes(ENTITLEMENT_ID);

  if (affectsOurEntitlement && GRANT_EVENTS.has(event.type)) {
    db.prepare("UPDATE users SET tier = 'premium' WHERE id = ?").run(user.id);
  } else if (affectsOurEntitlement && REVOKE_EVENTS.has(event.type)) {
    db.prepare("UPDATE users SET tier = 'free' WHERE id = ?").run(user.id);
  }

  res.status(200).json({ ok: true });
});

module.exports = router;
