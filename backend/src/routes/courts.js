const express = require('express');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { sendPushNotification } = require('../utils/pushNotifications');
const { seedCourtsNear } = require('../utils/overpassCourts');

const router = express.Router();

const EARTH_RADIUS_KM = 6371;
const DEFAULT_RADIUS_KM = 20;
// Independent confirmations a user-dropped pin needs before it's trusted
// enough to show as a normal (verified) court to everyone.
const CONFIRMATION_THRESHOLD = 2;

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
    WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
  `).all(userId, userId, lat - latDelta, lat + latDelta, lng - lngDelta, lng + lngDelta);

  return candidates
    .map((c) => ({
      ...c,
      already_confirmed: !!c.already_confirmed,
      club_already_watched: !!c.club_already_watched,
      distance_km: Math.round(haversineKm(lat, lng, c.latitude, c.longitude) * 10) / 10,
    }))
    .filter((c) => c.distance_km <= radiusKm)
    .sort((a, b) => a.distance_km - b.distance_km);
}

router.get('/courts', requireAuth, async (req, res) => {
  const lat = parseFloat(req.query.lat);
  const lng = parseFloat(req.query.lng);
  const parsedRadiusKm = parseFloat(req.query.radiusKm);
  const radiusKm = Number.isNaN(parsedRadiusKm) ? DEFAULT_RADIUS_KM : parsedRadiusKm;

  if (Number.isNaN(lat) || Number.isNaN(lng)) {
    return res.status(400).json({ error: 'lat and lng are required' });
  }

  let courts = queryNearbyCourts(lat, lng, radiusKm, req.user.id);

  // Self-heal: nobody has ever queried this area before, so the local
  // `courts` table has nothing for it -- lazily pull real courts from OSM
  // once, then re-query. Best-effort: if Overpass is unreachable/rate-limited
  // we just fall back to an empty result rather than failing the request.
  if (courts.length === 0) {
    try {
      await seedCourtsNear(lat, lng, radiusKm);
      courts = queryNearbyCourts(lat, lng, radiusKm, req.user.id);
    } catch (err) {
      console.error('Lazy court seed failed:', err.message);
    }
  }

  res.json({ courts });
});

router.post('/courts', requireAuth, (req, res) => {
  const { name, latitude, longitude } = req.body || {};
  if (!name || !name.trim()) {
    return res.status(400).json({ error: 'Court name is required' });
  }
  if (typeof latitude !== 'number' || typeof longitude !== 'number') {
    return res.status(400).json({ error: 'latitude and longitude are required' });
  }

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

const COST_INFO_MAX_LENGTH = 500;

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
  if (cost_info !== null && cost_info !== undefined) {
    if (typeof cost_info !== 'string') {
      return res.status(400).json({ error: 'cost_info must be a string' });
    }
    if (cost_info.length > COST_INFO_MAX_LENGTH) {
      return res.status(400).json({ error: `cost_info must be ${COST_INFO_MAX_LENGTH} characters or fewer` });
    }
  }
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
  if (!start_time) {
    return res.status(400).json({ error: 'start_time is required' });
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
