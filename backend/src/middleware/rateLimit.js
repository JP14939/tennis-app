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
// from any other limiter keyed by the same value. Keyed by req.ip by default
// -- requires `app.set('trust proxy', ...)` upstream (see server.js) to
// reflect the real client address rather than the Caddy reverse-proxy
// container's own IP. `keyGenerator` lets a route key by something else
// instead (e.g. the authenticated user id, for a limiter that must survive
// the caller rotating IPs/accounts less easily than an IP-only key would).
// Weighted sliding-window-counter approximation, not a true rolling log --
// the module comment above (and every call site's own reasoning, e.g. "15
// login attempts per 15 minutes") describes a sliding bound, but the bucket
// used to fully reset the moment `now - windowStart > windowMs`, which is a
// fixed/tumbling window: a caller could exhaust `max` right before a reset
// and another `max` right after, getting up to 2x the intended ceiling in a
// short burst spanning the boundary. Carrying the previous window's count,
// weighted by how much of it still overlaps the current windowMs, keeps the
// count for any windowMs-wide slice close to the real sliding-window bound
// without needing a full timestamp log per key.
function rateLimit({ windowMs, max, keyPrefix, keyGenerator = (req) => req.ip }) {
  return (req, res, next) => {
    const key = `${keyPrefix}:${keyGenerator(req)}`;
    const now = Date.now();
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = { windowStart: now, windowMs, count: 0, prevCount: 0 };
      buckets.set(key, bucket);
    } else if (now - bucket.windowStart >= 2 * windowMs) {
      // Idle for at least a full extra window -- the previous window is
      // entirely out of range, so there's nothing left to weight in.
      bucket.windowStart = now;
      bucket.count = 0;
      bucket.prevCount = 0;
    } else if (now - bucket.windowStart >= windowMs) {
      bucket.windowStart += windowMs;
      bucket.prevCount = bucket.count;
      bucket.count = 0;
    }

    const elapsed = now - bucket.windowStart;
    const overlap = Math.max(0, (windowMs - elapsed) / windowMs);
    const weightedCount = bucket.prevCount * overlap + bucket.count;
    if (weightedCount + 1 > max) {
      return res.status(429).json({ error: 'Too many requests -- please try again later' });
    }
    bucket.count += 1;
    next();
  };
}

module.exports = { rateLimit };
