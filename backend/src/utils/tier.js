const db = require('../db');

// Always looked up fresh from the users table rather than trusted from a
// JWT's tier claim -- tokens are valid 30 days and tier can change (e.g. via
// direct DB edit, the only way to become premium today) without the user
// re-logging-in, so a stale token must never let tier-gated behavior go stale.
function currentTier(userId) {
  const row = db.prepare('SELECT tier FROM users WHERE id = ?').get(userId);
  return row ? row.tier : 'free';
}

module.exports = { currentTier };
