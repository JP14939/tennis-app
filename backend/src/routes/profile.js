const express = require('express');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');

const router = express.Router();

// Same threshold theme.js/HomeScreen.js/HistoryScreen.js already use client-
// side for "great swing" -- reused here, not reinvented, so a rank change
// and the frontend's own "great swings" count never disagree.
const GREAT_SWING_THRESHOLD = 75;

// Count-based, tennis-lore-themed -- climbs with total great swings logged,
// never goes down. Thresholds are a first-pass spacing (roughly geometric,
// ~2.5x per step) with no real usage data behind them yet; revisit once
// there's a real distribution of great-swing counts across users.
const RANK_TIERS = [
  { name: 'Rookie', threshold: 0 },
  { name: 'Rally Starter', threshold: 1 },
  { name: 'Baseliner', threshold: 5 },
  { name: 'Contender', threshold: 15 },
  { name: 'Circuit Player', threshold: 40 },
  { name: 'Tour Regular', threshold: 100 },
  { name: 'Grand Slammer', threshold: 250 },
  { name: 'Legend of the Game', threshold: 600 },
];

function rankForCount(greatCount) {
  let current = RANK_TIERS[0];
  let next = null;
  for (let i = 0; i < RANK_TIERS.length; i++) {
    if (RANK_TIERS[i].threshold <= greatCount) {
      current = RANK_TIERS[i];
      next = RANK_TIERS[i + 1] ?? null;
    }
  }
  return { current, next };
}

router.get('/profile/rank', requireAuth, (req, res) => {
  const { greatCount } = db.prepare(
    'SELECT COUNT(*) AS greatCount FROM analyses WHERE user_id = ? AND similarity >= ?'
  ).get(req.user.id, GREAT_SWING_THRESHOLD);

  const { current, next } = rankForCount(greatCount);

  res.json({
    greatCount,
    rank: { name: current.name, threshold: current.threshold },
    next: next ? { name: next.name, threshold: next.threshold } : null,
    remaining: next ? next.threshold - greatCount : 0,
  });
});

// Minimum sample sizes before either signal is trusted enough to show --
// small numbers are noisy (e.g. 1 error out of 2 tagged rallies is not a
// real "error-prone" signal), same "don't trust a lucky/unlucky streak"
// reasoning tip_training_log.py's should_trust_student() already uses.
const MIN_TAGGED_RALLIES = 5;
const MIN_ANALYSES = 10;

const PLAYER_TYPES = {
  grinder: {
    type: 'grinder',
    label: 'The Grinder',
    description: 'You win points by outlasting opponents in long rallies -- patient and consistent rather than going for early winners.',
  },
  finisher: {
    type: 'finisher',
    label: 'The Finisher',
    description: 'You end points quickly with aggressive shots -- a high rate of winners and aces relative to how long your rallies run.',
  },
  big_server: {
    type: 'big_server',
    label: 'Big Server',
    description: 'Your serve is doing a lot of the work -- a big share of your logged swings are serves.',
  },
  all_court: {
    type: 'all_court',
    label: 'All-Court Player',
    description: 'A balanced game with no single dominant tendency yet -- keep logging swings and match highlights to sharpen this.',
  },
};

// First-pass, rule-based estimate -- this app has no court-position or
// rally-pattern tracking (see HANDOVER.md), so this is an approximation
// from what's already logged (highlight-reel outcome tags, and failing
// that, shot-type mix), not a real tactical-style classifier. Revisit once
// there's real positional/rally data to work from.
function computePlayerType(userId) {
  const taggedRallies = db.prepare(
    `SELECT outcome_tag, swing_count, duration_sec FROM rally_clips
     WHERE user_id = ? AND outcome_tag IN ('winner', 'ace', 'error')`
  ).all(userId);

  if (taggedRallies.length >= MIN_TAGGED_RALLIES) {
    const total = taggedRallies.length;
    const aggressive = taggedRallies.filter((r) => r.outcome_tag === 'winner' || r.outcome_tag === 'ace').length;
    const aggressionRate = aggressive / total;
    const avgSwingCount = taggedRallies.reduce((sum, r) => sum + (r.swing_count ?? 0), 0) / total;
    const avgDuration = taggedRallies.reduce((sum, r) => sum + (r.duration_sec ?? 0), 0) / total;

    if (aggressionRate >= 0.5 && avgSwingCount <= 4) {
      return { ...PLAYER_TYPES.finisher, confidence: 'estimated' };
    }
    if ((avgSwingCount >= 8 || avgDuration >= 15) && aggressionRate < 0.35) {
      return { ...PLAYER_TYPES.grinder, confidence: 'estimated' };
    }
    return { ...PLAYER_TYPES.all_court, confidence: 'estimated' };
  }

  const analyses = db.prepare('SELECT shot_type FROM analyses WHERE user_id = ?').all(userId);
  if (analyses.length >= MIN_ANALYSES) {
    const serveShare = analyses.filter((a) => a.shot_type === 'serve').length / analyses.length;
    if (serveShare >= 0.45) {
      return { ...PLAYER_TYPES.big_server, confidence: 'estimated' };
    }
    return { ...PLAYER_TYPES.all_court, confidence: 'estimated' };
  }

  const swingsNeeded = Math.max(0, MIN_ANALYSES - analyses.length);
  return { type: null, reason: 'not_enough_data', swingsNeeded };
}

router.get('/profile/player-type', requireAuth, (req, res) => {
  res.json(computePlayerType(req.user.id));
});

module.exports = router;
