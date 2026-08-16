const express = require('express');
const fs = require('fs');
const path = require('path');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { currentTier } = require('../utils/tier');
const { DATA_DIR } = require('../config/paths');

const router = express.Router();

const FREE_TIER_LIMIT = 3;

// Same JSONL file scripts/16_shot_verification/shot_contact_training_log.py
// reads/writes -- a user flag is real human ground truth for that
// teacher-student loop, appended in the same shape (source='user_flag',
// no paired student prediction at flag time, so agreed=null -- see that
// module's agreement_rate()/should_trust_student() for why those are
// excluded from the trust math but still kept as training data).
const SHOT_VERIFICATION_LOG_PATH = path.join(DATA_DIR, '16_shot_verification', 'shot_contact_training_log.jsonl');

function logUserFlag(analysisId, isRealShot) {
  fs.mkdirSync(path.dirname(SHOT_VERIFICATION_LOG_PATH), { recursive: true });
  const record = {
    timestamp: Date.now() / 1000,
    student_pick: null,
    teacher_pick: isRealShot,
    agreed: null,
    source: 'user_flag',
    student_meta: { analysis_id: analysisId },
  };
  fs.appendFileSync(SHOT_VERIFICATION_LOG_PATH, JSON.stringify(record) + '\n');
}

// Same JSONL file scripts/14_shot_classifier/shot_classifier_training_log.py
// reads/writes -- field names match THAT log's shape (scores/student_pick/
// claude_pick/agreed), not shot_contact_training_log.py's (teacher_pick).
// A user's shot-type correction has no paired student prediction at
// correction time, so agreed=null -- same reasoning as logUserFlag() above,
// and that module's agreement_rate()/should_trust_student() were updated
// this session to exclude agreed=null records from the trust math.
const SHOT_CLASSIFIER_LOG_PATH = path.join(DATA_DIR, '14_shot_classifier', 'shot_classifier_training_log.jsonl');
const SHOT_TYPES = ['forehand', 'backhand', 'serve'];

function logShotTypeCorrection(analysisId, correctedShotType) {
  fs.mkdirSync(path.dirname(SHOT_CLASSIFIER_LOG_PATH), { recursive: true });
  const record = {
    timestamp: Date.now() / 1000,
    scores: null,
    student_pick: null,
    claude_pick: correctedShotType,
    agreed: null,
    source: 'user_flag',
    student_meta: { analysis_id: analysisId },
  };
  fs.appendFileSync(SHOT_CLASSIFIER_LOG_PATH, JSON.stringify(record) + '\n');
}

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
    flagged_not_shot: !!row.flagged_not_shot,
    confirmed_real_shot: !!row.confirmed_real_shot,
    result: JSON.parse(row.result_json),
  };
}

// Per-frame pose/racket trajectories exist only to drive the skeleton/racket
// overlays in Sync Compare -- the History list never renders them, and
// they're the overwhelming majority of each row's byte size (confirmed
// live: ~25KB of a ~28KB average row, on a 105-row real account this
// blew the list payload out to ~2.9MB and made the phone visibly stall).
// Strip them for the list response; GET /history/:id below returns the
// untouched full result for whichever single item is actually opened.
function stripHeavyOverlays(result) {
  const { user_overlay_trajectory, racket_overlay_trajectory, ...rest } = result;
  return {
    ...rest,
    matches: (result.matches ?? []).map(({ pro_overlay_trajectory, pro_racket_overlay_trajectory, ...m }) => m),
  };
}

function serializeRowSummary(row) {
  const full = serializeRow(row);
  return { ...full, result: stripHeavyOverlays(full.result) };
}

router.get('/history', requireAuth, (req, res) => {
  const tier = currentTier(req.user.id);
  const rows = db.prepare('SELECT * FROM analyses WHERE user_id = ? ORDER BY created_at DESC').all(req.user.id);
  res.json({
    analyses: rows.map(serializeRowSummary),
    count: rows.length,
    limit: limitForTier(tier),
  });
});

// Full result (including overlay trajectories) for a single saved analysis
// -- fetched on demand when a History card is actually opened, instead of
// every row carrying that weight in the list response above.
router.get('/history/:id', requireAuth, (req, res) => {
  const row = db.prepare('SELECT * FROM analyses WHERE id = ? AND user_id = ?').get(req.params.id, req.user.id);
  if (!row) return res.status(404).json({ error: 'Analysis not found' });
  res.json(serializeRow(row));
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
    top.tips?.[0]?.tip_text ?? null,
    JSON.stringify(result)
  );

  const row = db.prepare('SELECT * FROM analyses WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json(serializeRow(row));
});

router.patch('/history/:id', requireAuth, (req, res) => {
  const { flagged_not_shot, confirmed_real_shot, shot_type } = req.body || {};
  const hasShotType = typeof shot_type === 'string';
  if (typeof flagged_not_shot !== 'boolean' && typeof confirmed_real_shot !== 'boolean' && !hasShotType) {
    return res.status(400).json({ error: 'flagged_not_shot, confirmed_real_shot (boolean), or shot_type (string) is required' });
  }
  if (hasShotType && !SHOT_TYPES.includes(shot_type)) {
    return res.status(400).json({ error: `shot_type must be one of: ${SHOT_TYPES.join(', ')}` });
  }

  const row = db.prepare('SELECT * FROM analyses WHERE id = ? AND user_id = ?').get(req.params.id, req.user.id);
  if (!row) {
    return res.status(404).json({ error: 'Analysis not found' });
  }

  // The two verdicts are mutually exclusive -- confirming "real" clears any
  // "not a shot" flag and vice versa, so the UI never shows both at once.
  const nextFlagged = typeof flagged_not_shot === 'boolean'
    ? flagged_not_shot
    : (confirmed_real_shot ? false : !!row.flagged_not_shot);
  const nextConfirmed = typeof confirmed_real_shot === 'boolean'
    ? confirmed_real_shot
    : (flagged_not_shot ? false : !!row.confirmed_real_shot);
  const nextShotType = hasShotType ? shot_type : row.shot_type;

  db.prepare('UPDATE analyses SET flagged_not_shot = ?, confirmed_real_shot = ?, shot_type = ? WHERE id = ?')
    .run(nextFlagged ? 1 : 0, nextConfirmed ? 1 : 0, nextShotType, row.id);

  // Only log a genuinely new verdict/correction as a training example --
  // toggling either flag back off, or "correcting" to the same type it
  // already was, isn't a real label in either direction.
  try {
    if (nextFlagged && !row.flagged_not_shot) {
      logUserFlag(row.id, false);
    } else if (nextConfirmed && !row.confirmed_real_shot) {
      logUserFlag(row.id, true);
    }
    if (hasShotType && shot_type !== row.shot_type) {
      logShotTypeCorrection(row.id, shot_type);
    }
  } catch (e) {
    console.error('[history] failed to log user verdict/correction for training:', e);
    // Non-fatal -- the flag/confirm/correction itself already saved, this is just training data.
  }

  const updated = db.prepare('SELECT * FROM analyses WHERE id = ?').get(row.id);
  res.json(serializeRow(updated));
});

router.delete('/history/:id', requireAuth, (req, res) => {
  const info = db.prepare('DELETE FROM analyses WHERE id = ? AND user_id = ?').run(req.params.id, req.user.id);
  if (info.changes === 0) {
    return res.status(404).json({ error: 'Analysis not found' });
  }
  res.status(204).end();
});

module.exports = router;
