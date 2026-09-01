const express = require('express');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { redeemInviteCode, generateInviteCode } = require('../utils/inviteCodes');
const {
  PHASE_KEYS, MAX_LENGTHS, isPhaseKey, isText, isTimestampSec, isPositiveIntegerId,
} = require('../domain/invariants');
const { validate, optional, oneOfMessage } = require('../validation/validateBody');
const { safeJsonParse } = require('../utils/safeJsonParse');

const router = express.Router();

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
    code = generateInviteCode();
  } while (db.prepare('SELECT 1 FROM coach_invite_codes WHERE code = ?').get(code));

  db.prepare('INSERT INTO coach_invite_codes (student_id, code) VALUES (?, ?)').run(req.user.id, code);
  res.status(201).json({ code });
});

router.post('/coach/link', requireAuth, (req, res) => {
  const { code } = req.body || {};
  if (!code) {
    return res.status(400).json({ error: 'code is required' });
  }

  const { outcome, CODE_NOT_FOUND, SELF_LINK } = redeemInviteCode({
    inviteTable: 'coach_invite_codes',
    ownerIdColumn: 'student_id',
    code,
    requesterId: req.user.id,
    insertLink: (invite) => {
      db.prepare('INSERT OR IGNORE INTO coach_links (coach_id, student_id) VALUES (?, ?)')
        .run(req.user.id, invite.student_id);
    },
  });
  if (outcome === CODE_NOT_FOUND) {
    return res.status(404).json({ error: 'Invalid or already-used invite code' });
  }
  if (outcome === SELF_LINK) {
    return res.status(400).json({ error: "You can't link to your own invite code" });
  }

  const student = db.prepare('SELECT id, name FROM users WHERE id = ?').get(outcome);
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
  // A non-numeric :studentId used to silently become NaN and degrade to
  // isLinked() returning false (a correct-looking 403) instead of a clean
  // 400 -- same reasoning/fix as friends.js's matches routes.
  if (!Number.isInteger(studentId)) {
    return res.status(400).json({ error: 'Invalid student id' });
  }
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
      // See history.js's serializeRow -- one corrupted row used to crash
      // this whole list for the coach instead of just coming back null.
      result: safeJsonParse(row.result_json, `analysis ${row.id}`),
    })),
  });
});

// A caller may add a note only if they're a linked coach of the analysis
// owner. phaseKey/timestampSec are each optional and mutually exclusive
// (both null = a general note).
router.post('/coach/notes', requireAuth, (req, res) => {
  const { analysisId, noteText, phaseKey, timestampSec } = req.body || {};

  // noteText and timestampSec were previously bound straight into the INSERT
  // with only a truthy check between them and better-sqlite3 -- a non-string
  // noteText or a non-numeric timestampSec threw inside the driver and came
  // back as a 500, the same class of bug already fixed for cost_info in
  // courts.js. A timestamp is a video offset, so it can't be negative.
  const bad = validate([
    ['analysisId', analysisId, isPositiveIntegerId, 'must be a valid analysis id'],
    ['noteText', noteText, isText(MAX_LENGTHS.noteText), `must be text of ${MAX_LENGTHS.noteText} characters or fewer`],
    ['phaseKey', phaseKey, optional(isPhaseKey), oneOfMessage(PHASE_KEYS)],
    ['timestampSec', timestampSec, optional(isTimestampSec), 'must be a non-negative number of seconds'],
  ]);
  if (bad) return res.status(400).json(bad);

  // "Mutually exclusive" was documented here and in db.js's schema comment but
  // enforced by neither -- each field was only validated independently, so a
  // request setting both stored a note claiming to be pinned to a phase AND to
  // a timestamp at once, a shape ResultsScreen and SyncCompareScreen both
  // filter on and neither can render coherently.
  if (phaseKey != null && timestampSec != null) {
    return res.status(400).json({
      error: 'phaseKey and timestampSec are mutually exclusive', field: 'phaseKey',
    });
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
  // Checked as an id rather than just coerced with Number(): '1.5' and '1e3'
  // both survive Number() and then silently match nothing.
  if (!isPositiveIntegerId(req.query.analysisId)) {
    return res.status(400).json({ error: 'analysisId must be a valid analysis id', field: 'analysisId' });
  }
  const analysisId = Number(req.query.analysisId);

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
