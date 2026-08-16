const express = require('express');
const crypto = require('crypto');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { sendPushNotification } = require('../utils/pushNotifications');

const router = express.Router();

// Same alphabet/shape as coach.js's generateCode() -- 8 uppercase
// base32-ish chars, excludes ambiguous 0/O/1/I.
function generateCode() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code = '';
  for (let i = 0; i < 8; i++) {
    code += alphabet[crypto.randomInt(alphabet.length)];
  }
  return code;
}

// Friendship is symmetric -- always store/query the pair sorted ascending
// so there's exactly one row per pair regardless of who initiated it.
function sortedPair(id1, id2) {
  return id1 < id2 ? [id1, id2] : [id2, id1];
}

function isFriends(userAId, userBId) {
  const [a, b] = sortedPair(userAId, userBId);
  return !!db.prepare('SELECT 1 FROM friend_links WHERE user_a_id = ? AND user_b_id = ?').get(a, b);
}

// Every friend_matches row stores sets_won/sets_lost relative to logged_by,
// not a fixed side -- normalize each row to {my_sets, their_sets} from
// `viewerId`'s perspective, flipping when the friend was the one who logged it.
function getMatchesBetween(viewerId, friendId) {
  const rows = db.prepare(
    `SELECT * FROM friend_matches
     WHERE (logged_by = ? AND opponent_id = ?) OR (logged_by = ? AND opponent_id = ?)
     ORDER BY played_at DESC, id DESC`
  ).all(viewerId, friendId, friendId, viewerId);

  return rows.map((row) => {
    const loggedByViewer = row.logged_by === viewerId;
    return {
      id: row.id,
      played_at: row.played_at,
      score_detail: row.score_detail,
      created_at: row.created_at,
      logged_by_me: loggedByViewer,
      my_sets: loggedByViewer ? row.sets_won : row.sets_lost,
      their_sets: loggedByViewer ? row.sets_lost : row.sets_won,
    };
  });
}

function computeRecord(matches) {
  return matches.reduce((acc, m) => {
    if (m.my_sets > m.their_sets) acc.wins += 1;
    else if (m.my_sets < m.their_sets) acc.losses += 1;
    return acc;
  }, { wins: 0, losses: 0 });
}

// Regenerating leaves old unused codes in place (harmless -- link only ever
// succeeds once, friend_links has a UNIQUE(user_a_id, user_b_id)
// constraint), same as coach.js's invite-code endpoint.
router.post('/friends/code', requireAuth, (req, res) => {
  let code;
  do {
    code = generateCode();
  } while (db.prepare('SELECT 1 FROM friend_codes WHERE code = ?').get(code));

  db.prepare('INSERT INTO friend_codes (user_id, code) VALUES (?, ?)').run(req.user.id, code);
  res.status(201).json({ code });
});

router.post('/friends/link', requireAuth, (req, res) => {
  const { code } = req.body || {};
  if (!code) {
    return res.status(400).json({ error: 'code is required' });
  }

  const invite = db.prepare('SELECT * FROM friend_codes WHERE code = ? AND used_at IS NULL')
    .get(String(code).toUpperCase());
  if (!invite) {
    return res.status(404).json({ error: 'Invalid or already-used invite code' });
  }
  if (invite.user_id === req.user.id) {
    return res.status(400).json({ error: "You can't add yourself as a friend" });
  }

  const [a, b] = sortedPair(req.user.id, invite.user_id);
  db.prepare('INSERT OR IGNORE INTO friend_links (user_a_id, user_b_id) VALUES (?, ?)').run(a, b);
  db.prepare("UPDATE friend_codes SET used_at = datetime('now') WHERE id = ?").run(invite.id);

  const friend = db.prepare('SELECT id, name, username FROM users WHERE id = ?').get(invite.user_id);
  res.status(201).json({ friend });
});

router.get('/friends', requireAuth, (req, res) => {
  const myId = req.user.id;
  const rows = db.prepare(`
    SELECT u.id, u.name, u.username FROM friend_links fl
    JOIN users u ON u.id = (CASE WHEN fl.user_a_id = ? THEN fl.user_b_id ELSE fl.user_a_id END)
    WHERE fl.user_a_id = ? OR fl.user_b_id = ?
    ORDER BY u.name
  `).all(myId, myId, myId);

  const friends = rows.map((friend) => ({
    ...friend,
    record: computeRecord(getMatchesBetween(myId, friend.id)),
  }));

  res.json({ friends });
});

router.delete('/friends/:userId', requireAuth, (req, res) => {
  const [a, b] = sortedPair(req.user.id, parseInt(req.params.userId, 10));
  db.prepare('DELETE FROM friend_links WHERE user_a_id = ? AND user_b_id = ?').run(a, b);
  res.status(204).end();
});

router.get('/friends/:userId/matches', requireAuth, (req, res) => {
  const friendId = parseInt(req.params.userId, 10);
  if (!isFriends(req.user.id, friendId)) {
    return res.status(403).json({ error: 'Not friends with this user' });
  }
  res.json({ matches: getMatchesBetween(req.user.id, friendId) });
});

router.post('/friends/:userId/matches', requireAuth, (req, res) => {
  const friendId = parseInt(req.params.userId, 10);
  const { playedAt, setsWon, setsLost, scoreDetail } = req.body || {};

  if (!isFriends(req.user.id, friendId)) {
    return res.status(403).json({ error: 'Not friends with this user' });
  }
  if (!playedAt || !Number.isInteger(setsWon) || !Number.isInteger(setsLost)) {
    return res.status(400).json({ error: 'playedAt, setsWon, and setsLost are required' });
  }

  const info = db.prepare(
    `INSERT INTO friend_matches (logged_by, opponent_id, played_at, sets_won, sets_lost, score_detail)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).run(req.user.id, friendId, playedAt, setsWon, setsLost, scoreDetail ?? null);

  const [match] = getMatchesBetween(req.user.id, friendId).filter((m) => m.id === info.lastInsertRowid);
  res.status(201).json({ match });
});

router.delete('/friends/matches/:matchId', requireAuth, (req, res) => {
  const match = db.prepare('SELECT * FROM friend_matches WHERE id = ? AND logged_by = ?')
    .get(req.params.matchId, req.user.id);
  if (!match) return res.status(404).json({ error: 'Match not found' });

  db.prepare('DELETE FROM friend_matches WHERE id = ?').run(match.id);
  res.status(204).end();
});

// Explicit per-swing sharing (unlike coach linking's full-access-once-linked
// model) -- a friend only ever sees an analysis you actively shared.
router.post('/friends/:userId/share', requireAuth, (req, res) => {
  const friendId = parseInt(req.params.userId, 10);
  const { analysisId } = req.body || {};

  if (!isFriends(req.user.id, friendId)) {
    return res.status(403).json({ error: 'Not friends with this user' });
  }
  const analysis = db.prepare('SELECT * FROM analyses WHERE id = ? AND user_id = ?')
    .get(analysisId, req.user.id);
  if (!analysis) {
    return res.status(404).json({ error: 'Analysis not found' });
  }

  db.prepare('INSERT OR IGNORE INTO shared_analyses (analysis_id, owner_id, friend_id) VALUES (?, ?, ?)')
    .run(analysis.id, req.user.id, friendId);

  const sharer = db.prepare('SELECT name FROM users WHERE id = ?').get(req.user.id);
  sendPushNotification(friendId, `${sharer?.name ?? 'A friend'} shared a swing`, 'Tap to see it on Friends.', { analysisId: analysis.id });

  res.status(201).json({ shared: true });
});

router.get('/friends/:userId/shared', requireAuth, (req, res) => {
  const myId = req.user.id;
  const friendId = parseInt(req.params.userId, 10);

  const rows = db.prepare(`
    SELECT sa.*, a.shot_type, a.similarity, a.created_at AS analysis_created_at
    FROM shared_analyses sa
    JOIN analyses a ON a.id = sa.analysis_id
    WHERE (sa.owner_id = ? AND sa.friend_id = ?) OR (sa.owner_id = ? AND sa.friend_id = ?)
    ORDER BY sa.shared_at DESC
  `).all(myId, friendId, friendId, myId);

  const shared = rows.map((row) => ({
    id: row.id,
    analysis_id: row.analysis_id,
    shot_type: row.shot_type,
    similarity: row.similarity,
    analysis_created_at: row.analysis_created_at,
    shared_at: row.shared_at,
    direction: row.owner_id === myId ? 'sent' : 'received',
  }));

  res.json({ shared });
});

router.get('/friends/shared/:analysisId', requireAuth, (req, res) => {
  const analysisId = parseInt(req.params.analysisId, 10);
  const analysis = db.prepare('SELECT * FROM analyses WHERE id = ?').get(analysisId);
  if (!analysis) return res.status(404).json({ error: 'Analysis not found' });

  const isOwner = analysis.user_id === req.user.id;
  const isRecipient = !!db.prepare('SELECT 1 FROM shared_analyses WHERE analysis_id = ? AND friend_id = ?')
    .get(analysisId, req.user.id);
  if (!isOwner && !isRecipient) {
    return res.status(403).json({ error: 'This swing was not shared with you' });
  }

  const owner = db.prepare('SELECT name, username FROM users WHERE id = ?').get(analysis.user_id);
  res.json({
    id: analysis.id,
    shot_type: analysis.shot_type,
    similarity: analysis.similarity,
    created_at: analysis.created_at,
    result: JSON.parse(analysis.result_json),
    owner_name: owner?.username ? `@${owner.username}` : owner?.name,
  });
});

module.exports = router;
