// Minimal in-memory sliding-window rate limiter -- no new dependency, and
// fine for this app's actual deployment shape (a single Node process on one
// Hetzner box, no horizontal scaling -- see HANDOVER.md). Not meant as a
// general-purpose limiter: it exists specifically to put a ceiling on the
// auth endpoints (routes/auth.js), which had none at all -- unlimited
// POST /auth/login attempts against any known email, unlimited
// POST /auth/signup (each new free account gets its own fresh
// FREE_DAILY_LIMIT on /api/analyse, so unrestricted signup is itself a
// resource-exhaustion path against the Python/MediaPipe subprocess), and
// unlimited POST /auth/forgot-password (an email-bombing vector against
// Resend's account and against whoever's inbox is targeted).
const buckets = new Map();

// Sweep stale buckets periodically so this doesn't grow unbounded across a
// long-running process -- same "basic starting point, not a robust queue"
// spirit as server.js's runtime-dir sweep.
const SWEEP_INTERVAL_MS = 10 * 60 * 1000;
setInterval(() => {
  const now = Date.now();
  for (const [key, bucket] of buckets) {
    if (now - bucket.windowStart > bucket.windowMs) buckets.delete(key);
  }
}, SWEEP_INTERVAL_MS).unref();

// windowMs/max define the limit; keyPrefix namespaces this limiter's buckets
// from any other limiter keyed by the same IP. Keyed by req.ip -- requires
// `app.set('trust proxy', ...)` upstream (see server.js) to reflect the real
// client address rather than the Caddy reverse-proxy container's own IP.
function rateLimit({ windowMs, max, keyPrefix }) {
  return (req, res, next) => {
    const key = `${keyPrefix}:${req.ip}`;
    const now = Date.now();
    let bucket = buckets.get(key);
    if (!bucket || now - bucket.windowStart > windowMs) {
      bucket = { windowStart: now, windowMs, count: 0 };
      buckets.set(key, bucket);
    }
    bucket.count += 1;
    if (bucket.count > max) {
      return res.status(429).json({ error: 'Too many requests -- please try again later' });
    }
    next();
  };
}

module.exports = { rateLimit };
