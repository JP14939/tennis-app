// Re-checks the invariants in ./invariants.js against rows ALREADY STORED.
//
// Route validation only guards writes made from now on -- it says nothing
// about what a past bug, a direct sqlite3 session, a half-finished migration,
// or a seed script already put in the file. This module answers the separate
// question "is what's in there actually valid?", which is the part that can be
// run against production data.
//
// Two categories of check:
//   - VALUE DOMAIN: the same rules the validation layer enforces at the door,
//     asked of stored rows.
//   - STRUCTURAL: relationships between columns/tables that no single request
//     can see and therefore no route-level validator can enforce (pair
//     ordering, self-referencing links, clip timing coherence, orphans).
//
// Pure and db-injected so tests can point it at an in-memory database with
// deliberately-corrupt rows. Read-only: it reports, it never repairs.

const {
  SHOT_TYPES,
  DRILL_SHOT_TYPES,
  DRILL_KINDS,
  OUTCOME_TAGS,
  TIERS,
  JOB_STATUSES,
  COURT_SOURCES,
  AVAILABILITY_STATUSES,
  MAX_SETS_IN_A_MATCH,
  MAX_VIDEO_SECONDS,
  PHASE_KEYS,
  isBoundaryNote,
  isIsoDateTime,
} = require('./invariants');

// SQL fragment for `col IN ('a','b')` built from a JS vocabulary, so the
// checker can't drift from the catalog. Values are internal constants (never
// user input), but they're still escaped rather than interpolated raw.
function sqlIn(vocabulary) {
  return vocabulary.map((v) => `'${String(v).replace(/'/g, "''")}'`).join(', ');
}

// A stored REAL column can hold text (SQLite type affinity does not coerce a
// bound string), and text sorts ABOVE every number in ORDER BY -- so "is this
// actually a number?" is a real check at rest, not a tautology.
function numericTypeGuard(column) {
  return `typeof(${column}) NOT IN ('integer', 'real')`;
}

// Each check yields the offending rows; `count` is how many, `sample` is up to
// SAMPLE_LIMIT of them so a report can show what's actually wrong.
const SAMPLE_LIMIT = 5;

// ── Value-domain checks ─────────────────────────────────────────────────────

const VALUE_DOMAIN_CHECKS = [
  {
    name: 'analyses.shot_type',
    description: `every analysis is one of the shot types the ML pipeline analyses (${SHOT_TYPES.join(', ')})`,
    sql: `SELECT id, user_id, shot_type FROM analyses WHERE shot_type NOT IN (${sqlIn(SHOT_TYPES)})`,
  },
  {
    name: 'analyses.similarity',
    description: 'every similarity is a number between 0 and 100 (it is a percentage)',
    sql: `SELECT id, user_id, similarity FROM analyses
          WHERE ${numericTypeGuard('similarity')} OR similarity < 0 OR similarity > 100`,
  },
  {
    name: 'analyses.shot_verdict',
    description: 'no analysis is both flagged as not-a-shot and confirmed as a real shot',
    sql: 'SELECT id, user_id FROM analyses WHERE flagged_not_shot = 1 AND confirmed_real_shot = 1',
  },
  {
    name: 'rally_clips.outcome_tag',
    description: `a tagged rally carries one of the review screen's answers (${OUTCOME_TAGS.join(', ')})`,
    sql: `SELECT id, user_id, outcome_tag FROM rally_clips
          WHERE outcome_tag IS NOT NULL AND outcome_tag NOT IN (${sqlIn(OUTCOME_TAGS)})`,
  },
  {
    name: 'rally_clips.timing',
    description: 'each clip starts at or after 0, ends after it starts, and its duration matches that span',
    // 0.5s tolerance: duration_sec comes from the detector's own frame maths,
    // so exact float equality with (end - start) is not expected.
    sql: `SELECT id, start_sec, end_sec, duration_sec FROM rally_clips
          WHERE start_sec < 0 OR end_sec <= start_sec
             OR ABS(duration_sec - (end_sec - start_sec)) > 0.5`,
  },
  {
    name: 'courts.coordinates',
    description: 'every court sits at a real latitude/longitude',
    sql: `SELECT id, name, latitude, longitude FROM courts
          WHERE ${numericTypeGuard('latitude')} OR ${numericTypeGuard('longitude')}
             OR latitude NOT BETWEEN -90 AND 90 OR longitude NOT BETWEEN -180 AND 180`,
  },
  {
    // clubs.latitude/longitude has the exact same shape as courts' -- same
    // NOT NULL REAL columns, no CHECK constraint -- but only clubs.js's
    // scripts/clusterCourts.js writes it (no route does), so a bad centroid
    // from that offline script had no check to catch it before poisoning
    // every haversine-distance computation against that club silently.
    name: 'clubs.coordinates',
    description: 'every club sits at a real latitude/longitude',
    sql: `SELECT id, name, latitude, longitude FROM clubs
          WHERE ${numericTypeGuard('latitude')} OR ${numericTypeGuard('longitude')}
             OR latitude NOT BETWEEN -90 AND 90 OR longitude NOT BETWEEN -180 AND 180`,
  },
  {
    name: 'courts.source',
    description: `every court came from a known source (${COURT_SOURCES.join(', ')})`,
    sql: `SELECT id, name, source FROM courts WHERE source NOT IN (${sqlIn(COURT_SOURCES)})`,
  },
  {
    name: 'courts.verified',
    description: 'verified is a boolean flag (0 or 1)',
    sql: 'SELECT id, name, verified FROM courts WHERE verified NOT IN (0, 1)',
  },
  {
    name: 'friend_matches.sets',
    description: `set counts are whole numbers between 0 and ${MAX_SETS_IN_A_MATCH}`,
    sql: `SELECT id, logged_by, sets_won, sets_lost FROM friend_matches
          WHERE ${numericTypeGuard('sets_won')} OR ${numericTypeGuard('sets_lost')}
             OR sets_won < 0 OR sets_lost < 0
             OR sets_won > ${MAX_SETS_IN_A_MATCH} OR sets_lost > ${MAX_SETS_IN_A_MATCH}
             OR sets_won != CAST(sets_won AS INTEGER) OR sets_lost != CAST(sets_lost AS INTEGER)`,
  },
  {
    name: 'availability_posts.window',
    description: 'an availability post that names an end time ends after it starts',
    sql: `SELECT id, user_id, start_time, end_time FROM availability_posts
          WHERE end_time IS NOT NULL AND end_time <= start_time`,
  },
  {
    name: 'availability_posts.status',
    description: `every post is ${AVAILABILITY_STATUSES.join(' or ')}`,
    sql: `SELECT id, status FROM availability_posts WHERE status NOT IN (${sqlIn(AVAILABILITY_STATUSES)})`,
  },
  // coach.js validates both of these at write time via optional(isPhaseKey) /
  // optional(isTimestampSec), but neither had an at-rest counterpart -- the
  // one pairing this module exists to keep symmetrical.
  {
    name: 'coach_notes.phase_key',
    description: `a phase-pinned note names a real phase (${PHASE_KEYS.join(', ')})`,
    sql: `SELECT id, analysis_id, phase_key FROM coach_notes
          WHERE phase_key IS NOT NULL AND phase_key NOT IN (${sqlIn(PHASE_KEYS)})`,
  },
  {
    name: 'coach_notes.timestamp_sec',
    description: `a timestamp-pinned note sits between 0 and ${MAX_VIDEO_SECONDS} seconds into the video`,
    sql: `SELECT id, analysis_id, timestamp_sec FROM coach_notes
          WHERE timestamp_sec IS NOT NULL
            AND (${numericTypeGuard('timestamp_sec')}
                 OR timestamp_sec < 0 OR timestamp_sec > ${MAX_VIDEO_SECONDS})`,
  },
  {
    name: 'celebrity_scores.score',
    description: 'a curated leaderboard score is a number between 0 and 100, like any other score',
    sql: `SELECT id, name, score FROM celebrity_scores
          WHERE ${numericTypeGuard('score')} OR score < 0 OR score > 100`,
  },
  {
    name: 'celebrity_scores.shot_type',
    description: `every curated leaderboard entry targets one of the ML pipeline's shot types (${SHOT_TYPES.join(', ')})`,
    sql: `SELECT id, name, shot_type FROM celebrity_scores WHERE shot_type NOT IN (${sqlIn(SHOT_TYPES)})`,
  },
  {
    name: 'users.email',
    description: 'every email is stored normalised to lowercase, so the UNIQUE constraint means what it says',
    sql: 'SELECT id, email FROM users WHERE email != lower(email)',
  },
  {
    name: 'users.tier',
    description: `every account is ${TIERS.join(' or ')}`,
    sql: `SELECT id, email, tier FROM users WHERE tier NOT IN (${sqlIn(TIERS)})`,
  },
  {
    name: 'drill_items.kind',
    description: `every library item is a ${DRILL_KINDS.join(' or a ')}`,
    sql: `SELECT id, title, kind FROM drill_items WHERE kind NOT IN (${sqlIn(DRILL_KINDS)})`,
  },
  {
    name: 'drill_items.shot_type',
    description: `every library item targets ${DRILL_SHOT_TYPES.join(', ')}`,
    sql: `SELECT id, title, shot_type FROM drill_items WHERE shot_type NOT IN (${sqlIn(DRILL_SHOT_TYPES)})`,
  },
  {
    name: 'highlight_jobs.status',
    description: `every detection job is ${JOB_STATUSES.join(', ')}`,
    sql: `SELECT id, user_id, status FROM highlight_jobs WHERE status NOT IN (${sqlIn(JOB_STATUSES)})`,
  },
  {
    name: 'reel_jobs.status',
    description: `every reel job is ${JOB_STATUSES.join(', ')}`,
    sql: `SELECT id, user_id, status FROM reel_jobs WHERE status NOT IN (${sqlIn(JOB_STATUSES)})`,
  },
];

// ── Structural checks ───────────────────────────────────────────────────────
// Relationships spanning columns or tables. None of these can be enforced by
// validating one request body, because none of them are visible from one.

const STRUCTURAL_CHECKS = [
  {
    name: 'messages.pair_ordering',
    description: 'every thread stores its two users as [min(id), max(id)] -- an unsorted pair makes the whole conversation invisible to both sides',
    sql: 'SELECT id, user_a_id, user_b_id FROM messages WHERE user_a_id >= user_b_id',
  },
  {
    name: 'messages.sender_in_thread',
    description: 'the sender of a message is one of the two people in the thread',
    sql: 'SELECT id, user_a_id, user_b_id, sender_id FROM messages WHERE sender_id NOT IN (user_a_id, user_b_id)',
  },
  {
    name: 'friend_links.pair_ordering',
    description: 'a friendship is one row stored as [min(id), max(id)], and nobody is their own friend',
    sql: 'SELECT id, user_a_id, user_b_id FROM friend_links WHERE user_a_id >= user_b_id',
  },
  {
    name: 'coach_links.self',
    description: 'nobody coaches themselves',
    sql: 'SELECT id, coach_id FROM coach_links WHERE coach_id = student_id',
  },
  {
    name: 'user_blocks.self',
    description: 'nobody blocks themselves',
    sql: 'SELECT id, blocker_id FROM user_blocks WHERE blocker_id = blocked_id',
  },
  {
    name: 'friend_matches.self',
    description: 'nobody logs a match against themselves',
    sql: 'SELECT id, logged_by FROM friend_matches WHERE logged_by = opponent_id',
  },
  {
    name: 'shared_analyses.owner',
    description: "a share's recorded owner is the analysis's actual owner",
    sql: `SELECT sa.id, sa.owner_id, a.user_id AS analysis_owner
          FROM shared_analyses sa JOIN analyses a ON a.id = sa.analysis_id
          WHERE sa.owner_id != a.user_id`,
  },
  {
    name: 'shared_analyses.self',
    description: 'an analysis is never shared with its own owner',
    sql: 'SELECT id, owner_id, friend_id FROM shared_analyses WHERE owner_id = friend_id',
  },
  {
    name: 'drill_routine_steps.ordering',
    description: 'a lesson never has two practice steps claiming the same position',
    sql: `SELECT drill_item_id, step_order, COUNT(*) AS n FROM drill_routine_steps
          GROUP BY drill_item_id, step_order HAVING n > 1`,
  },
  {
    name: 'rally_clips.job_owner',
    description: "a rally clip belongs to the same user as the detection job that produced it",
    sql: `SELECT rc.id, rc.user_id, hj.user_id AS job_owner
          FROM rally_clips rc JOIN highlight_jobs hj ON hj.id = rc.job_id
          WHERE rc.user_id != hj.user_id`,
  },
];

// ── Orphan canaries ─────────────────────────────────────────────────────────
// db.js never sets `PRAGMA foreign_keys = ON` (confirmed -- there is no such
// pragma call anywhere in that file), and SQLite's own default for that
// pragma is OFF, not ON. The comment that used to sit here claimed
// better-sqlite3 turns it on by default, which is not true of the underlying
// SQLite library -- every `REFERENCES` in the schema below is decorative,
// and these checks are catching real, currently-possible orphaned rows
// today, not standing guard against a hypothetical future misconfiguration.
// This list used to cover only 17 of the schema's ~45 REFERENCES columns;
// the rest is filled in below so `npm run verify:db` actually sees the
// whole foreign-key graph.

const ORPHAN_CHECKS = [
  ['analyses', 'user_id', 'users'],
  ['analysis_usage', 'user_id', 'users'],
  ['payment_events', 'user_id', 'users'],
  ['highlight_jobs', 'user_id', 'users'],
  ['coach_notes', 'analysis_id', 'analyses'],
  ['coach_notes', 'coach_id', 'users'],
  ['shared_analyses', 'analysis_id', 'analyses'],
  ['shared_analyses', 'owner_id', 'users'],
  ['shared_analyses', 'friend_id', 'users'],
  ['swing_annotations', 'analysis_id', 'analyses'],
  ['swing_annotations', 'author_id', 'users'],
  ['drill_practice_attempts', 'user_id', 'users'],
  ['drill_practice_attempts', 'step_id', 'drill_routine_steps'],
  ['drill_practice_attempts', 'analysis_id', 'analyses'],
  ['drill_routine_steps', 'drill_item_id', 'drill_items'],
  ['rally_clips', 'job_id', 'highlight_jobs'],
  ['rally_clips', 'user_id', 'users'],
  ['reel_jobs', 'highlight_job_id', 'highlight_jobs'],
  ['reel_jobs', 'user_id', 'users'],
  ['courts', 'cost_updated_by', 'users'],
  ['courts', 'submitted_by', 'users'],
  ['court_confirmations', 'court_id', 'courts'],
  ['court_confirmations', 'user_id', 'users'],
  ['court_watches', 'court_id', 'courts'],
  ['court_watches', 'user_id', 'users'],
  ['club_courts', 'club_id', 'clubs'],
  ['club_courts', 'court_id', 'courts'],
  ['club_watches', 'user_id', 'users'],
  ['club_watches', 'club_id', 'clubs'],
  ['availability_posts', 'court_id', 'courts'],
  ['availability_posts', 'user_id', 'users'],
  ['message_reports', 'message_id', 'messages'],
  ['message_reports', 'reporter_id', 'users'],
  ['messages', 'user_a_id', 'users'],
  ['messages', 'user_b_id', 'users'],
  ['messages', 'sender_id', 'users'],
  ['user_blocks', 'blocker_id', 'users'],
  ['user_blocks', 'blocked_id', 'users'],
  ['friend_codes', 'user_id', 'users'],
  ['friend_links', 'user_a_id', 'users'],
  ['friend_links', 'user_b_id', 'users'],
  ['friend_matches', 'logged_by', 'users'],
  ['friend_matches', 'opponent_id', 'users'],
  ['celebrity_scores', 'added_by', 'users'],
  ['password_resets', 'user_id', 'users'],
].map(([table, column, parent]) => ({
  name: `${table}.${column}`,
  description: `every ${table} row points at a ${parent} row that still exists`,
  // c.rowid rather than c.id -- club_courts is a pure join table with no `id`
  // column of its own, and rowid identifies a row in every table here.
  sql: `SELECT c.rowid AS rowid, c.${column} AS dangling_ref
        FROM ${table} c LEFT JOIN ${parent} p ON p.id = c.${column}
        WHERE c.${column} IS NOT NULL AND p.id IS NULL`,
}));

// ── JS-side checks ──────────────────────────────────────────────────────────
// Two invariants can't be expressed as a single SQL predicate: the CSV grammar
// of boundary_note, and "is this string a real date in a plausible year".
// Both reuse the exact predicate the validation layer uses, rather than a
// SQL approximation of it -- so at-rest and at-the-door can't disagree.

const JS_CHECKS = [
  {
    name: 'rally_clips.boundary_note',
    description: "boundary notes form a valid comma-joined list, with 'ok'/'should_split' standing alone",
    run: (db) => db.prepare('SELECT id, user_id, boundary_note FROM rally_clips WHERE boundary_note IS NOT NULL')
      .all()
      .filter((row) => !isBoundaryNote(row.boundary_note)),
  },
  {
    name: 'friend_matches.played_at',
    description: 'every match has a parseable date in a plausible year (it is a sort key and a rendered date)',
    run: (db) => db.prepare('SELECT id, logged_by, played_at FROM friend_matches').all()
      .filter((row) => !isIsoDateTime(row.played_at)),
  },
  {
    name: 'availability_posts.start_time',
    description: 'every availability post has a parseable start time in a plausible year',
    run: (db) => db.prepare('SELECT id, user_id, start_time FROM availability_posts').all()
      .filter((row) => !isIsoDateTime(row.start_time)),
  },
  {
    // courts.js validates end_time with the same isIsoDateTime predicate as
    // start_time, but only start_time was re-checked here. The relational
    // `end_time <= start_time` check above can't catch an end_time that isn't
    // a real date at all -- that one renders as "Invalid Date" to every
    // watcher of the court and never surfaced in a report.
    name: 'availability_posts.end_time',
    description: 'an availability post that names an end time has it parseable and in a plausible year',
    run: (db) => db.prepare('SELECT id, user_id, end_time FROM availability_posts WHERE end_time IS NOT NULL').all()
      .filter((row) => !isIsoDateTime(row.end_time)),
  },
];

const ALL_CHECKS = [
  ...VALUE_DOMAIN_CHECKS.map((c) => ({ ...c, category: 'value-domain' })),
  ...STRUCTURAL_CHECKS.map((c) => ({ ...c, category: 'structural' })),
  ...ORPHAN_CHECKS.map((c) => ({ ...c, category: 'orphan' })),
  ...JS_CHECKS.map((c) => ({ ...c, category: 'value-domain' })),
];

// Runs every check against `db` and returns ONLY the violated ones, each as
// { name, category, description, count, sample }. An empty array means the
// stored data satisfies every invariant in ./invariants.js.
function runIntegrityChecks(db) {
  const violations = [];

  for (const check of ALL_CHECKS) {
    const rows = check.run ? check.run(db) : db.prepare(check.sql).all();
    if (rows.length > 0) {
      violations.push({
        name: check.name,
        category: check.category,
        description: check.description,
        count: rows.length,
        sample: rows.slice(0, SAMPLE_LIMIT),
      });
    }
  }

  return violations;
}

module.exports = { runIntegrityChecks, ALL_CHECKS, SAMPLE_LIMIT };
