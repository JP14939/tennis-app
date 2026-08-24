const express = require('express');
const db = require('../db');
const optionalAuth = require('../middleware/optionalAuth');
const requireAuth = require('../middleware/requireAuth');
const { currentTier } = require('../utils/tier');
const { toClipUrl } = require('../utils/drillClips');
const { DRILL_KINDS, isPositiveIntegerId, isDrillKind } = require('../domain/invariants');
const { oneOfMessage } = require('../validation/validateBody');

const router = express.Router();

function isLocked(item, req) {
  if (!item.is_premium) return false;
  const tier = req.user ? currentTier(req.user.id) : 'free';
  return tier !== 'premium';
}

// List view -- locked premium items still appear (so the Lessons segment can
// show what exists, matching PremiumScreen.js's existing locked-card
// pattern) but with video/explanation/emphasis/diagram stripped, never sent
// to a non-premium client even just to be hidden client-side.
function serializeListItem(item, req) {
  const locked = isLocked(item, req);
  return {
    id: item.id,
    kind: item.kind,
    shot_type: item.shot_type,
    title: item.title,
    is_premium: !!item.is_premium,
    locked,
    video_url: locked ? null : toClipUrl(item.video_path),
    explanation: locked ? null : item.explanation,
    emphasis: locked ? null : item.emphasis,
    diagram_tip_id: locked ? null : item.diagram_tip_id,
  };
}

router.get('/drills', optionalAuth, (req, res) => {
  const { kind, shot_type } = req.query;
  if (kind && !isDrillKind(kind)) {
    return res.status(400).json({ error: `kind ${oneOfMessage(DRILL_KINDS)}`, field: 'kind' });
  }
  // A repeated query key (e.g. ?shot_type=forehand&shot_type=backhand) parses
  // to an array via Express/qs -- binding that straight into better-sqlite3's
  // .all(...params) throws "Too many parameter values were provided" (a
  // single '?' placeholder, multiple values spread in), crashing the route
  // with a 500 instead of a clean 400. `kind` was already guarded against
  // this; `shot_type` wasn't.
  if (shot_type !== undefined && typeof shot_type !== 'string') {
    return res.status(400).json({ error: 'shot_type must be a single value' });
  }

  let query = 'SELECT * FROM drill_items WHERE archived = 0';
  const params = [];
  if (kind) { query += ' AND kind = ?'; params.push(kind); }
  if (shot_type) { query += ' AND shot_type = ?'; params.push(shot_type); }
  query += ' ORDER BY sort_order ASC, id ASC';

  const items = db.prepare(query).all(...params);
  res.json({ items: items.map((item) => serializeListItem(item, req)) });
});

router.get('/drills/:id', optionalAuth, (req, res) => {
  const item = db.prepare('SELECT * FROM drill_items WHERE id = ? AND archived = 0').get(req.params.id);
  if (!item) return res.status(404).json({ error: 'Not found' });

  if (isLocked(item, req)) {
    return res.status(403).json({
      error: 'This is a Premium lesson — upgrade to unlock it.',
      code: 'PREMIUM_REQUIRED',
      title: item.title,
    });
  }

  const rawSteps = db.prepare('SELECT * FROM drill_routine_steps WHERE drill_item_id = ? ORDER BY step_order ASC').all(item.id);

  // One grouped query for every step's attempt count instead of one query
  // per step -- same result, fewer round trips as a lesson's step count grows.
  let attemptCounts = {};
  if (req.user && rawSteps.length) {
    const placeholders = rawSteps.map(() => '?').join(',');
    attemptCounts = db.prepare(`
      SELECT step_id, COUNT(*) AS n FROM drill_practice_attempts
      WHERE user_id = ? AND step_id IN (${placeholders})
      GROUP BY step_id
    `).all(req.user.id, ...rawSteps.map((s) => s.id))
      .reduce((acc, row) => { acc[row.step_id] = row.n; return acc; }, {});
  }
  const steps = rawSteps.map((step) => ({ ...step, attempt_count: attemptCounts[step.id] ?? 0 }));

  res.json({
    id: item.id,
    kind: item.kind,
    shot_type: item.shot_type,
    title: item.title,
    is_premium: !!item.is_premium,
    video_url: toClipUrl(item.video_path),
    explanation: item.explanation,
    emphasis: item.emphasis,
    diagram_tip_id: item.diagram_tip_id,
    steps,
  });
});

// Links a practice attempt's real analysis (already created via the normal
// /api/analyse flow) to a routine step -- not a second scoring system, just
// a record of "this analysis was done as practice for this step".
router.post('/drills/:stepId/practice', requireAuth, (req, res) => {
  const { analysisId } = req.body || {};
  if (!isPositiveIntegerId(req.params.stepId)) {
    return res.status(400).json({ error: 'Invalid step id' });
  }
  if (analysisId !== undefined && analysisId !== null && !isPositiveIntegerId(analysisId)) {
    return res.status(400).json({ error: 'analysisId must be a valid analysis id', field: 'analysisId' });
  }

  const step = db.prepare('SELECT * FROM drill_routine_steps WHERE id = ?').get(req.params.stepId);
  if (!step) return res.status(404).json({ error: 'Step not found' });

  // A step's id is only ever handed out via GET /drills/:id, which already
  // 403s a locked (premium, non-premium-user) item before returning its
  // steps -- but nothing stopped a guessed/reused stepId from recording a
  // practice attempt here without going through that gate. Re-check the
  // parent item so this route can't be used to bypass the paywall. Also
  // 403s on a missing parentItem (an orphaned step) rather than silently
  // allowing it through.
  const parentItem = db.prepare('SELECT * FROM drill_items WHERE id = ?').get(step.drill_item_id);
  if (!parentItem || isLocked(parentItem, req)) {
    return res.status(403).json({
      error: 'This is a Premium lesson — upgrade to unlock it.',
      code: 'PREMIUM_REQUIRED',
    });
  }

  if (analysisId !== undefined && analysisId !== null) {
    const analysis = db.prepare('SELECT id FROM analyses WHERE id = ? AND user_id = ?').get(analysisId, req.user.id);
    if (!analysis) return res.status(403).json({ error: 'That analysis does not belong to you' });
  }

  const result = db.prepare(
    'INSERT INTO drill_practice_attempts (user_id, step_id, analysis_id) VALUES (?, ?, ?)'
  ).run(req.user.id, step.id, analysisId ?? null);

  const attemptCount = db.prepare('SELECT COUNT(*) AS n FROM drill_practice_attempts WHERE step_id = ? AND user_id = ?')
    .get(step.id, req.user.id).n;

  res.json({ id: result.lastInsertRowid, attempt_count: attemptCount });
});

module.exports = router;
