const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const db = require('../db');
const requireAuth = require('../middleware/requireAuth');
const { requireAdmin } = require('../middleware/requireAdmin');
const { SCRIPTS_DIR, PYTHON } = require('../config/paths');
const { CLIPS_DIR: DRILL_CLIPS_DIR, toClipUrl } = require('../utils/drillClips');

const router = express.Router();

fs.mkdirSync(DRILL_CLIPS_DIR, { recursive: true });

const uploadDrillVideo = multer({
  storage: multer.diskStorage({
    destination: DRILL_CLIPS_DIR,
    filename: (req, file, cb) => {
      const ext = path.extname(file.originalname) || '.mp4';
      cb(null, `drill_${Date.now()}_${Math.round(Math.random() * 1e6)}${ext}`);
    },
  }),
  limits: { fileSize: 500 * 1024 * 1024 }, // 500MB -- short instructional clips, not full matches
});

const ML_STATUS_REPORTER = path.join(SCRIPTS_DIR, '00_utils', 'ml_status_report.py');
const REPORT_TIMEOUT_MS = 30 * 1000; // just reads local JSONL files, should be near-instant

const LIST_SWING_CANDIDATES = path.join(SCRIPTS_DIR, '16_shot_verification', 'list_swing_candidates.py');
const LOG_MANUAL_REVIEW = path.join(SCRIPTS_DIR, '16_shot_verification', 'log_manual_review.py');
// Pose extraction + racket/ball detection per un-cached rally clip is real
// compute (no Claude call, but not instant) -- generous ceiling for a job
// whose clips haven't been through this or batch_verify_all.py yet.
const CANDIDATES_TIMEOUT_MS = 10 * 60 * 1000;
const LOG_REVIEW_TIMEOUT_MS = 15 * 1000; // just appends a line to two JSONL files

const LIST_TIP_REVIEW_CANDIDATES = path.join(SCRIPTS_DIR, '09_coaching_ai', 'list_tip_review_candidates.py');
const LOG_MANUAL_TIP_REVIEW = path.join(SCRIPTS_DIR, '09_coaching_ai', 'log_manual_tip_review.py');
// Re-runs pose extraction per candidate analysis (no Claude call) -- same
// order of magnitude as CANDIDATES_TIMEOUT_MS above, generous ceiling for
// a batch of ~20 candidates rather than a single clip.
const TIP_REVIEW_CANDIDATES_TIMEOUT_MS = 10 * 60 * 1000;
const LOG_TIP_REVIEW_TIMEOUT_MS = 15 * 1000; // just appends a line to two JSONL files

const LIST_PRO_CLIP_REVIEW_CANDIDATES = path.join(SCRIPTS_DIR, '06_database_build', 'list_pro_clip_review_candidates.py');
const LOG_PRO_CLIP_REVIEW = path.join(SCRIPTS_DIR, '06_database_build', 'log_pro_clip_review.py');
// Just reads pro_database.json + the review log, no pose extraction --
// near-instant, but generous ceiling matches the other list routes' style.
const PRO_CLIP_REVIEW_CANDIDATES_TIMEOUT_MS = 30 * 1000;
const LOG_PRO_CLIP_REVIEW_TIMEOUT_MS = 15 * 1000; // just appends a line to one JSONL file

const LIST_BALL_LABEL_CANDIDATES = path.join(SCRIPTS_DIR, '07_ball_racket_tracking', 'list_ball_label_candidates.py');
const LOG_MANUAL_BALL_LABEL = path.join(SCRIPTS_DIR, '07_ball_racket_tracking', 'log_manual_ball_label.py');
// Just reads a JSON labels file + the review log -- near-instant.
const BALL_LABEL_CANDIDATES_TIMEOUT_MS = 30 * 1000;
const LOG_BALL_LABEL_TIMEOUT_MS = 15 * 1000; // just appends a line to one JSONL file

// Hidden Dev Page (Profile -> Settings -> Dev Page) -- every route here is
// requireAuth + requireAdmin, a real 403 for anyone but the admin allowlist
// in middleware/requireAdmin.js, regardless of what the frontend hides.
router.get('/dev/ml-status', requireAuth, requireAdmin, (req, res) => {
  const proc = spawn(PYTHON, [ML_STATUS_REPORTER]);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => proc.kill(), REPORT_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    if (code !== 0) {
      console.error('[dev] ml_status_report.py failed:', stderr.slice(-2000));
      return res.status(500).json({ error: 'Failed to generate ML status report' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch {
      console.error('[dev] failed to parse ml_status_report.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'ML status report produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    console.error('[dev] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start ML status report' });
  });
});

// Free, no-API-cost manual review tool: lists every wrist-velocity swing
// candidate for a job's rally clips, with the geometric student's opinion
// (no Claude involved) for reference by log-manual-review below.
router.get('/dev/swing-candidates/:jobId', requireAuth, requireAdmin, (req, res) => {
  const proc = spawn(PYTHON, [LIST_SWING_CANDIDATES, req.params.jobId]);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => proc.kill(), CANDIDATES_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    if (code !== 0) {
      console.error('[dev] list_swing_candidates.py failed:', stderr.slice(-2000));
      return res.status(500).json({ error: 'Failed to list swing candidates' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch {
      console.error('[dev] failed to parse list_swing_candidates.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Swing candidate list produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    console.error('[dev] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start swing candidate listing' });
  });
});

// Logs Jack's own manual verdict on one swing candidate into both training
// logs -- the free substitute for a paid Claude teacher call. Body is the
// candidate object from GET /dev/swing-candidates/:jobId (student_* fields)
// plus his verdict (is_real_shot, shot_type).
router.post('/dev/swing-candidates/label', requireAuth, requireAdmin, (req, res) => {
  const proc = spawn(PYTHON, [LOG_MANUAL_REVIEW]);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => proc.kill(), LOG_REVIEW_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    if (code !== 0) {
      console.error('[dev] log_manual_review.py failed:', stderr.slice(-2000));
      return res.status(500).json({ error: 'Failed to log review' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch {
      console.error('[dev] failed to parse log_manual_review.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Log review produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    console.error('[dev] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start review logging' });
  });

  proc.stdin.write(JSON.stringify(req.body));
  proc.stdin.end();
});

// Free, no-API-cost manual review tool for coaching-tip selection: lists
// recent saved analyses with the full scored candidate-issue list
// (tip_selector.score_issues()) re-derived alongside whichever tips were
// actually shown, so Jack can judge whether the right ones got picked --
// the same free substitute for tip_verifier.py that swing-candidates
// above is for the shot-contact/classifier verifiers.
router.get('/dev/tip-review-candidates', requireAuth, requireAdmin, (req, res) => {
  const args = [LIST_TIP_REVIEW_CANDIDATES];
  if (req.query.limit) args.push(String(req.query.limit));
  const proc = spawn(PYTHON, args);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => proc.kill(), TIP_REVIEW_CANDIDATES_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    if (code !== 0) {
      console.error('[dev] list_tip_review_candidates.py failed:', stderr.slice(-2000));
      return res.status(500).json({ error: 'Failed to list tip review candidates' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch {
      console.error('[dev] failed to parse list_tip_review_candidates.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Tip review candidate list produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    console.error('[dev] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start tip review candidate listing' });
  });
});

// Logs Jack's own manual verdict on one tip-review candidate -- the free
// substitute for a paid Claude teacher call. Body is
// {analysis_id, shot_type, deviation_features, shown_tip_ids, reviewer_pick_ids}.
router.post('/dev/tip-review/label', requireAuth, requireAdmin, (req, res) => {
  const proc = spawn(PYTHON, [LOG_MANUAL_TIP_REVIEW]);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => proc.kill(), LOG_TIP_REVIEW_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    if (code !== 0) {
      console.error('[dev] log_manual_tip_review.py failed:', stderr.slice(-2000));
      return res.status(500).json({ error: 'Failed to log tip review' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch {
      console.error('[dev] failed to parse log_manual_tip_review.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Log tip review produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    console.error('[dev] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start tip review logging' });
  });

  proc.stdin.write(JSON.stringify(req.body));
  proc.stdin.end();
});

// Free manual data-quality review tool for the pro database itself --
// mismatched footage, slow-motion clips, clips spanning the tail of one
// swing/player into the start of another (flagged directly, not derived
// from any automated check). Not a teacher-student ML loop like the
// review tools above -- this just curates data quality.
router.get('/dev/pro-clip-review-candidates', requireAuth, requireAdmin, (req, res) => {
  const args = [LIST_PRO_CLIP_REVIEW_CANDIDATES];
  if (req.query.limit) args.push(String(req.query.limit));
  const proc = spawn(PYTHON, args);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => proc.kill(), PRO_CLIP_REVIEW_CANDIDATES_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    if (code !== 0) {
      console.error('[dev] list_pro_clip_review_candidates.py failed:', stderr.slice(-2000));
      return res.status(500).json({ error: 'Failed to list pro clip review candidates' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch {
      console.error('[dev] failed to parse list_pro_clip_review_candidates.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Pro clip review candidate list produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    console.error('[dev] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start pro clip review candidate listing' });
  });
});

// Logs Jack's manual data-quality verdict on one pro-database clip. Body
// is {id, verdict, note}, verdict one of 'ok'|'mismatched'|'slow_motion'|'wrong_boundary'.
router.post('/dev/pro-clip-review/label', requireAuth, requireAdmin, (req, res) => {
  const proc = spawn(PYTHON, [LOG_PRO_CLIP_REVIEW]);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => proc.kill(), LOG_PRO_CLIP_REVIEW_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    if (code !== 0) {
      console.error('[dev] log_pro_clip_review.py failed:', stderr.slice(-2000));
      return res.status(500).json({ error: 'Failed to log pro clip review' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch {
      console.error('[dev] failed to parse log_pro_clip_review.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Log pro clip review produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    console.error('[dev] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start pro clip review logging' });
  });

  proc.stdin.write(JSON.stringify(req.body));
  proc.stdin.end();
});

// Manual ball-labeling tool for the fine-tuned ball detector project --
// serves frames the classical-detector-plus-Claude-confirm pipeline
// couldn't resolve (needs_manual_review), plus a small spot-check slice
// of already-confirmed ones, for Jack to draw a box on directly.
router.get('/dev/ball-label-candidates', requireAuth, requireAdmin, (req, res) => {
  const args = [LIST_BALL_LABEL_CANDIDATES];
  if (req.query.limit) args.push(String(req.query.limit));
  const proc = spawn(PYTHON, args);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => proc.kill(), BALL_LABEL_CANDIDATES_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    if (code !== 0) {
      console.error('[dev] list_ball_label_candidates.py failed:', stderr.slice(-2000));
      return res.status(500).json({ error: 'Failed to list ball label candidates' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch {
      console.error('[dev] failed to parse list_ball_label_candidates.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Ball label candidate list produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    console.error('[dev] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start ball label candidate listing' });
  });
});

// Logs Jack's manually-drawn ball box (or "no ball" verdict). Body is
// {file, bucket, ball_visible, box_norm}.
router.post('/dev/ball-label/label', requireAuth, requireAdmin, (req, res) => {
  const proc = spawn(PYTHON, [LOG_MANUAL_BALL_LABEL]);

  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', (chunk) => { stdout += chunk; });
  proc.stderr.on('data', (chunk) => { stderr += chunk; });

  const timeout = setTimeout(() => proc.kill(), LOG_BALL_LABEL_TIMEOUT_MS);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    if (code !== 0) {
      console.error('[dev] log_manual_ball_label.py failed:', stderr.slice(-2000));
      return res.status(500).json({ error: 'Failed to log ball label' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch {
      console.error('[dev] failed to parse log_manual_ball_label.py output:', stdout.slice(-2000));
      res.status(500).json({ error: 'Log ball label produced invalid output' });
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    console.error('[dev] failed to spawn python:', err);
    res.status(500).json({ error: 'Failed to start ball label logging' });
  });

  proc.stdin.write(JSON.stringify(req.body));
  proc.stdin.end();
});

// Drills & Lessons editor -- unfiltered (incl. archived/premium) so the
// editor UI can show/manage everything, unlike GET /drills which is the
// real user-facing, tier-gated listing (routes/drills.js).
router.get('/dev/drills', requireAuth, requireAdmin, (req, res) => {
  const items = db.prepare('SELECT * FROM drill_items ORDER BY sort_order ASC, id ASC').all();
  const stepsByItem = db.prepare('SELECT * FROM drill_routine_steps ORDER BY step_order ASC').all()
    .reduce((acc, step) => {
      (acc[step.drill_item_id] ??= []).push(step);
      return acc;
    }, {});
  res.json({
    items: items.map((item) => ({
      ...item,
      video_url: toClipUrl(item.video_path),
      steps: stepsByItem[item.id] ?? [],
    })),
  });
});

// Create (no id) or update (id present) one drill/lesson. Steps are
// reconciled by id, NOT wholesale deleted-and-reinserted -- a step's id is
// what drill_practice_attempts.step_id points at, and SQLite foreign keys
// aren't enforced in this app, so deleting and recreating every step on
// every save (even a pure title edit) used to silently orphan any practice
// history for that lesson with no error anywhere. Steps the client sends
// with an existing id are updated in place (same id, history intact); steps
// with no id are new; any existing step not present in the submitted list
// is a real removal.
router.post('/dev/drills', requireAuth, requireAdmin, uploadDrillVideo.single('video'), (req, res) => {
  const { id, kind, shot_type: shotType, title, explanation, emphasis, diagram_tip_id: diagramTipId } = req.body;
  const isPremium = req.body.is_premium === '1' || req.body.is_premium === 'true' ? 1 : 0;
  const sortOrder = Number.parseInt(req.body.sort_order, 10) || 0;

  if (!kind || !['drill', 'lesson'].includes(kind)) {
    return res.status(400).json({ error: "kind must be 'drill' or 'lesson'" });
  }
  if (!shotType || !title || !explanation) {
    return res.status(400).json({ error: 'shot_type, title, and explanation are required' });
  }

  let steps = [];
  if (req.body.steps) {
    try {
      steps = JSON.parse(req.body.steps);
    } catch {
      return res.status(400).json({ error: 'steps must be valid JSON' });
    }
  }

  const videoPath = req.file ? req.file.path : undefined;

  const save = db.transaction(() => {
    let itemId = id ? Number.parseInt(id, 10) : null;

    if (itemId) {
      const existing = db.prepare('SELECT * FROM drill_items WHERE id = ?').get(itemId);
      if (!existing) throw new Error('NOT_FOUND');
      db.prepare(`
        UPDATE drill_items
        SET kind = ?, shot_type = ?, title = ?, explanation = ?, emphasis = ?,
            diagram_tip_id = ?, is_premium = ?, sort_order = ?,
            video_path = COALESCE(?, video_path)
        WHERE id = ?
      `).run(kind, shotType, title, explanation, emphasis ?? null, diagramTipId ?? null, isPremium, sortOrder, videoPath ?? null, itemId);
    } else {
      const result = db.prepare(`
        INSERT INTO drill_items (kind, shot_type, title, video_path, explanation, emphasis, diagram_tip_id, is_premium, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(kind, shotType, title, videoPath ?? null, explanation, emphasis ?? null, diagramTipId ?? null, isPremium, sortOrder);
      itemId = result.lastInsertRowid;
    }

    const existingStepIds = new Set(
      db.prepare('SELECT id FROM drill_routine_steps WHERE drill_item_id = ?').all(itemId).map((s) => s.id)
    );
    const keptStepIds = new Set();

    const insertStep = db.prepare(`
      INSERT INTO drill_routine_steps (drill_item_id, step_order, label, shot_type, target_reps)
      VALUES (?, ?, ?, ?, ?)
    `);
    const updateStep = db.prepare(`
      UPDATE drill_routine_steps SET step_order = ?, label = ?, shot_type = ?, target_reps = ?
      WHERE id = ? AND drill_item_id = ?
    `);
    steps.forEach((step, i) => {
      const stepId = step.id ? Number.parseInt(step.id, 10) : null;
      if (stepId && existingStepIds.has(stepId)) {
        updateStep.run(i, step.label, step.shot_type ?? null, step.target_reps ?? null, stepId, itemId);
        keptStepIds.add(stepId);
      } else {
        insertStep.run(itemId, i, step.label, step.shot_type ?? null, step.target_reps ?? null);
      }
    });

    // Only steps genuinely dropped from the submitted list get removed --
    // this deletion is a real edit, not the old delete-everything-then-
    // reinsert artifact that used to orphan every step's practice history.
    const removedStepIds = [...existingStepIds].filter((sid) => !keptStepIds.has(sid));
    if (removedStepIds.length) {
      const placeholders = removedStepIds.map(() => '?').join(',');
      db.prepare(`DELETE FROM drill_routine_steps WHERE id IN (${placeholders})`).run(...removedStepIds);
    }

    return itemId;
  });

  try {
    const itemId = save();
    res.json({ id: itemId });
  } catch (err) {
    if (err.message === 'NOT_FOUND') return res.status(404).json({ error: 'Drill/lesson not found' });
    console.error('[dev] failed to save drill/lesson:', err);
    res.status(500).json({ error: 'Failed to save' });
  }
});

// Soft-delete -- same spirit as rally_clips' archived flag, never hard-
// deleted so past drill_practice_attempts/analyses referencing it stay valid.
router.delete('/dev/drills/:id', requireAuth, requireAdmin, (req, res) => {
  const result = db.prepare('UPDATE drill_items SET archived = 1 WHERE id = ?').run(req.params.id);
  if (result.changes === 0) return res.status(404).json({ error: 'Not found' });
  res.json({ ok: true });
});

module.exports = router;
