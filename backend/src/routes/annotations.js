const express = require('express');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');

const router = express.Router();

// Decoupled from coach.js/friends.js on purpose -- checks both linkage
// types directly rather than importing across route files, matching this
// codebase's existing pattern of each route file owning its own
// access-check helpers (see isLinked() in coach.js, isFriends() in
// friends.js). Access mirrors analysis *view* access generally: the owner,
// a linked coach, or a friend the analysis was explicitly shared with.
function canAccessAnalysis(userId, analysisId) {
  const analysis = db.prepare('SELECT user_id FROM analyses WHERE id = ?').get(analysisId);
  if (!analysis) return false;
  if (analysis.user_id === userId) return true;

  const isCoach = db.prepare('SELECT 1 FROM coach_links WHERE coach_id = ? AND student_id = ?')
    .get(userId, analysis.user_id);
  if (isCoach) return true;

  const isSharedWith = db.prepare('SELECT 1 FROM shared_analyses WHERE analysis_id = ? AND friend_id = ?')
    .get(analysisId, userId);
  return !!isSharedWith;
}

router.get('/analyses/:analysisId/annotations', requireAuth, (req, res) => {
  const analysisId = parseInt(req.params.analysisId, 10);
  if (!canAccessAnalysis(req.user.id, analysisId)) {
    return res.status(403).json({ error: 'Not authorized to view annotations on this analysis' });
  }

  const rows = db.prepare(`
    SELECT sa.author_id, u.name AS author_name, sa.pane_a_strokes, sa.pane_b_strokes, sa.updated_at
    FROM swing_annotations sa
    JOIN users u ON u.id = sa.author_id
    WHERE sa.analysis_id = ?
    ORDER BY sa.updated_at DESC
  `).all(analysisId);

  res.json({
    annotations: rows.map((row) => ({
      author_id: row.author_id,
      author_name: row.author_name,
      pane_a_strokes: JSON.parse(row.pane_a_strokes),
      pane_b_strokes: JSON.parse(row.pane_b_strokes),
      updated_at: row.updated_at,
    })),
  });
});

router.put('/analyses/:analysisId/annotations', requireAuth, (req, res) => {
  const analysisId = parseInt(req.params.analysisId, 10);
  const { paneAStrokes, paneBStrokes } = req.body || {};

  if (!canAccessAnalysis(req.user.id, analysisId)) {
    return res.status(403).json({ error: 'Not authorized to annotate this analysis' });
  }
  if (!Array.isArray(paneAStrokes) || !Array.isArray(paneBStrokes)) {
    return res.status(400).json({ error: 'paneAStrokes and paneBStrokes must be arrays' });
  }

  db.prepare(`
    INSERT INTO swing_annotations (analysis_id, author_id, pane_a_strokes, pane_b_strokes, updated_at)
    VALUES (?, ?, ?, ?, datetime('now'))
    ON CONFLICT(analysis_id, author_id) DO UPDATE SET
      pane_a_strokes = excluded.pane_a_strokes,
      pane_b_strokes = excluded.pane_b_strokes,
      updated_at = excluded.updated_at
  `).run(analysisId, req.user.id, JSON.stringify(paneAStrokes), JSON.stringify(paneBStrokes));

  res.status(200).json({ saved: true });
});

module.exports = router;
