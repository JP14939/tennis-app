const express = require('express');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { currentTier } = require('../utils/tier');

const router = express.Router();

const FREE_TIER_LIMIT = 3;

function limitForTier(tier) {
  return tier === 'premium' ? null : FREE_TIER_LIMIT;
}

function serializeRow(row) {
  return {
    id: row.id,
    shot_type: row.shot_type,
    similarity: row.similarity,
    pro_id: row.pro_id,
    angle_label: row.angle_label,
    tip: row.tip,
    created_at: row.created_at,
    result: JSON.parse(row.result_json),
  };
}

router.get('/history', requireAuth, (req, res) => {
  const tier = currentTier(req.user.id);
  const rows = db.prepare('SELECT * FROM analyses WHERE user_id = ? ORDER BY created_at DESC').all(req.user.id);
  res.json({
    analyses: rows.map(serializeRow),
    count: rows.length,
    limit: limitForTier(tier),
  });
});

router.post('/history', requireAuth, (req, res) => {
  const result = req.body || {};
  const { shotType } = result;
  if (!shotType) {
    return res.status(400).json({ error: 'shotType is required' });
  }

  const tier = currentTier(req.user.id);
  const limit = limitForTier(tier);
  if (limit !== null) {
    const { count } = db.prepare('SELECT COUNT(*) AS count FROM analyses WHERE user_id = ?').get(req.user.id);
    if (count >= limit) {
      return res.status(403).json({
        error: `Free plan is limited to ${limit} saved shots — upgrade to Premium to save unlimited.`,
        code: 'HISTORY_LIMIT',
      });
    }
  }

  const top = result.matches?.[0] || {};
  const info = db.prepare(
    `INSERT INTO analyses (user_id, shot_type, similarity, pro_id, angle_label, tip, result_json)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  ).run(
    req.user.id,
    shotType,
    top.overall_score ?? top.similarity ?? 0,
    top.pro_id ?? null,
    result.angle_label ?? null,
    top.tips?.[0] ?? null,
    JSON.stringify(result)
  );

  const row = db.prepare('SELECT * FROM analyses WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json(serializeRow(row));
});

router.delete('/history/:id', requireAuth, (req, res) => {
  const info = db.prepare('DELETE FROM analyses WHERE id = ? AND user_id = ?').run(req.params.id, req.user.id);
  if (info.changes === 0) {
    return res.status(404).json({ error: 'Analysis not found' });
  }
  res.status(204).end();
});

module.exports = router;
