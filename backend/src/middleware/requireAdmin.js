// Comma-separated env var, defaulting to Jack's own account so this works
// out of the box without requiring a .env edit first -- extracted from
// routes/leaderboard.js (celebrity-scores admin gate) so the Dev Page's
// routes (routes/dev.js) share the exact same allowlist instead of a second
// copy that could drift out of sync with it.
const ADMIN_EMAILS = (process.env.ADMIN_EMAILS || 'jack.p14370@gmail.com')
  .split(',').map((e) => e.trim().toLowerCase());

function isAdmin(user) {
  return ADMIN_EMAILS.includes((user?.email || '').toLowerCase());
}

function requireAdmin(req, res, next) {
  if (!isAdmin(req.user)) {
    return res.status(403).json({ error: 'Admin only' });
  }
  next();
}

module.exports = { isAdmin, requireAdmin, ADMIN_EMAILS };
