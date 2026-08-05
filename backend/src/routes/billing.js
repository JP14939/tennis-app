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
    if (!response.ok) {
      throw new Error(`RevenueCat API returned ${response.status}`);
    }
    const data = await response.json();
    // v2 list endpoints commonly wrap results in `items` -- checking both
    // shapes since this hasn't been confirmed against a real response yet.
    // Verify this against an actual RevenueCat account during testing and
    // simplify to whichever key is correct.
    const isPremium = (data.active_entitlements || data.items || [])
      .some((e) => e.entitlement_id === ENTITLEMENT_ID);

    db.prepare('UPDATE users SET tier = ? WHERE id = ?').run(isPremium ? 'premium' : 'free', req.user.id);
    res.json({ tier: isPremium ? 'premium' : 'free' });
  } catch (err) {
    console.error('[billing/sync] failed:', err.message);
    res.status(502).json({ error: 'Could not reach billing provider' });
  }
});

module.exports = router;
