const jwt = require('jsonwebtoken');
const db = require('../db');

function requireAuth(req, res, next) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) {
    return res.status(401).json({ error: 'Missing or malformed Authorization header' });
  }

  try {
    // Pin the accepted algorithm rather than trusting whichever one the
    // token's own header claims -- issueToken() (routes/auth.js) only ever
    // signs with HS256, so a token asserting anything else is never one we
    // issued. Not exploitable today (jsonwebtoken already rejects 'none',
    // and verifying e.g. RS256 against a plain HMAC secret string fails
    // rather than succeeding), but pinning is free, standard JWT hardening
    // (OWASP JWT cheat sheet) and removes the algorithm-confusion class of
    // bug entirely rather than relying on the library's current defaults.
    const decoded = jwt.verify(token, process.env.JWT_SECRET, { algorithms: ['HS256'] });

    // A valid signature alone doesn't mean this token is still supposed to
    // work -- tokens live up to 30 days (routes/auth.js's TOKEN_TTL), and
    // until this check existed there was no way to revoke one short of
    // rotating JWT_SECRET for every user at once. Compare against the
    // version active at signing time (see db.js's token_version comment):
    // a password change or account deletion bumps the DB column, which
    // immediately invalidates every token minted before that point.
    // `?? 0` on both sides so a token signed before this column existed
    // (no `tv` claim) still matches a freshly-migrated row (default 0)
    // instead of every existing session being logged out on deploy.
    const row = db.prepare('SELECT token_version FROM users WHERE id = ?').get(decoded.id);
    if (!row || (decoded.tv ?? 0) !== (row.token_version ?? 0)) {
      return res.status(401).json({ error: 'Invalid or expired token' });
    }

    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid or expired token' });
  }
}

module.exports = requireAuth;
