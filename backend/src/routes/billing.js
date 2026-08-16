const express = require('express');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');

const router = express.Router();

const ENTITLEMENT_ID = process.env.REVENUECAT_ENTITLEMENT_ID || 'premium';

// Called by the frontend immediately after a successful checkout.
// Webhooks (see routes/webhooks.js) are the durable source of truth for
// renewals/cancellations over time, but relying on webhook delivery timing
// alone would leave the UI showing "still free" for a few seconds right
// after someone just paid -- this hits RevenueCat's REST API directly for
// this user's current entitlement status and updates tier synchronously.
// https://www.revenuecat.com/docs/api-v2
router.post('/billing/sync', requireAuth, async (req, res) => {
  const projectId = process.env.REVENUECAT_PROJECT_ID;
  const secretKey = process.env.REVENUECAT_SECRET_API_KEY;
  if (!projectId || !secretKey) {
    return res.status(503).json({ error: 'Billing sync not configured' });
  }

  try {
    const response = await fetch(
      `https://api.revenuecat.com/v2/projects/${projectId}/customers/${req.user.id}/active_entitlements`,
      { headers: { Authorization: `Bearer ${secretKey}` } }
    );
    // A customer who has never made a purchase doesn't exist in RevenueCat
    // yet -- confirmed live against the real API (a fresh test user 404s
    // with type: "resource_missing"), and is the single most common case
    // this endpoint will see (every free user). Not an error: no purchases
    // means not premium, same as an empty entitlements list.
    if (response.status === 404) {
      db.prepare('UPDATE users SET tier = ? WHERE id = ?').run('free', req.user.id);
      return res.json({ tier: 'free' });
    }
    if (!response.ok) {
      throw new Error(`RevenueCat API returned ${response.status}`);
    }
    const data = await response.json();
    // Confirmed shape (RevenueCat API v2 docs + community-reported real
    // responses): the array is nested at active_entitlements.items, not
    // active_entitlements itself (that's an object: {object, items,
    // next_page, url}) -- the old `data.active_entitlements || data.items`
    // fallback was broken, since a truthy object short-circuited past the
    // real array and .some() was called on a plain object.
    //
    // Confirmed live against a real purchase: each item's `entitlement_id`
    // is RevenueCat's internal opaque ID (e.g. "entlee4b5ca9dd"), NOT the
    // human-readable identifier ("premium") set in the dashboard -- so
    // comparing against ENTITLEMENT_ID here always failed, silently
    // clobbering a correct webhook-driven grant moments after purchase
    // (this endpoint runs right after checkout and overwrites tier).
    // Resolving "premium" to its opaque ID needs a project_configuration
    // read scope this key deliberately doesn't have (see the comment on
    // REVENUECAT_SECRET_API_KEY in .env.example). Since this project only
    // ever grants one real entitlement, "any active entitlement" is an
    // accurate proxy -- revisit with a proper ID lookup if a second
    // entitlement is ever added.
    const isPremium = (data.active_entitlements?.items || data.items || []).length > 0;

    db.prepare('UPDATE users SET tier = ? WHERE id = ?').run(isPremium ? 'premium' : 'free', req.user.id);
    res.json({ tier: isPremium ? 'premium' : 'free' });
  } catch (err) {
    console.error('[billing/sync] failed:', err.message);
    res.status(502).json({ error: 'Could not reach billing provider' });
  }
});

module.exports = router;
