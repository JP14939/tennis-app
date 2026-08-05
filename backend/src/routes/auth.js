const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const fs = require('fs');
const path = require('path');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { DATA_DIR } = require('../config/paths');

const router = express.Router();

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const TOKEN_TTL = '30d'; // mobile app — favour staying logged in over frequent re-auth
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

router.get('/auth/me', requireAuth, (req, res) => {
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.user.id);
  if (!user) {
    return res.status(404).json({ error: 'User no longer exists' });
  }
  res.json({ user: publicUser(user) });
});

router.patch('/auth/me', requireAuth, (req, res) => {
  const { name, notifications_enabled } = req.body || {};

  if (name !== undefined && !name.trim()) {
    return res.status(400).json({ error: 'Name is required' });
  }

  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.user.id);
  if (!user) {
    return res.status(404).json({ error: 'User no longer exists' });
  }

  db.prepare('UPDATE users SET name = ?, notifications_enabled = ? WHERE id = ?').run(
    name !== undefined ? name.trim() : user.name,
    notifications_enabled !== undefined ? (notifications_enabled ? 1 : 0) : user.notifications_enabled,
    user.id
  );

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

  const deleteUser = db.transaction((userId) => {
    db.prepare('DELETE FROM analyses WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM analysis_usage WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM rally_clips WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM highlight_jobs WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM push_tokens WHERE user_id = ?').run(userId);
    // Financial audit trail -- kept, just disassociated from the deleted account.
    db.prepare('UPDATE payment_events SET user_id = NULL WHERE user_id = ?').run(userId);
    db.prepare('DELETE FROM users WHERE id = ?').run(userId);
  });
  deleteUser(user.id);

  fs.rm(path.join(HIGHLIGHT_CLIPS_DIR, String(user.id)), { recursive: true, force: true }, () => {});

  res.status(204).end();
});

module.exports = router;
