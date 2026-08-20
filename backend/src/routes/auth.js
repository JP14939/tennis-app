const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { DATA_DIR } = require('../config/paths');
const { sendPasswordResetEmail } = require('../utils/email');

const router = express.Router();

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const USERNAME_RE = /^[a-z0-9_]{3,20}$/;
const TOKEN_TTL = '30d'; // mobile app — favour staying logged in over frequent re-auth
const RESET_TOKEN_TTL_MS = 60 * 60 * 1000; // 1 hour
// Same path convention highlights.js uses for its per-user clip subdirectory.
const HIGHLIGHT_CLIPS_DIR = path.join(DATA_DIR, 'runtime', 'highlight_clips');

function issueToken(user) {
  return jwt.sign(
    { id: user.id, email: user.email, tier: user.tier },
    process.env.JWT_SECRET,
    { expiresIn: TOKEN_TTL }
  );
}

function publicUser(user) {
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    username: user.username,
    tier: user.tier,
    notifications_enabled: !!user.notifications_enabled,
  };
}

router.post('/auth/signup', async (req, res) => {
  const { email, password, name } = req.body || {};

  if (!email || !EMAIL_RE.test(email)) {
    return res.status(400).json({ error: 'A valid email is required' });
  }
  if (!password || password.length < 8) {
    return res.status(400).json({ error: 'Password must be at least 8 characters' });
  }
  if (!name || !name.trim()) {
    return res.status(400).json({ error: 'Name is required' });
  }

  const normalisedEmail = email.trim().toLowerCase();
  const existing = db.prepare('SELECT id FROM users WHERE email = ?').get(normalisedEmail);
  if (existing) {
    return res.status(409).json({ error: 'An account with this email already exists' });
  }

  const passwordHash = await bcrypt.hash(password, 10);
  const info = db.prepare(
    'INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)'
  ).run(normalisedEmail, passwordHash, name.trim());

  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(info.lastInsertRowid);
  res.status(201).json({ token: issueToken(user), user: publicUser(user) });
});

router.post('/auth/login', async (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password are required' });
  }

  const normalisedEmail = email.trim().toLowerCase();
  const user = db.prepare('SELECT * FROM users WHERE email = ?').get(normalisedEmail);

  // Compare against a dummy hash when the user doesn't exist so the response
  // timing doesn't reveal whether an email is registered.
  const hashToCheck = user ? user.password_hash : '$2a$10$invalidsaltinvalidsaltinvalidsaltuw';
  const valid = await bcrypt.compare(password, hashToCheck);

  if (!user || !valid) {
    return res.status(401).json({ error: 'Incorrect email or password' });
  }

  res.json({ token: issueToken(user), user: publicUser(user) });
});

router.post('/auth/forgot-password', async (req, res) => {
  const { email } = req.body || {};
  if (!email || !EMAIL_RE.test(email)) {
    return res.status(400).json({ error: 'A valid email is required' });
  }

  const normalisedEmail = email.trim().toLowerCase();
  const user = db.prepare('SELECT * FROM users WHERE email = ?').get(normalisedEmail);

  // Always respond 204 whether or not the account exists -- same
  // don't-leak-account-existence reasoning as /auth/login's timing-safe
  // dummy hash comparison above, just applied to response shape instead
  // of timing since there's no password to compare against here.
  if (!user) {
    return res.status(204).end();
  }

  const rawToken = crypto.randomBytes(32).toString('hex');
  const tokenHash = crypto.createHash('sha256').update(rawToken).digest('hex');
  const expiresAt = new Date(Date.now() + RESET_TOKEN_TTL_MS).toISOString();
  db.prepare(
    'INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (?, ?, ?)'
  ).run(user.id, tokenHash, expiresAt);

  const publicBaseUrl = process.env.PUBLIC_BASE_URL || '';
  const resetUrl = `${publicBaseUrl}/reset-password.html?token=${rawToken}`;

  try {
    await sendPasswordResetEmail(user.email, resetUrl);
  } catch (err) {
    // Not configured yet (no RESEND_API_KEY) or Resend itself failed --
    // still respond 204 either way so this endpoint's response shape never
    // reveals email-sending state, but log loudly so a real misconfiguration
    // is noticeable in the backend console rather than silently swallowed.
    console.error('[auth/forgot-password] sendPasswordResetEmail failed:', err.message);
  }

  res.status(204).end();
});

router.post('/auth/reset-password', async (req, res) => {
  const { token, newPassword } = req.body || {};
  if (!token || !newPassword) {
    return res.status(400).json({ error: 'Token and new password are required' });
  }
  if (newPassword.length < 8) {
    return res.status(400).json({ error: 'New password must be at least 8 characters' });
  }

  const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
  const reset = db.prepare(
    'SELECT * FROM password_resets WHERE token_hash = ? AND used_at IS NULL AND expires_at > ? ORDER BY id DESC LIMIT 1'
  ).get(tokenHash, new Date().toISOString());

  if (!reset) {
    return res.status(400).json({ error: 'This reset link is invalid or has expired' });
  }

  const passwordHash = await bcrypt.hash(newPassword, 10);
  db.prepare('UPDATE users SET password_hash = ? WHERE id = ?').run(passwordHash, reset.user_id);
  db.prepare('UPDATE password_resets SET used_at = datetime(\'now\') WHERE id = ?').run(reset.id);

  res.status(204).end();
});

router.get('/auth/me', requireAuth, (req, res) => {
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.user.id);
  if (!user) {
    return res.status(404).json({ error: 'User no longer exists' });
  }
  res.json({ user: publicUser(user) });
});

router.patch('/auth/me', requireAuth, (req, res) => {
  const { name, notifications_enabled, username } = req.body || {};

  if (name !== undefined && !name.trim()) {
    return res.status(400).json({ error: 'Name is required' });
  }

  let normalisedUsername;
  if (username !== undefined) {
    normalisedUsername = username.trim().toLowerCase();
    if (!USERNAME_RE.test(normalisedUsername)) {
      return res.status(400).json({ error: 'Username must be 3-20 characters, lowercase letters, numbers, or underscores only' });
    }
  }

  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.user.id);
  if (!user) {
    return res.status(404).json({ error: 'User no longer exists' });
  }

  try {
    db.prepare('UPDATE users SET name = ?, notifications_enabled = ?, username = ? WHERE id = ?').run(
      name !== undefined ? name.trim() : user.name,
      notifications_enabled !== undefined ? (notifications_enabled ? 1 : 0) : user.notifications_enabled,
      normalisedUsername !== undefined ? normalisedUsername : user.username,
      user.id
    );
  } catch (err) {
    if (err.code === 'SQLITE_CONSTRAINT_UNIQUE') {
      return res.status(409).json({ error: 'Username is already taken' });
    }
    throw err;
  }

  const updated = db.prepare('SELECT * FROM users WHERE id = ?').get(user.id);
  res.json({ user: publicUser(updated) });
});

router.patch('/auth/password', requireAuth, async (req, res) => {
  const { currentPassword, newPassword } = req.body || {};
  if (!currentPassword || !newPassword) {
    return res.status(400).json({ error: 'Current and new password are required' });
  }
  if (newPassword.length < 8) {
    return res.status(400).json({ error: 'New password must be at least 8 characters' });
  }

  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.user.id);
  if (!user) {
    return res.status(404).json({ error: 'User no longer exists' });
  }

  const valid = await bcrypt.compare(currentPassword, user.password_hash);
  if (!valid) {
    return res.status(401).json({ error: 'Incorrect current password' });
  }

  const passwordHash = await bcrypt.hash(newPassword, 10);
  db.prepare('UPDATE users SET password_hash = ? WHERE id = ?').run(passwordHash, user.id);
  res.status(204).end();
});

router.delete('/auth/me', requireAuth, async (req, res) => {
  const { password } = req.body || {};
  if (!password) {
    return res.status(400).json({ error: 'Password is required to delete your account' });
  }

  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.user.id);
  if (!user) {
    return res.status(404).json({ error: 'User no longer exists' });
  }

  const valid = await bcrypt.compare(password, user.password_hash);
  if (!valid) {
    return res.status(401).json({ error: 'Incorrect password' });
  }

  // Every table below was audited against db.js's full schema (grew a lot
  // since this endpoint was first written -- messages, friends, court
  // activity, shared analyses, and annotations weren't handled at all,
  // meaning any user who'd ever used those features would hit a foreign-key
  // constraint error mid-transaction and simply be unable to delete their
  // account). Two categories:
  //   - Solely-owned content (their own analyses/videos, push tokens, court
  //     watches, etc.) -- fully deleted below.
  //   - Content shared with/by another user (messages, shared analyses they
  //     received, annotations they drew on someone else's swing, coach
  //     notes they wrote as a coach, match records) -- the ROW is kept so
  //     the other party's thread/history isn't destroyed, and resolved via
  //     the anonymized `users` row at the end instead of being deleted here.
  const deleteUser = db.transaction((userId) => {
    // Coach notes ON THE DELETED USER'S OWN analyses go with those analyses
    // (the analysis itself is being destroyed, so a note about a specific
    // moment of a video that no longer exists is meaningless). Coach notes
    // the deleted user WROTE about someone else's analysis are left alone.
    db.prepare('DELETE FROM coach_notes WHERE analysis_id IN (SELECT id FROM analyses WHERE user_id = ?)').run(userId);
    db.prepare('DELETE FROM coach_links WHERE coach_id = ? OR student_id = ?').run(userId, userId);
    db.prepare('DELETE FROM coach_invite_codes WHERE student_id = ?').run(userId);

    // Same reasoning as coach_notes above -- shares/annotations tied to the
    // deleted user's OWN analyses are destroyed along with those analyses;
    // shares/annotations they made on someone ELSE's analysis are left
    // alone (that other user's shared swing/feedback shouldn't vanish).
    db.prepare('DELETE FROM shared_analyses WHERE analysis_id IN (SELECT id FROM analyses WHERE user_id = ?)').run(userId);
    db.prepare('DELETE FROM swing_annotations WHERE analysis_id IN (SELECT id FROM analyses WHERE user_id = ?)').run(userId);
    db.prepare('DELETE FROM analyses WHERE user_id = ?').run(userId);

    db.prepare('DELETE FROM analysis_usage WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM reel_jobs WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM rally_clips WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM highlight_jobs WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM push_tokens WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM court_watches WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM court_confirmations WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM availability_posts WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM friend_codes WHERE user_id = ?').run(userId);
    // Pure relationship-state records (no independent content the other
    // party would lose) -- safe to delete outright, unlike messages.
    db.prepare('DELETE FROM friend_links WHERE user_a_id = ? OR user_b_id = ?').run(userId, userId);
    db.prepare('DELETE FROM user_blocks WHERE blocker_id = ? OR blocked_id = ?').run(userId, userId);
    // message_reports is a trust-and-safety record, not personal content --
    // left alone deliberately (same reasoning as messages/coach_notes),
    // resolved via the anonymized users row below.

    // Community data they contributed to (courts) -- kept, just
    // disassociated from their identity; other users rely on the court
    // itself continuing to exist.
    db.prepare('UPDATE courts SET submitted_by = NULL WHERE submitted_by = ?').run(userId);
    db.prepare('UPDATE courts SET cost_updated_by = NULL WHERE cost_updated_by = ?').run(userId);

    // Financial audit trail -- kept, just disassociated from the deleted account.
    db.prepare('UPDATE payment_events SET user_id = NULL WHERE user_id = ?').run(userId);

    // Anonymize rather than delete the users row itself: messages,
    // shared_analyses (as recipient), swing_annotations (as a guest
    // annotator on someone else's swing), friend_matches, coach_notes (as
    // coach), and celebrity_scores all still reference this id via a
    // NOT NULL foreign key, so the row must keep existing -- scrubbing its
    // personal fields is what actually fulfils "delete my account" for
    // those relational rows without breaking the other party's data.
    // password_hash is set to a real bcrypt hash of random bytes (not a
    // sentinel string) so a login attempt fails cleanly through the normal
    // bcrypt.compare() path rather than depending on how the library
    // handles a malformed hash.
    const deadHash = bcrypt.hashSync(crypto.randomBytes(32).toString('hex'), 10);
    db.prepare(`
      UPDATE users
      SET email = 'deleted_' || id || '@rallymax.invalid',
          password_hash = ?,
          name = 'Deleted user',
          username = NULL,
          tier = 'free'
      WHERE id = ?
    `).run(deadHash, userId);
  });
  deleteUser(user.id);

  fs.rm(path.join(HIGHLIGHT_CLIPS_DIR, String(user.id)), { recursive: true, force: true }, () => {});

  res.status(204).end();
});

module.exports = router;
