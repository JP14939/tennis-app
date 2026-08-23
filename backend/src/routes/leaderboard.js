const express = require('express');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { requireAdmin } = require('../middleware/requireAdmin');
const { SHOT_TYPES } = require('../config/shotTypes');

const router = express.Router();

function validateShotType(req, res) {
  const shotType = req.query.shotType || req.body?.shotType;
  if (!SHOT_TYPES.includes(shotType)) {
    res.status(400).json({ error: `shotType must be one of ${SHOT_TYPES.join(', ')}` });
    return null;
  }
  return shotType;
}

router.get('/leaderboard/friends', requireAuth, (req, res) => {
  const shotType = validateShotType(req, res);
  if (!shotType) return;

  const myId = req.user.id;
  const friendIds = db.prepare(`
    SELECT CASE WHEN user_a_id = ? THEN user_b_id ELSE user_a_id END AS friend_id
    FROM friend_links WHERE user_a_id = ? OR user_b_id = ?
  `).all(myId, myId, myId).map((r) => r.friend_id);

  const ids = [myId, ...friendIds];
  const rows = db.prepare(`
    SELECT u.id AS user_id, u.name, u.username, MAX(a.similarity) AS score
    FROM users u
    JOIN analyses a ON a.user_id = u.id AND a.shot_type = ? AND a.flagged_not_shot = 0
    WHERE u.id IN (${ids.map(() => '?').join(',')})
    GROUP BY u.id
    ORDER BY score DESC
  `).all(shotType, ...ids);

  res.json({
    leaderboard: rows.map((r) => ({ ...r, is_me: r.user_id === myId })),
  });
});

router.get('/leaderboard/worldwide', requireAuth, (req, res) => {
  const shotType = validateShotType(req, res);
  if (!shotType) return;

  const myId = req.user.id;
  const userRows = db.prepare(`
    SELECT u.id AS user_id, u.name, u.username, MAX(a.similarity) AS score
    FROM users u
    JOIN analyses a ON a.user_id = u.id AND a.shot_type = ? AND a.flagged_not_shot = 0
    GROUP BY u.id
  `).all(shotType).map((r) => ({ ...r, type: 'user', is_me: r.user_id === myId }));

  const celebRows = db.prepare(
    `SELECT id, name, score, note FROM celebrity_scores WHERE shot_type = ?`
  ).all(shotType).map((r) => ({ ...r, type: 'celebrity', is_me: false }));

  const leaderboard = [...userRows, ...celebRows].sort((a, b) => b.score - a.score);
  res.json({ leaderboard });
});

router.get('/leaderboard/celebrities', requireAuth, requireAdmin, (req, res) => {
  const rows = db.prepare('SELECT * FROM celebrity_scores ORDER BY shot_type, score DESC').all();
  res.json({ celebrities: rows });
});

router.post('/leaderboard/celebrities', requireAuth, requireAdmin, (req, res) => {
  const { name, score, note } = req.body || {};
  const shotType = validateShotType(req, res);
  if (!shotType) return;
  if (!name || !name.trim() || typeof score !== 'number') {
    return res.status(400).json({ error: 'name and score are required' });
  }

  const info = db.prepare(
    'INSERT INTO celebrity_scores (name, shot_type, score, note, added_by) VALUES (?, ?, ?, ?, ?)'
  ).run(name.trim(), shotType, score, note ?? null, req.user.id);

  const celebrity = db.prepare('SELECT * FROM celebrity_scores WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json({ celebrity });
});

router.delete('/leaderboard/celebrities/:id', requireAuth, requireAdmin, (req, res) => {
  db.prepare('DELETE FROM celebrity_scores WHERE id = ?').run(req.params.id);
  res.status(204).end();
});

module.exports = router;
