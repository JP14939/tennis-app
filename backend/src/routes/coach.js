const express = require('express');
const crypto = require('crypto');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');

const router = express.Router();

const VALID_PHASE_KEYS = ['backswing', 'contact', 'follow_through', 'body_rotation'];

function generateCode() {
  // 8 uppercase base32-ish chars, easy to read/type aloud -- excludes
  // ambiguous 0/O/1/I.
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code = '';
  for (let i = 0; i < 8; i++) {
    code += alphabet[crypto.randomInt(alphabet.length)];
  }
  return code;
}

function isLinked(coachId, studentId) {
  return !!db.prepare('SELECT 1 FROM coach_links WHERE coach_id = ? AND student_id = ?').get(coachId, studentId);
}

// Generates a fresh invite code for the caller as student. Old unused codes
// for this student are left in place (harmless -- link only succeeds once,
// since coach_links has a UNIQUE(coach_id, student_id) constraint), but are
// no longer the one shown, so this is effectively "regenerate."
router.post('/coach/invite-code', requireAuth, (req, res) => {
  let code;
  do {
    code = generateCode();
  } while (db.prepare('SELECT 1 FROM coach_invite_codes WHERE code = ?').get(code));

  db.prepare('INSERT INTO coach_invite_codes (student_id, code) VALUES (?, ?)').run(req.user.id, code);
  res.status(201).json({ code });
});

router.post('/coach/link', requireAuth, (req, res) => {
  const { code } = req.body || {};
  if (!code) {
    return res.status(400).json({ error: 'code is required' });
  }

  const invite = db.prepare('SELECT * FROM coach_invite_codes WHERE code = ? AND used_at IS NULL')
    .get(String(code).toUpperCase());
  if (!invite) {
    return res.status(404).json({ error: 'Invalid or already-used invite code' });
  }
  if (invite.student_id === req.user.id) {
    return res.status(400).json({ error: "You can't link to your own invite code" });
  }

  db.prepare('INSERT OR IGNORE INTO coach_links (coach_id, student_id) VALUES (?, ?)')
    .run(req.user.id, invite.student_id);
  db.prepare("UPDATE coach_invite_codes SET used_at = datetime('now') WHERE id = ?").run(invite.id);

  const student = db.prepare('SELECT id, name FROM users WHERE id = ?').get(invite.student_id);
  res.status(201).json({ student });
});

router.get('/coach/students', requireAuth, (req, res) => {
  const students = db.prepare(
    `SELECT u.id, u.name FROM coach_links cl
     JOIN users u ON u.id = cl.student_id
     WHERE cl.coach_id = ?
     ORDER BY u.name`
  ).all(req.user.id);
  res.json({ students });
});

router.get('/coach/students/:studentId/history', requireAuth, (req, res) => {
  const studentId = Number(req.params.studentId);
  if (!isLinked(req.user.id, studentId)) {
    return res.status(403).json({ error: 'Not linked to this student' });
  }

  const rows = db.prepare('SELECT * FROM analyses WHERE user_id = ? ORDER BY created_at DESC').all(studentId);
  res.json({
    analyses: rows.map((row) => ({
      id: row.id,
      shot_type: row.shot_type,
      similarity: row.similarity,
      pro_id: row.pro_id,
      angle_label: row.angle_label,
      tip: row.tip,
      created_at: row.created_at,
      result: JSON.parse(row.result_json),
    })),
  });
});

// A caller may add a note only if they're a linked coach of the analysis
// owner. phaseKey/timestampSec are each optional and mutually exclusive
// (both null = a general note).
router.post('/coach/notes', requireAuth, (req, res) => {
  const { analysisId, noteText, phaseKey, timestampSec } = req.body || {};
  if (!analysisId || !noteText) {
    return res.status(400).json({ error: 'analysisId and noteText are required' });
  }
  if (phaseKey && !VALID_PHASE_KEYS.includes(phaseKey)) {
    return res.status(400).json({ error: `phaseKey must be one of ${VALID_PHASE_KEYS.join(', ')}` });
  }

  const analysis = db.prepare('SELECT user_id FROM analyses WHERE id = ?').get(analysisId);
  if (!analysis) {
    return res.status(404).json({ error: 'Analysis not found' });
  }
  if (!isLinked(req.user.id, analysis.user_id)) {
    return res.status(403).json({ error: 'Not linked as a coach of this analysis owner' });
  }

  const info = db.prepare(
    `INSERT INTO coach_notes (coach_id, analysis_id, phase_key, timestamp_sec, note_text)
     VALUES (?, ?, ?, ?, ?)`
  ).run(req.user.id, analysisId, phaseKey ?? null, timestampSec ?? null, noteText);

  const row = db.prepare(
    `SELECT cn.*, u.name AS coach_name FROM coach_notes cn
     JOIN users u ON u.id = cn.coach_id WHERE cn.id = ?`
  ).get(info.lastInsertRowid);
  res.status(201).json(row);
});

// Accessible to both the coach who wrote a note and the student who owns
// the analysis -- either side of the relationship should see the notes.
router.get('/coach/notes', requireAuth, (req, res) => {
  const analysisId = Number(req.query.analysisId);
  if (!analysisId) {
    return res.status(400).json({ error: 'analysisId query param is required' });
  }

  const analysis = db.prepare('SELECT user_id FROM analyses WHERE id = ?').get(analysisId);
  if (!analysis) {
    return res.status(404).json({ error: 'Analysis not found' });
  }
  const isOwner = analysis.user_id === req.user.id;
  const isCoach = isLinked(req.user.id, analysis.user_id);
  if (!isOwner && !isCoach) {
    return res.status(403).json({ error: 'Not authorized to view notes on this analysis' });
  }

  const notes = db.prepare(
    `SELECT cn.*, u.name AS coach_name FROM coach_notes cn
     JOIN users u ON u.id = cn.coach_id
     WHERE cn.analysis_id = ? ORDER BY cn.created_at ASC`
  ).all(analysisId);
  res.json({ notes });
});

module.exports = router;
