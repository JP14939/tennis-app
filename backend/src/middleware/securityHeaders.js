// A small, hand-rolled set of response security headers -- same "no new
// dependency, fine for this app's actual shape" spirit as middleware/rateLimit.js.
// helmet would pull in a package whose defaults (notably its own CSP and
// Cross-Origin-Embedder/Opener policies) would need per-header tuning anyway to
// not break the cross-origin video mounts (/user-clips, /pro-clips, ...) and
// the one served HTML page, so the headers this app actually wants are set
// explicitly here instead.
//
// This backend is a JSON API plus a handful of static mounts: video clips the
// Expo app (a different origin) loads directly, and one self-serve
// reset-password.html. The headers below are the subset that matters for that:
//
//   X-Content-Type-Options: nosniff
//     Defence in depth with utils/videoUpload.js's safeVideoExt() -- even if a
//     non-video somehow lands in a served directory, the browser won't
//     second-guess our Content-Type and render it as HTML.
//   X-Frame-Options: DENY  (+ CSP frame-ancestors 'none' on the HTML page)
//     Nothing here should ever be embedded in a frame; the reset page handling
//     a token especially must not be clickjackable.
//   Referrer-Policy: no-referrer
//     The password-reset link carries the token in its query string. Without
//     this, any resource that page loads (or a click off it) could leak the
//     full URL -- and therefore the token -- in a Referer header.
//   Cross-Origin-Resource-Policy: cross-origin
//     The app IS a different origin from this API, and it must still be able to
//     load the clip files. This states that intent explicitly rather than
//     leaving it to a browser default that trends stricter over time.
//   X-Permitted-Cross-Domain-Policies: none
//     No Flash/Acrobat cross-domain policy file should ever be honoured.
//
// A stricter Content-Security-Policy is applied ONLY to the served HTML
// (reset-password.html) -- a global CSP would also land on the 404/JSON error
// responses for the video mounts for no benefit, and the API responses are
// JSON that no browser renders as a document anyway. The page uses an inline
// <style> and inline <script>, so 'unsafe-inline' is unavoidable there without
// rewriting it; the policy still pins default-src to 'none', limits fetch()
// back to this origin, and blocks framing and <base>/<form> hijacking.
const HTML_CSP = [
  "default-src 'none'",
  "style-src 'unsafe-inline'",
  "script-src 'unsafe-inline'",
  "connect-src 'self'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join('; ');

function securityHeaders(req, res, next) {
  res.set('X-Content-Type-Options', 'nosniff');
  res.set('X-Frame-Options', 'DENY');
  res.set('Referrer-Policy', 'no-referrer');
  res.set('Cross-Origin-Resource-Policy', 'cross-origin');
  res.set('X-Permitted-Cross-Domain-Policies', 'none');

  // The only HTML this backend serves is the static reset-password page.
  if (req.path.endsWith('.html')) {
    res.set('Content-Security-Policy', HTML_CSP);
  }

  next();
}

module.exports = { securityHeaders, HTML_CSP };
