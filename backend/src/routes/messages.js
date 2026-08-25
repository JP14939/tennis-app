const express = require('express');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { sendPushNotification } = require('../utils/pushNotifications');
const { MAX_LENGTHS, isText, isOptionalText } = require('../domain/invariants');
const { validate } = require('../validation/validateBody');

const router = express.Router();

// Always store the pair sorted ascending -- so a whole thread between two
// users is one WHERE user_a_id = ? AND user_b_id = ? query regardless of
// who initiated it; sender_id on each row carries the actual direction.
function threadPair(id1, id2) {
  return id1 < id2 ? [id1, id2] : [id2, id1];
}

function isBlocked(userId, otherId) {
  // Checked in both directions at send-time (either party blocking stops
  // new messages), but a user's own thread LIST only hides people THEY
  // blocked (see GET /messages/threads below) -- someone who blocked you
  // doesn't disappear from your own history, only from theirs.
  return !!db.prepare(
    'SELECT 1 FROM user_blocks WHERE (blocker_id = ? AND blocked_id = ?) OR (blocker_id = ? AND blocked_id = ?)'
  ).get(userId, otherId, otherId, userId);
}

// POST /messages/thread/:otherUserId previously required only auth -- any
// logged-in user could message (and push-notify) any other user id with no
// relationship check at all, which is a spam vector if `otherUserId` is
// iterated. Allowed to send if: friends, linked as coach/student (either
// direction), or a thread with this person already exists (so an existing
// conversation -- e.g. one that predates this check -- can still continue).
function canMessage(myId, otherId) {
  const [a, b] = threadPair(myId, otherId);
  const isFriend = !!db.prepare('SELECT 1 FROM friend_links WHERE user_a_id = ? AND user_b_id = ?').get(a, b);
  if (isFriend) return true;
  const isCoachLinked = !!db.prepare(
    'SELECT 1 FROM coach_links WHERE (coach_id = ? AND student_id = ?) OR (coach_id = ? AND student_id = ?)'
  ).get(myId, otherId, otherId, myId);
  if (isCoachLinked) return true;
  return !!db.prepare('SELECT 1 FROM messages WHERE user_a_id = ? AND user_b_id = ? LIMIT 1').get(a, b);
}

router.get('/messages/threads', requireAuth, (req, res) => {
  const myId = req.user.id;
  const rows = db.prepare(`
    SELECT
      m.*,
      CASE WHEN m.user_a_id = ? THEN m.user_b_id ELSE m.user_a_id END AS other_id
    FROM messages m
    WHERE m.user_a_id = ? OR m.user_b_id = ?
    ORDER BY m.created_at DESC, m.id DESC
  `).all(myId, myId, myId);

  const blockedByMe = new Set(
    db.prepare('SELECT blocked_id FROM user_blocks WHERE blocker_id = ?').all(myId).map((r) => r.blocked_id)
  );

  const threads = new Map();
  for (const row of rows) {
    if (blockedByMe.has(row.other_id)) continue;
    if (!threads.has(row.other_id)) {
      threads.set(row.other_id, { other_id: row.other_id, last_body: row.body, last_at: row.created_at, unread_count: 0 });
    }
    if (row.sender_id !== myId && !row.read_at) {
      threads.get(row.other_id).unread_count += 1;
    }
  }

  const otherIds = [...threads.keys()];
  const users = otherIds.length
    ? db.prepare(`SELECT id, name, username FROM users WHERE id IN (${otherIds.map(() => '?').join(',')})`).all(...otherIds)
    : [];
  const userById = new Map(users.map((u) => [u.id, u]));

  const result = otherIds.map((id) => ({ ...threads.get(id), user: userById.get(id) ?? null }))
    .sort((a, b) => new Date(b.last_at) - new Date(a.last_at));

  res.json({ threads: result });
});

router.get('/messages/thread/:otherUserId', requireAuth, (req, res) => {
  const myId = req.user.id;
  const otherId = parseInt(req.params.otherUserId, 10);
  if (!Number.isInteger(otherId)) {
    return res.status(400).json({ error: 'Invalid user id' });
  }

  const [a, b] = threadPair(myId, otherId);
  const messages = db.prepare(
    `SELECT * FROM messages WHERE user_a_id = ? AND user_b_id = ? ORDER BY created_at ASC`
  ).all(a, b);

  db.prepare(
    `UPDATE messages SET read_at = datetime('now') WHERE user_a_id = ? AND user_b_id = ? AND sender_id = ? AND read_at IS NULL`
  ).run(a, b, otherId);

  res.json({ messages });
});

router.post('/messages/thread/:otherUserId', requireAuth, (req, res) => {
  const myId = req.user.id;
  const otherId = parseInt(req.params.otherUserId, 10);
  const { body } = req.body || {};

  if (!Number.isInteger(otherId)) {
    return res.status(400).json({ error: 'Invalid user id' });
  }
  // The old truthy-and-trim check accepted a non-string body (which then threw
  // inside better-sqlite3 as a 500) and had no length cap -- and the body is
  // pushed verbatim as a notification, not just stored.
  const bad = validate([
    ['body', body, isText(MAX_LENGTHS.messageBody), `must be a message of ${MAX_LENGTHS.messageBody} characters or fewer`],
  ]);
  if (bad) return res.status(400).json(bad);

  const recipient = db.prepare('SELECT id, name FROM users WHERE id = ?').get(otherId);
  if (!recipient) return res.status(404).json({ error: 'User not found' });

  if (isBlocked(myId, otherId)) {
    return res.status(403).json({ error: "You can't message this user" });
  }
  if (!canMessage(myId, otherId)) {
    return res.status(403).json({ error: 'You can only message friends or a linked coach/student' });
  }

  const [a, b] = threadPair(myId, otherId);
  const info = db.prepare(
    `INSERT INTO messages (user_a_id, user_b_id, sender_id, body) VALUES (?, ?, ?, ?)`
  ).run(a, b, myId, body.trim());

  const sender = db.prepare('SELECT name FROM users WHERE id = ?').get(myId);
  sendPushNotification(otherId, `Message from ${sender?.name ?? 'a player'}`, body.trim(), { fromUserId: myId });

  const message = db.prepare('SELECT * FROM messages WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json({ message });
});

router.post('/messages/report/:messageId', requireAuth, (req, res) => {
  const messageId = parseInt(req.params.messageId, 10);
  const { reason } = req.body || {};
  if (!Number.isInteger(messageId)) {
    return res.status(400).json({ error: 'Invalid message id' });
  }
  const bad = validate([
    ['reason', reason, isOptionalText(MAX_LENGTHS.reportReason), `must be ${MAX_LENGTHS.reportReason} characters or fewer`],
  ]);
  if (bad) return res.status(400).json(bad);

  const message = db.prepare(
    'SELECT * FROM messages WHERE id = ? AND (user_a_id = ? OR user_b_id = ?)'
  ).get(messageId, req.user.id, req.user.id);
  if (!message) return res.status(404).json({ error: 'Message not found' });

  db.prepare('INSERT INTO message_reports (message_id, reporter_id, reason) VALUES (?, ?, ?)')
    .run(messageId, req.user.id, reason ?? null);
  res.status(201).end();
});

router.post('/users/:id/block', requireAuth, (req, res) => {
  const blockedId = parseInt(req.params.id, 10);
  if (!Number.isInteger(blockedId) || blockedId === req.user.id) {
    return res.status(400).json({ error: 'Invalid user id' });
  }
  const target = db.prepare('SELECT id FROM users WHERE id = ?').get(blockedId);
  if (!target) return res.status(404).json({ error: 'User not found' });

  db.prepare('INSERT OR IGNORE INTO user_blocks (blocker_id, blocked_id) VALUES (?, ?)')
    .run(req.user.id, blockedId);
  res.status(204).end();
});

router.delete('/users/:id/block', requireAuth, (req, res) => {
  const blockedId = parseInt(req.params.id, 10);
  if (!Number.isInteger(blockedId)) {
    return res.status(400).json({ error: 'Invalid user id' });
  }
  db.prepare('DELETE FROM user_blocks WHERE blocker_id = ? AND blocked_id = ?')
    .run(req.user.id, blockedId);
  res.status(204).end();
});

router.get('/users/blocked', requireAuth, (req, res) => {
  const blocked = db.prepare(`
    SELECT u.id, u.name, u.username FROM user_blocks b
    JOIN users u ON u.id = b.blocked_id
    WHERE b.blocker_id = ?
    ORDER BY b.created_at DESC
  `).all(req.user.id);
  res.json({ blocked });
});

module.exports = router;
