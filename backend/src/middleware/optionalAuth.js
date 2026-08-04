const jwt = require('jsonwebtoken');

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
      req.user = jwt.verify(token, process.env.JWT_SECRET);
    } catch {
      // Invalid/expired token -- treat as anonymous rather than rejecting.
    }
  }
  next();
}

module.exports = optionalAuth;
