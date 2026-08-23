const express = require('express');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { sendPushNotification } = require('../utils/pushNotifications');
const { redeemInviteCode, generateInviteCode } = require('../utils/inviteCodes');
const {
  MAX_LENGTHS, MAX_SETS_IN_A_MATCH, isSetCount, isIsoDateTime, isOptionalText, isPositiveIntegerId,
} = require('../domain/invariants');
const { validate } = require('../validation/validateBody');

const router = express.Router();

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
    code = generateInviteCode();
  } while (db.prepare('SELECT 1 FROM friend_codes WHERE code = ?').get(code));

  db.prepare('INSERT INTO friend_codes (user_id, code) VALUES (?, ?)').run(req.user.id, code);
  res.status(201).json({ code });
});

router.post('/friends/link', requireAuth, (req, res) => {
  const { code } = req.body || {};
  if (!code) {
    return res.status(400).json({ error: 'code is required' });
  }

  const { outcome, CODE_NOT_FOUND, SELF_LINK } = redeemInviteCode({
    inviteTable: 'friend_codes',
    ownerIdColumn: 'user_id',
    code,
    requesterId: req.user.id,
    insertLink: (invite) => {
      const [a, b] = sortedPair(req.user.id, invite.user_id);
      db.prepare('INSERT OR IGNORE INTO friend_links (user_a_id, user_b_id) VALUES (?, ?)').run(a, b);
    },
  });
  if (outcome === CODE_NOT_FOUND) {
    return res.status(404).json({ error: 'Invalid or already-used invite code' });
  }
  if (outcome === SELF_LINK) {
    return res.status(400).json({ error: "You can't add yourself as a friend" });
  }

  const friend = db.prepare('SELECT id, name, username FROM users WHERE id = ?').get(outcome);
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

  // One query for every friend's matches, not one query PER friend --
  // getMatchesBetween() ran a separate friend_matches SELECT inside this
  // .map() before, so a user with N friends made N+1 synchronous SQLite
  // calls on every load of this screen. Every match involving myId (either
  // as logged_by or opponent_id) is fetched in one query, then grouped by
  // whichever side isn't myId -- that's always the friend the row is about.
  const friendIds = rows.map((f) => f.id);
  const matchesByFriendId = new Map(friendIds.map((id) => [id, []]));
  if (friendIds.length > 0) {
    const placeholders = friendIds.map(() => '?').join(',');
    const allMatches = db.prepare(
      `SELECT * FROM friend_matches
       WHERE (logged_by = ? AND opponent_id IN (${placeholders}))
          OR (opponent_id = ? AND logged_by IN (${placeholders}))
       ORDER BY played_at DESC, id DESC`
    ).all(myId, ...friendIds, myId, ...friendIds);

    for (const row of allMatches) {
      const friendId = row.logged_by === myId ? row.opponent_id : row.logged_by;
      const loggedByViewer = row.logged_by === myId;
      matchesByFriendId.get(friendId).push({
        id: row.id,
        played_at: row.played_at,
        score_detail: row.score_detail,
        created_at: row.created_at,
        logged_by_me: loggedByViewer,
        my_sets: loggedByViewer ? row.sets_won : row.sets_lost,
        their_sets: loggedByViewer ? row.sets_lost : row.sets_won,
      });
    }
  }

  const friends = rows.map((friend) => ({
    ...friend,
    record: computeRecord(matchesByFriendId.get(friend.id)),
  }));

  res.json({ friends });
});

router.delete('/friends/:userId', requireAuth, (req, res) => {
  const otherId = parseInt(req.params.userId, 10);
  if (!Number.isInteger(otherId)) {
    return res.status(400).json({ error: 'Invalid user id' });
  }
  // 204 whether or not a link actually existed -- delete is idempotent by
  // design here (the frontend's unfriend() doesn't distinguish "removed"
  // from "already gone", e.g. a double-tap or a stale friend list), unlike
  // the invalid-input case above which IS a real client bug worth a 400.
  const [a, b] = sortedPair(req.user.id, otherId);
  db.prepare('DELETE FROM friend_links WHERE user_a_id = ? AND user_b_id = ?').run(a, b);
  res.status(204).end();
});

router.get('/friends/:userId/matches', requireAuth, (req, res) => {
  const friendId = parseInt(req.params.userId, 10);
  // Matches the guard the DELETE /friends/:userId handler above already
  // has -- was missing here, so a non-numeric :userId silently degraded to
  // isFriends() returning false (a correct-looking 403) instead of a clean
  // 400. Harmless today, but fragile: any future change to isFriends()/
  // getMatchesBetween() that does arithmetic on the id before the DB call
  // would turn that into an unhandled crash instead of a clean rejection.
  if (!Number.isInteger(friendId)) {
    return res.status(400).json({ error: 'Invalid user id' });
  }
  if (!isFriends(req.user.id, friendId)) {
    return res.status(403).json({ error: 'Not friends with this user' });
  }
  res.json({ matches: getMatchesBetween(req.user.id, friendId) });
});

router.post('/friends/:userId/matches', requireAuth, (req, res) => {
  const friendId = parseInt(req.params.userId, 10);
  const { playedAt, setsWon, setsLost, scoreDetail } = req.body || {};

  if (!Number.isInteger(friendId)) {
    return res.status(400).json({ error: 'Invalid user id' });
  }
  if (!isFriends(req.user.id, friendId)) {
    return res.status(403).json({ error: 'Not friends with this user' });
  }

  // A match record is shown to BOTH players and feeds computeRecord()'s
  // win/loss tally, so nonsense here corrupts your friend's view of their own
  // record too. Integer alone wasn't enough: -5 sets and 10^9 sets both
  // passed the old check. playedAt is the ORDER BY key for the match list
  // and gets rendered as a date, so it has to actually be one.
  const bad = validate([
    ['playedAt', playedAt, isIsoDateTime, 'must be a valid date'],
    ['setsWon', setsWon, isSetCount, `must be a whole number between 0 and ${MAX_SETS_IN_A_MATCH}`],
    ['setsLost', setsLost, isSetCount, `must be a whole number between 0 and ${MAX_SETS_IN_A_MATCH}`],
    ['scoreDetail', scoreDetail, isOptionalText(MAX_LENGTHS.scoreDetail), `must be ${MAX_LENGTHS.scoreDetail} characters or fewer`],
  ]);
  if (bad) return res.status(400).json(bad);

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

  // Same guard the other :userId routes in this file already have -- without
  // it a non-numeric id became NaN and degraded to a misleading 403.
  if (!Number.isInteger(friendId)) {
    return res.status(400).json({ error: 'Invalid user id' });
  }
  if (!isPositiveIntegerId(analysisId)) {
    return res.status(400).json({ error: 'analysisId must be a valid analysis id', field: 'analysisId' });
  }
  if (!isFriends(req.user.id, friendId)) {
    return res.status(403).json({ error: 'Not friends with this user' });
  }
  // Bound directly into the SELECT below -- a non-primitive analysisId (e.g.
  // an object) throws a RangeError deep in better-sqlite3 instead of a clean
  // 400, same class of bug fixed elsewhere in this file for friendId.
  if (!Number.isInteger(analysisId)) {
    return res.status(400).json({ error: 'Invalid analysisId' });
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
  // Matches the guard every other :userId route in this file already has --
  // was missing here, inconsistent with the pattern the rest of the file
  // establishes. Harmless today (a NaN bind just matches nothing, so this
  // fails safe to an empty list rather than a 500), but a landmine for any
  // future change to this query that does arithmetic on the id first.
  if (!Number.isInteger(friendId)) {
    return res.status(400).json({ error: 'Invalid user id' });
  }

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
  if (!isPositiveIntegerId(req.params.analysisId)) {
    return res.status(400).json({ error: 'Invalid analysis id' });
  }
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
