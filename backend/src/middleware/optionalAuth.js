const jwt = require('jsonwebtoken');
const db = require('../db');

// Unlike requireAuth, never rejects the request -- identifies a logged-in
// user when a valid token is present (req.user), otherwise leaves req.user
// null and lets the request through as a guest. Used by routes that behave
// differently for logged-in vs anonymous callers without forcing login for
// everyone (e.g. the free-tier daily analysis limit only applies to
// identifiable free accounts; guests keep today's unauthenticated behavior).
function optionalAuth(req, res, next) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;

  req.user = null;
  if (token) {
    try {
      // Same algorithm pinning as requireAuth.js -- see its comment.
      const decoded = jwt.verify(token, process.env.JWT_SECRET, { algorithms: ['HS256'] });
      // Same token_version freshness check as requireAuth.js -- a token
      // that's been revoked by a password change or account deletion
      // should fall back to anonymous here too, not silently keep
      // identifying the caller as that user.
      const row = db.prepare('SELECT token_version FROM users WHERE id = ?').get(decoded.id);
      if (row && (decoded.tv ?? 0) === (row.token_version ?? 0)) {
        req.user = decoded;
      }
    } catch {
      // Invalid/expired token -- treat as anonymous rather than rejecting.
    }
  }
  next();
}

module.exports = optionalAuth;
