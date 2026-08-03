const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');

const router = express.Router();

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const TOKEN_TTL = '30d'; // mobile app — favour staying logged in over frequent re-auth

function issueToken(user) {
  return jwt.sign(
    { id: user.id, email: user.email, tier: user.tier },
    process.env.JWT_SECRET,
    { expiresIn: TOKEN_TTL }
  );
}

function publicUser(user) {
  return { id: user.id, email: user.email, name: user.name, tier: user.tier };
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

module.exports = router;
