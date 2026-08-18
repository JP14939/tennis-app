// Atomic "check-and-reserve" helper for free-tier usage caps. Extracted out
// of routes/analyse.js so the race-condition fix (check + insert as one
// synchronous transaction, done BEFORE any async work starts rather than
// after it finishes) is unit-testable without spinning up the whole
// analyse route (which spawns a real Python process).
const LIMIT_EXCEEDED = Symbol('LIMIT_EXCEEDED');

// Returns the new analysis_usage row id, or LIMIT_EXCEEDED if the user is
// already at `limit` for today. Synchronous + transactional so two calls
// for the same user can't both observe a count under the limit.
function reserveDailyUsageSlot(db, userId, limit) {
  const reserve = db.transaction(() => {
    const { count } = db.prepare(
      `SELECT COUNT(*) AS count FROM analysis_usage WHERE user_id = ? AND date(created_at) = date('now')`
    ).get(userId);
    if (count >= limit) return LIMIT_EXCEEDED;
    return db.prepare('INSERT INTO analysis_usage (user_id) VALUES (?)').run(userId).lastInsertRowid;
  });
  return reserve();
}

// Undoes a reservation (e.g. the analysis that reserved it then failed) so
// a failed attempt doesn't count against the user's daily limit.
function releaseUsageSlot(db, usageRowId) {
  if (usageRowId !== null && usageRowId !== undefined) {
    db.prepare('DELETE FROM analysis_usage WHERE id = ?').run(usageRowId);
  }
}

module.exports = { reserveDailyUsageSlot, releaseUsageSlot, LIMIT_EXCEEDED };
