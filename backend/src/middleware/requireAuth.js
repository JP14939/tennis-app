const jwt = require('jsonwebtoken');

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
    req.user = jwt.verify(token, process.env.JWT_SECRET, { algorithms: ['HS256'] });
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid or expired token' });
  }
}

module.exports = requireAuth;
