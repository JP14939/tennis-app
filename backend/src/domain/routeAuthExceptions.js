// Centralizes routes that intentionally have neither requireAuth nor
// optionalAuth wired -- consumed by routeAuthConvention.test.js, which fails
// closed on any route not listed here. Deliberately require a `reason` so
// adding an exception is a conscious choice, not a way to silence the test.
//
// Root cause this guards against: there was no enforced convention for
// requireAuth vs optionalAuth per route, which caused a real free-tier-cap
// bypass (fixed 2026-08-22). Each known site was patched individually, but
// nothing stopped the *next* new route from repeating it -- this list plus
// the test that reads it is that guard.
module.exports = [
  { method: 'post', path: '/auth/signup', reason: 'pre-login: creates the account that would hold the token' },
  { method: 'post', path: '/auth/login', reason: 'pre-login: issues the token' },
  { method: 'post', path: '/auth/forgot-password', reason: 'pre-login: caller has no token yet' },
  { method: 'post', path: '/auth/reset-password', reason: 'pre-login: authenticated via the emailed reset token, not a JWT' },
  { method: 'post', path: '/webhooks/revenuecat', reason: 'authenticated via a constant-time header-secret check instead of JWT (see webhooks.js safeEqual)' },
];
