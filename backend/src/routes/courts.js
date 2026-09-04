const express = require('express');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { sendPushNotification } = require('../utils/pushNotifications');
const { seedCourtsNear } = require('../utils/overpassCourts');
const {
  MAX_LENGTHS, isLatitude, isLongitude, isText, isOptionalText, isIsoDateTime,
} = require('../domain/invariants');
const { validate, optional } = require('../validation/validateBody');

const router = express.Router();

const EARTH_RADIUS_KM = 6371;
const DEFAULT_RADIUS_KM = 20;
const MAX_RADIUS_KM = 100;
// Independent confirmations a user-dropped pin needs before it's trusted
// enough to show as a normal (verified) court to everyone.
const CONFIRMATION_THRESHOLD = 2;

// In-process, best-effort memory of areas that were just seeded and came
// back with nothing -- without this, every request for a genuinely
// court-less area (rural spot, GPS glitch, ocean) re-triggers a live
// Overpass call on every single request, forever, since an empty result
// always looks like "never queried before" to the self-heal check below.
// Repeated hits risk Overpass rate-limiting/banning this backend's shared
// IP, which would degrade court search for every user, not just this area.
// Keyed on a coarse lat/lng bucket (~1.1km) so nearby requests share a
// cache entry; resets on server restart, which is fine -- worst case is
// one real Overpass call per area per process lifetime plus this TTL.
const SEED_MISS_TTL_MS = 60 * 60 * 1000;
const recentEmptySeedAreas = new Map();

// recentEmptySeedAreas grew one entry per distinct empty-result coordinate
// bucket forever -- wasRecentlySeededEmpty only ever READ an entry's
// staleness, never removed one, and nothing else swept the map (unlike
// middleware/rateLimit.js's own buckets Map, which sweeps on an interval).
// A client hitting many distinct ocean/rural coordinates (this route has no
// rate limit) could grow this unboundedly and eventually exhaust process
// memory. Prune stale entries on read, plus a periodic sweep as a backstop
// for keys that are never looked up again.
const SEED_MISS_SWEEP_INTERVAL_MS = 60 * 60 * 1000;
setInterval(() => {
  const now = Date.now();
  for (const [key, seededAt] of recentEmptySeedAreas) {
    if (now - seededAt >= SEED_MISS_TTL_MS) recentEmptySeedAreas.delete(key);
  }
}, SEED_MISS_SWEEP_INTERVAL_MS).unref();

function seedAreaKey(lat, lng) {
  return `${Math.round(lat * 100)},${Math.round(lng * 100)}`;
}

function wasRecentlySeededEmpty(lat, lng) {
  const key = seedAreaKey(lat, lng);
  const seededAt = recentEmptySeedAreas.get(key);
  if (seededAt === undefined) return false;
  if (Date.now() - seededAt >= SEED_MISS_TTL_MS) {
    recentEmptySeedAreas.delete(key);
    return false;
  }
  return true;
}

function markSeededEmpty(lat, lng) {
  recentEmptySeedAreas.set(seedAreaKey(lat, lng), Date.now());
}

// Two or more concurrent requests for the same never-before-seeded area
// each saw an empty local result and no recentEmptySeedAreas entry yet, so
// each independently kicked off its own live Overpass call for the same
// bounding box -- exactly the "risk rate-limiting/banning this backend's
// shared IP" scenario the cache above exists to prevent, just not covered
// for the concurrent case. Track one in-flight seed Promise per area key so
// concurrent callers await the same request instead of each starting one.
const inFlightSeeds = new Map();

function seedCourtsNearOnce(lat, lng, radiusKm) {
  const key = seedAreaKey(lat, lng);
  let promise = inFlightSeeds.get(key);
  if (!promise) {
    promise = seedCourtsNear(lat, lng, radiusKm).finally(() => inFlightSeeds.delete(key));
    inFlightSeeds.set(key, promise);
  }
  return promise;
}

function haversineKm(lat1, lng1, lat2, lng2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function queryNearbyCourts(lat, lng, radiusKm, userId) {
  // Cheap bounding-box prefilter in SQL (degrees, not exact -- lng shrinks
  // toward the poles, so this box is intentionally a bit generous), then an
  // exact haversine distance filter/sort in JS. Fine at this dataset size
  // (a local-area OSM seed); would need a spatial index at real scale.
  const latDelta = radiusKm / 111;
  const lngDelta = radiusKm / (111 * Math.cos((lat * Math.PI) / 180) || 1);

  const candidates = db.prepare(`
    SELECT c.*,
      (SELECT COUNT(*) FROM court_confirmations cc WHERE cc.court_id = c.id) AS confirmation_count,
      EXISTS(SELECT 1 FROM court_confirmations cc WHERE cc.court_id = c.id AND cc.user_id = ?) AS already_confirmed,
      cl.id AS club_id, cl.name AS club_name,
      EXISTS(SELECT 1 FROM club_watches cw WHERE cw.club_id = cl.id AND cw.user_id = ?) AS club_already_watched,
      (SELECT COUNT(*) FROM club_courts cc2 WHERE cc2.club_id = cl.id) AS club_court_count
    FROM courts c
    LEFT JOIN club_courts clc ON clc.court_id = c.id
    LEFT JOIN clubs cl ON cl.id = clc.club_id
    -- Qualified with c. -- clubs also has its own latitude/longitude
    -- columns, so once the LEFT JOIN brings clubs into scope, an
    -- unqualified reference is genuinely ambiguous to SQLite (this was a
    -- live SQLITE_ERROR: "ambiguous column name: latitude", not a network
    -- issue, despite the frontend showing a generic connection error for
    -- it). We want the court's own coordinates for this bounding box.
    WHERE c.latitude BETWEEN ? AND ? AND c.longitude BETWEEN ? AND ?
  `).all(userId, userId, lat - latDelta, lat + latDelta, lng - lngDelta, lng + lngDelta);

  return candidates
    .map((c) => {
      const exactDistanceKm = haversineKm(lat, lng, c.latitude, c.longitude);
      return {
        ...c,
        already_confirmed: !!c.already_confirmed,
        club_already_watched: !!c.club_already_watched,
        exactDistanceKm,
        // Rounded for display only -- filtering/sorting on this instead of
        // exactDistanceKm let a court up to 0.05km outside radiusKm round
        // down to it and be wrongly admitted.
        distance_km: Math.round(exactDistanceKm * 10) / 10,
      };
    })
    .filter((c) => c.exactDistanceKm <= radiusKm)
    .sort((a, b) => a.exactDistanceKm - b.exactDistanceKm)
    .map(({ exactDistanceKm, ...c }) => c);
}

router.get('/courts', requireAuth, async (req, res) => {
  const lat = parseFloat(req.query.lat);
  const lng = parseFloat(req.query.lng);
  const parsedRadiusKm = parseFloat(req.query.radiusKm);
  // A radiusKm <= 0 (e.g. a negative value) makes latDelta/lngDelta negative,
  // producing an inverted `BETWEEN low AND high` clause that always matches
  // zero rows -- courts silently comes back empty regardless of what's
  // actually in the DB, and since queryNearbyCourts().length === 0 is then
  // always true, it re-triggers the Overpass self-heal seed call on EVERY
  // request for that lat/lng instead of once.
  // Capped so a caller can't force a continent/world-scale bounding box into
  // a single query or Overpass call -- every other geo input here (lat/lng)
  // already has a domain bound; radiusKm previously only had a `> 0` floor.
  const radiusKm = Number.isFinite(parsedRadiusKm) && parsedRadiusKm > 0
    ? Math.min(parsedRadiusKm, MAX_RADIUS_KM)
    : DEFAULT_RADIUS_KM;

  // Unlike POST /courts (which validates via isLatitude/isLongitude), this
  // route only ever checked for NaN -- an out-of-range value like lat=9999
  // still passed, and fed straight into queryNearbyCourts()'s bounding-box
  // arithmetic and, on a cache miss, into seedCourtsNearOnce()'s live
  // Overpass API call with a nonsensical bounding box. Same real-world-value
  // reasoning as isLatitude/isLongitude's own comment: a coordinate outside
  // ±90/±180 isn't a valid location, so this should 400 the same way the
  // write path already does rather than silently querying garbage.
  if (!isLatitude(lat) || !isLongitude(lng)) {
    return res.status(400).json({ error: 'lat must be a number between -90 and 90, lng between -180 and 180' });
  }

  let courts = queryNearbyCourts(lat, lng, radiusKm, req.user.id);

  // Self-heal: nobody has ever queried this area before, so the local
  // `courts` table has nothing for it -- lazily pull real courts from OSM
  // once, then re-query. Best-effort: if Overpass is unreachable/rate-limited
  // we just fall back to an empty result rather than failing the request.
  if (courts.length === 0 && !wasRecentlySeededEmpty(lat, lng)) {
    try {
      // Seed at MAX_RADIUS_KM regardless of this request's radiusKm.
      // seedAreaKey()/wasRecentlySeededEmpty() (and inFlightSeeds) are keyed
      // on coordinates alone, with no radius in the key -- seeding at a
      // narrower radius than MAX_RADIUS_KM let a later, wider-radius request
      // at the same coordinates find `wasRecentlySeededEmpty` already true
      // and skip the self-heal entirely, even though Overpass was never
      // actually asked about the extra distance and might have real courts
      // there. Always seeding at the true ceiling keeps the empty-result
      // cache (and the in-flight dedup) valid for any radius a caller asks
      // for, not just the one that happened to trigger it first.
      await seedCourtsNearOnce(lat, lng, MAX_RADIUS_KM);
      courts = queryNearbyCourts(lat, lng, radiusKm, req.user.id);
      if (courts.length === 0) markSeededEmpty(lat, lng);
    } catch (err) {
      console.error('Lazy court seed failed:', err.message);
    }
  }

  res.json({ courts });
});

router.post('/courts', requireAuth, (req, res) => {
  const { name, latitude, longitude } = req.body || {};

  // courts is a SHARED table (~33k rows) that every user's map reads, so a
  // bad pin isn't just this user's problem. A number alone wasn't enough:
  // a latitude of 5000 passed the old typeof check, then made haversineKm()
  // return a meaningless distance for every nearby-court query it appeared in.
  const bad = validate([
    ['name', name, isText(MAX_LENGTHS.courtName), `must be a name of ${MAX_LENGTHS.courtName} characters or fewer`],
    ['latitude', latitude, isLatitude, 'must be a number between -90 and 90'],
    ['longitude', longitude, isLongitude, 'must be a number between -180 and 180'],
  ]);
  if (bad) return res.status(400).json(bad);

  // User-dropped pins start unverified -- they only show as a trusted court
  // once CONFIRMATION_THRESHOLD other users independently confirm it via
  // POST /courts/:id/confirm below.
  const info = db.prepare(
    `INSERT INTO courts (name, latitude, longitude, source, verified, submitted_by) VALUES (?, ?, ?, 'user', 0, ?)`
  ).run(name.trim(), latitude, longitude, req.user.id);

  const court = db.prepare('SELECT * FROM courts WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json({ court: { ...court, confirmation_count: 0, already_confirmed: false } });
});

router.post('/courts/:id/confirm', requireAuth, (req, res) => {
  const court = db.prepare('SELECT * FROM courts WHERE id = ?').get(req.params.id);
  if (!court) return res.status(404).json({ error: 'Court not found' });
  if (court.submitted_by === req.user.id) {
    return res.status(400).json({ error: "You can't confirm a court you submitted yourself" });
  }

  // Insert + count + conditional verify-flip wrapped as one synchronous
  // transaction -- same check-then-write shape as history.js's
  // insertAnalysis. Unwrapped, two concurrent confirmations that both land
  // on count == CONFIRMATION_THRESHOLD - 1 could both read the same stale
  // count and disagree on whether this confirmation was the one that
  // crossed the threshold.
  const confirmCourt = db.transaction(() => {
    db.prepare('INSERT OR IGNORE INTO court_confirmations (court_id, user_id) VALUES (?, ?)')
      .run(court.id, req.user.id);

    const { count } = db.prepare(
      'SELECT COUNT(*) AS count FROM court_confirmations WHERE court_id = ?'
    ).get(court.id);

    if (!court.verified && count >= CONFIRMATION_THRESHOLD) {
      db.prepare('UPDATE courts SET verified = 1 WHERE id = ?').run(court.id);
    }

    return count;
  });

  const count = confirmCourt();
  const updated = db.prepare('SELECT * FROM courts WHERE id = ?').get(court.id);
  res.json({ court: { ...updated, confirmation_count: count, already_confirmed: true } });
});

// Deliberately open to any authenticated user, not just the court's
// submitter -- same crowd-sourced trust model as POST /courts/:id/confirm
// above (anyone who's actually played there can correct stale pricing).
// What WAS a real bug: no validation at all. `cost_info` bound directly to
// the UPDATE meant a non-string body (e.g. `{cost_info: {...}}`) threw
// inside better-sqlite3, and there was no length cap, so a malicious body
// could write an arbitrarily large string into a field served to every
// user who views this court.
router.patch('/courts/:id/cost', requireAuth, (req, res) => {
  const { cost_info } = req.body || {};
  const bad = validate([
    ['cost_info', cost_info, isOptionalText(MAX_LENGTHS.costInfo), `must be a string of ${MAX_LENGTHS.costInfo} characters or fewer`],
  ]);
  if (bad) return res.status(400).json(bad);

  const court = db.prepare('SELECT * FROM courts WHERE id = ?').get(req.params.id);
  if (!court) return res.status(404).json({ error: 'Court not found' });

  db.prepare(
    `UPDATE courts SET cost_info = ?, cost_updated_by = ?, cost_updated_at = datetime('now') WHERE id = ?`
  ).run(cost_info?.trim() || null, req.user.id, court.id);

  res.json({ court: db.prepare('SELECT * FROM courts WHERE id = ?').get(court.id) });
});

router.get('/courts/watched', requireAuth, (req, res) => {
  const courts = db.prepare(`
    SELECT c.* FROM courts c
    JOIN court_watches w ON w.court_id = c.id
    WHERE w.user_id = ?
    ORDER BY w.created_at DESC
  `).all(req.user.id);
  const clubs = db.prepare(`
    SELECT cl.* FROM clubs cl
    JOIN club_watches w ON w.club_id = cl.id
    WHERE w.user_id = ?
    ORDER BY w.created_at DESC
  `).all(req.user.id);
  res.json({ courts, clubs });
});

router.post('/courts/:id/watch', requireAuth, (req, res) => {
  const court = db.prepare('SELECT id FROM courts WHERE id = ?').get(req.params.id);
  if (!court) return res.status(404).json({ error: 'Court not found' });

  db.prepare(`INSERT OR IGNORE INTO court_watches (user_id, court_id) VALUES (?, ?)`)
    .run(req.user.id, court.id);
  res.status(204).end();
});

router.delete('/courts/:id/watch', requireAuth, (req, res) => {
  db.prepare('DELETE FROM court_watches WHERE user_id = ? AND court_id = ?')
    .run(req.user.id, req.params.id);
  res.status(204).end();
});

// Club-level watch -- resolved server-side from the court id so the
// frontend only ever deals in court ids, same shape as the per-court watch
// endpoints above.
router.post('/courts/:id/club/watch', requireAuth, (req, res) => {
  const membership = db.prepare('SELECT club_id FROM club_courts WHERE court_id = ?').get(req.params.id);
  if (!membership) return res.status(404).json({ error: "This court isn't part of a club" });

  db.prepare(`INSERT OR IGNORE INTO club_watches (user_id, club_id) VALUES (?, ?)`)
    .run(req.user.id, membership.club_id);
  res.status(204).end();
});

router.delete('/courts/:id/club/watch', requireAuth, (req, res) => {
  const membership = db.prepare('SELECT club_id FROM club_courts WHERE court_id = ?').get(req.params.id);
  if (!membership) return res.status(404).json({ error: "This court isn't part of a club" });

  db.prepare('DELETE FROM club_watches WHERE user_id = ? AND club_id = ?')
    .run(req.user.id, membership.club_id);
  res.status(204).end();
});

router.get('/courts/:id/availability', requireAuth, (req, res) => {
  const posts = db.prepare(`
    SELECT a.*, u.name AS user_name, u.username AS user_username
    FROM availability_posts a
    JOIN users u ON u.id = a.user_id
    WHERE a.court_id = ? AND a.status = 'open'
    ORDER BY a.start_time ASC
  `).all(req.params.id);
  res.json({ posts });
});

router.post('/courts/:id/availability', requireAuth, (req, res) => {
  const { start_time, end_time, note } = req.body || {};

  // start_time is both the ORDER BY key for GET /courts/:id/availability and
  // a date the app renders -- an unparseable string sorted unpredictably and
  // displayed as "Invalid Date" to everyone watching this court.
  const bad = validate([
    ['start_time', start_time, isIsoDateTime, 'must be a valid date/time'],
    ['end_time', end_time, optional(isIsoDateTime), 'must be a valid date/time'],
    ['note', note, isOptionalText(MAX_LENGTHS.availabilityNote), `must be ${MAX_LENGTHS.availabilityNote} characters or fewer`],
  ]);
  if (bad) return res.status(400).json(bad);

  // A session that ends before it starts isn't a validation nicety -- the
  // post is broadcast by push notification to every watcher of this court.
  if (end_time && new Date(end_time) <= new Date(start_time)) {
    return res.status(400).json({ error: 'end_time must be after start_time', field: 'end_time' });
  }

  const court = db.prepare('SELECT * FROM courts WHERE id = ?').get(req.params.id);
  if (!court) return res.status(404).json({ error: 'Court not found' });

  const info = db.prepare(
    `INSERT INTO availability_posts (user_id, court_id, start_time, end_time, note) VALUES (?, ?, ?, ?, ?)`
  ).run(req.user.id, court.id, start_time, end_time ?? null, note ?? null);

  // Broadcast to every other user watching this court, plus anyone watching
  // the club it belongs to (if any) -- confirmed model either way: anyone
  // watching gets notified regardless of friendship or their own stated
  // availability. Club watchers are deduped against direct court watchers
  // so someone watching both doesn't get notified twice for the same post.
  const poster = db.prepare('SELECT name FROM users WHERE id = ?').get(req.user.id);
  const courtWatchers = db.prepare(
    `SELECT user_id FROM court_watches WHERE court_id = ? AND user_id != ?`
  ).all(court.id, req.user.id);

  const notifiedIds = new Set(courtWatchers.map((w) => w.user_id));
  const membership = db.prepare('SELECT club_id FROM club_courts WHERE court_id = ?').get(court.id);
  const clubWatchers = membership
    ? db.prepare(
        `SELECT user_id FROM club_watches WHERE club_id = ? AND user_id != ?`
      ).all(membership.club_id, req.user.id)
    : [];

  const allWatcherIds = new Set([...notifiedIds, ...clubWatchers.map((w) => w.user_id)]);
  for (const user_id of allWatcherIds) {
    sendPushNotification(
      user_id,
      `${poster?.name ?? 'Someone'} is free to play`,
      `${court.name} — tap to see details and message them.`,
      { courtId: court.id }
    );
  }

  const post = db.prepare('SELECT * FROM availability_posts WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json({ post });
});

router.delete('/availability/:id', requireAuth, (req, res) => {
  const post = db.prepare('SELECT * FROM availability_posts WHERE id = ? AND user_id = ?')
    .get(req.params.id, req.user.id);
  if (!post) return res.status(404).json({ error: 'Availability post not found' });

  db.prepare(`UPDATE availability_posts SET status = 'cancelled' WHERE id = ?`).run(post.id);
  res.status(204).end();
});

module.exports = router;
