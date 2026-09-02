const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');
const { SHOT_TYPES } = require('./config/shotTypes');

// SQL fragment for `col IN ('a','b')` built from a JS vocabulary, so a schema
// CHECK constraint can't drift from the same list domain/invariants.js and
// the routes validate against. See SHOT_TYPES's own comment in
// config/shotTypes.js -- this constraint used to be a 6th hardcoded copy.
const shotTypesSqlIn = SHOT_TYPES.map((v) => `'${v}'`).join(', ');

const DATA_DIR = path.join(__dirname, '..', 'data');
fs.mkdirSync(DATA_DIR, { recursive: true });

// DB_PATH override lets tests point at an isolated file (or ':memory:')
// instead of mutating the real dev/prod database on every `require('../db')`.
const DB_PATH = process.env.DB_PATH || path.join(DATA_DIR, 'app.db');
const db = new Database(DB_PATH);

// WAL needs proper mmap/shared-memory support from the underlying
// filesystem -- works fine on a normal disk or a native Linux bind mount,
// but some virtualized mounts (confirmed: Docker Desktop for Windows' file
// sharing layer) can't open the .db-shm file and throw SQLITE_IOERR on
// startup. Non-fatal: fall back to the default rollback-journal mode rather
// than crash the whole server over a filesystem that doesn't support WAL.
try {
  db.pragma('journal_mode = WAL');
} catch (err) {
  console.error('[db] WAL mode unavailable on this filesystem, falling back to default journal mode:', err.message);
}

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name          TEXT NOT NULL,
    tier          TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'premium')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS analyses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    shot_type    TEXT NOT NULL,
    similarity   REAL NOT NULL,
    pro_id       TEXT,
    angle_label  TEXT,
    tip          TEXT,
    result_json  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS analysis_usage (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- Audit trail only -- users.tier stays the single source of truth for
  -- gating, updated directly by the RevenueCat webhook handler. This table
  -- just keeps the raw event history for debugging payment issues.
  CREATE TABLE IF NOT EXISTS payment_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id),
    event_type   TEXT NOT NULL,
    raw_payload  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- One row per uploaded match/practice video processed by the rally
  -- detector. Long-running (pose extraction over 10+ minutes of footage),
  -- so this is a background job the app polls for rather than a
  -- request-response call like /api/analyse.
  CREATE TABLE IF NOT EXISTS highlight_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    video_path   TEXT NOT NULL,
    error        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
  );

  -- One row per detected rally clip. outcome_tag stays NULL until the user
  -- reviews it; archived flips to 1 only once they actually save it (not
  -- just because it was detected), so a rejected/skipped clip never shows
  -- up in the Archive.
  CREATE TABLE IF NOT EXISTS rally_clips (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       INTEGER NOT NULL REFERENCES highlight_jobs(id),
    user_id      INTEGER NOT NULL REFERENCES users(id),
    clip_path    TEXT NOT NULL,
    start_sec    REAL NOT NULL,
    end_sec      REAL NOT NULL,
    duration_sec REAL NOT NULL,
    swing_count  INTEGER,
    outcome_tag  TEXT,
    archived     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS push_tokens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    token        TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- Coach collaboration mode. Coaching is a relationship between two
  -- ordinary accounts, not a separate role/tier -- any user can generate an
  -- invite code (as a student) and separately link to someone else's code
  -- (as a coach).
  CREATE TABLE IF NOT EXISTS coach_invite_codes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   INTEGER NOT NULL REFERENCES users(id),
    code         TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    used_at      TEXT
  );

  CREATE TABLE IF NOT EXISTS coach_links (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    coach_id     INTEGER NOT NULL REFERENCES users(id),
    student_id   INTEGER NOT NULL REFERENCES users(id),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(coach_id, student_id)
  );

  -- A note is tied to at most one of phase_key ('backswing'/'contact'/
  -- 'follow_through'/'body_rotation', matching ResultsScreen's phase cards)
  -- or timestamp_sec (a raw video-relative second, for SyncCompareScreen) --
  -- both may be NULL for a general note on the whole analysis.
  CREATE TABLE IF NOT EXISTS coach_notes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    coach_id      INTEGER NOT NULL REFERENCES users(id),
    analysis_id   INTEGER NOT NULL REFERENCES analyses(id),
    phase_key     TEXT,
    timestamp_sec REAL,
    note_text     TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- One row per highlight-reel stitch request. Same background-job shape as
  -- highlight_jobs -- POST /highlights/jobs/:id/reel used to spawn
  -- stitch_clips.py and block the request/response for up to REEL_TIMEOUT_MS,
  -- with no server-side record if the client gave up waiting. Now it enqueues
  -- a row here and returns immediately; the client polls
  -- GET /highlights/reel-jobs/:id instead.
  CREATE TABLE IF NOT EXISTS reel_jobs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    highlight_job_id INTEGER NOT NULL REFERENCES highlight_jobs(id),
    user_id          INTEGER NOT NULL REFERENCES users(id),
    status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    rally_ids        TEXT NOT NULL,
    output_path      TEXT,
    error            TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at     TEXT
  );

  -- Find Games: real-world tennis courts (seeded from OpenStreetMap via
  -- backend/scripts/seedCourts.js, or added ad hoc by a user), plus who's
  -- watching each court and who's posted "I'm free to play" there.
  CREATE TABLE IF NOT EXISTS courts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    source          TEXT NOT NULL DEFAULT 'osm' CHECK (source IN ('osm', 'user')),
    osm_id          TEXT UNIQUE,
    cost_info       TEXT,
    cost_updated_by INTEGER REFERENCES users(id),
    cost_updated_at TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS court_watches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    court_id   INTEGER NOT NULL REFERENCES courts(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, court_id)
  );

  -- Crowd-sourced verification for user-dropped-pin courts (OSM-seeded
  -- courts are trusted immediately -- see courts.verified below). Each row
  -- is one other user independently confirming a pin is a real court; once
  -- enough distinct confirmations land, routes/courts.js flips
  -- courts.verified to 1. UNIQUE stops one account confirming twice.
  CREATE TABLE IF NOT EXISTS court_confirmations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    court_id   INTEGER NOT NULL REFERENCES courts(id),
    user_id    INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(court_id, user_id)
  );

  CREATE TABLE IF NOT EXISTS availability_posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    court_id   INTEGER NOT NULL REFERENCES courts(id),
    start_time TEXT NOT NULL,
    end_time   TEXT,
    note       TEXT,
    status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'cancelled')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- A "club" is a cluster of 2+ courts close enough together to be one real
  -- venue (a tennis club, a park with several courts) -- computed by
  -- scripts/clusterCourts.js, not user-editable. Stored (rather than
  -- clustered fresh on every request) so club identity -- and therefore
  -- club_watches rows -- stays stable as new courts get added nearby later.
  CREATE TABLE IF NOT EXISTS clubs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    latitude   REAL NOT NULL,
    longitude  REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- One row per court that belongs to a club. A court not in this table is
  -- just a standalone court (no club to watch beyond the per-court watch).
  CREATE TABLE IF NOT EXISTS club_courts (
    club_id  INTEGER NOT NULL REFERENCES clubs(id),
    court_id INTEGER NOT NULL REFERENCES courts(id) UNIQUE
  );

  -- Same shape as court_watches, but at the club level -- lets someone get
  -- notified about availability at any court in a club without needing to
  -- be friends with (or even know) whoever posts it.
  CREATE TABLE IF NOT EXISTS club_watches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    club_id    INTEGER NOT NULL REFERENCES clubs(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, club_id)
  );

  -- Simple 1:1 messaging. user_a_id/user_b_id are always stored as
  -- [min(id), max(id)] (see threadPair() in routes/messages.js) so a whole
  -- thread is one WHERE user_a_id = ? AND user_b_id = ? query regardless of
  -- who sent which message -- sender_id carries the actual direction.
  CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_a_id  INTEGER NOT NULL REFERENCES users(id),
    user_b_id  INTEGER NOT NULL REFERENCES users(id),
    sender_id  INTEGER NOT NULL REFERENCES users(id),
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    read_at    TEXT
  );

  -- Blocking is directional (A blocking B doesn't mean B has blocked A),
  -- but sending is checked against BOTH directions (routes/messages.js) --
  -- so either party blocking the other stops new messages, while each
  -- person's own block list only reflects decisions they made themselves.
  CREATE TABLE IF NOT EXISTS user_blocks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    blocker_id INTEGER NOT NULL REFERENCES users(id),
    blocked_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(blocker_id, blocked_id)
  );

  -- Minimal moderation trail -- no in-app review queue/admin UI yet, just a
  -- durable record of what was reported and why, so a human can query it
  -- directly (e.g. via the DB) if a real complaint comes in.
  CREATE TABLE IF NOT EXISTS message_reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER NOT NULL REFERENCES messages(id),
    reporter_id INTEGER NOT NULL REFERENCES users(id),
    reason      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- Friends: same invite-code pattern as coach_invite_codes/coach_links
  -- (routes/coach.js), adapted from asymmetric (coach/student) to symmetric
  -- (friend/friend) -- redeeming a code is the mutual-consent step, no
  -- separate accept/reject flow.
  CREATE TABLE IF NOT EXISTS friend_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    code       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    used_at    TEXT
  );

  -- user_a_id/user_b_id always stored as [min(id), max(id)] (see
  -- sortedPair() in routes/friends.js) so a friendship is one row
  -- regardless of who initiated it.
  CREATE TABLE IF NOT EXISTS friend_links (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_a_id  INTEGER NOT NULL REFERENCES users(id),
    user_b_id  INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_a_id, user_b_id)
  );

  -- Manually-logged match results between friends. sets_won/sets_lost are
  -- always relative to logged_by, not a fixed side -- single-sided entry,
  -- no confirmation step (see HANDOVER.md for the known limitation: two
  -- friends separately logging the same real match isn't deduplicated).
  CREATE TABLE IF NOT EXISTS friend_matches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_by    INTEGER NOT NULL REFERENCES users(id),
    opponent_id  INTEGER NOT NULL REFERENCES users(id),
    played_at    TEXT NOT NULL,
    sets_won     INTEGER NOT NULL,
    sets_lost    INTEGER NOT NULL,
    score_detail TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- Explicit per-swing sharing -- unlike coach linking (full access once
  -- linked), a friend only ever sees an analysis the owner actively shared
  -- with them via this table, never their whole history.
  CREATE TABLE IF NOT EXISTS shared_analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id),
    owner_id    INTEGER NOT NULL REFERENCES users(id),
    friend_id   INTEGER NOT NULL REFERENCES users(id),
    shared_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(analysis_id, friend_id)
  );

  -- Persisted freehand annotations from SyncCompareScreen's AnnotationCanvas
  -- (pen/line/arrow/circle strokes, raw pane-local pixel coords). One
  -- upserted row per (analysis, author) -- saving again overwrites your own
  -- previous save rather than creating a new one. Access (who may read/write
  -- a given analysis's annotations) is checked in routes/annotations.js, not
  -- enforced here.
  CREATE TABLE IF NOT EXISTS swing_annotations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id    INTEGER NOT NULL REFERENCES analyses(id),
    author_id      INTEGER NOT NULL REFERENCES users(id),
    pane_a_strokes TEXT NOT NULL,
    pane_b_strokes TEXT NOT NULL,
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(analysis_id, author_id)
  );

  -- Manually-curated pro/celebrity scores for the worldwide leaderboard --
  -- entered by an admin (see isAdmin() in routes/leaderboard.js), not
  -- scraped, so the worldwide leaderboard can be computed live with no
  -- external data source or daily batch job.
  CREATE TABLE IF NOT EXISTS celebrity_scores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    shot_type  TEXT NOT NULL CHECK (shot_type IN (${shotTypesSqlIn})),
    score      REAL NOT NULL,
    note       TEXT,
    added_by   INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- Drills & Lessons library (Dev Page-authored, see routes/dev.js). A
  -- 'drill' is a free standalone library item (no routine steps needed). A
  -- 'lesson' is the bigger watch->learn->practice flow -- same row shape,
  -- plus 1+ drill_routine_steps for its practice phase. is_premium is
  -- per-item (drills default free, lessons can be either) rather than a
  -- blanket requirePremium on the whole route, so free drills stay free.
  CREATE TABLE IF NOT EXISTS drill_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT NOT NULL CHECK (kind IN ('drill', 'lesson')),
    shot_type      TEXT NOT NULL,
    title          TEXT NOT NULL,
    video_path     TEXT,
    explanation    TEXT NOT NULL,
    emphasis       TEXT,
    diagram_tip_id TEXT,
    is_premium     INTEGER NOT NULL DEFAULT 0,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    archived       INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
  );

  -- A lesson's ordered practice steps (e.g. "Crosscourt forehand x10" then
  -- "Down-the-line forehand x10"). shot_type is NULL for a step with no
  -- practice-analysis part (e.g. a pure rest/footwork instruction).
  CREATE TABLE IF NOT EXISTS drill_routine_steps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    drill_item_id INTEGER NOT NULL REFERENCES drill_items(id),
    step_order    INTEGER NOT NULL,
    label         TEXT NOT NULL,
    shot_type     TEXT,
    target_reps   INTEGER
  );

  -- One row per practice attempt, linking a routine step to the REAL
  -- analysis it produced -- practice reuses the existing /api/analyse
  -- pipeline/scoring rather than a separate one.
  CREATE TABLE IF NOT EXISTS drill_practice_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    step_id     INTEGER NOT NULL REFERENCES drill_routine_steps(id),
    analysis_id INTEGER REFERENCES analyses(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
  );
`);

// No migrations framework here -- CREATE TABLE IF NOT EXISTS above is
// naturally idempotent, but adding a column to an existing table needs its
// own guard so this doesn't error on every restart once the column exists.
const hasNotifCol = db.prepare("PRAGMA table_info(users)").all()
  .some((c) => c.name === 'notifications_enabled');
if (!hasNotifCol) {
  db.exec('ALTER TABLE users ADD COLUMN notifications_enabled INTEGER NOT NULL DEFAULT 1');
}

// boundary_note: Jack's review-pass signal for whether a detected rally's
// start/end boundaries look right ('cut_off_early' | 'should_split' | 'ok'),
// separate from outcome_tag (which is about the point's outcome, not the
// clip's boundaries) -- used to tune RALLY_GAP_SEC/THRESHOLD_PERCENTILE
// against real match footage instead of guessing.
const hasBoundaryNoteCol = db.prepare("PRAGMA table_info(rally_clips)").all()
  .some((c) => c.name === 'boundary_note');
if (!hasBoundaryNoteCol) {
  db.exec('ALTER TABLE rally_clips ADD COLUMN boundary_note TEXT');
}

// flagged_not_shot: any user can mark one of their own saved analyses as
// not actually being a real shot (camera fiddling, ball bouncing, etc.)
// -- real human ground truth for scripts/16_shot_verification/'s
// teacher-student loop, logged the same way Claude's own verdicts are
// (see backend/src/routes/history.js's PATCH handler).
const hasFlaggedNotShotCol = db.prepare("PRAGMA table_info(analyses)").all()
  .some((c) => c.name === 'flagged_not_shot');
if (!hasFlaggedNotShotCol) {
  db.exec('ALTER TABLE analyses ADD COLUMN flagged_not_shot INTEGER NOT NULL DEFAULT 0');
}

// The other direction of the same feedback loop -- a user actively
// confirming "yes, this really is a shot," not just flagging bad ones.
// Two independent booleans (mutually exclusive at the UI/route level, not
// enforced in the schema) rather than one tri-state column, so existing
// flagged_not_shot data/queries don't need migrating.
const hasConfirmedRealShotCol = db.prepare("PRAGMA table_info(analyses)").all()
  .some((c) => c.name === 'confirmed_real_shot');
if (!hasConfirmedRealShotCol) {
  db.exec('ALTER TABLE analyses ADD COLUMN confirmed_real_shot INTEGER NOT NULL DEFAULT 0');
}

// username: optional, set later via Profile (not required at signup) -- a
// separate handle from the free-text `name` display field, unique across
// all users. Nullable so existing accounts aren't broken; SQLite treats
// multiple NULLs as distinct under a UNIQUE index, so this is safe even
// before anyone has set one.
const hasUsernameCol = db.prepare("PRAGMA table_info(users)").all()
  .some((c) => c.name === 'username');
if (!hasUsernameCol) {
  db.exec('ALTER TABLE users ADD COLUMN username TEXT');
}
db.exec('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)');

// token_version: bumped whenever a user's password changes (self-service
// PATCH /auth/password, or a successful /auth/reset-password) or their
// account is deleted (auth.js anonymizes the row rather than removing it,
// so a stolen pre-deletion token would otherwise keep working). requireAuth
// and optionalAuth embed the value active at signing time in each JWT (see
// issueToken() in routes/auth.js) and compare it against this column on
// every request -- unlike tier, which was already re-read from the DB per
// request for exactly this staleness reason (see utils/tier.js's comment),
// this JWT claim had no equivalent freshness check at all: a 30-day token
// kept working through a password change or account deletion with no way
// to revoke it short of rotating JWT_SECRET for every user at once.
const hasTokenVersionCol = db.prepare("PRAGMA table_info(users)").all()
  .some((c) => c.name === 'token_version');
if (!hasTokenVersionCol) {
  db.exec('ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0');
}

// verified: OSM-seeded courts are trusted immediately (default 1); a
// user-dropped pin starts at 0 and only flips to 1 once routes/courts.js
// sees enough independent court_confirmations rows for it.
const hasVerifiedCol = db.prepare("PRAGMA table_info(courts)").all()
  .some((c) => c.name === 'verified');
if (!hasVerifiedCol) {
  db.exec('ALTER TABLE courts ADD COLUMN verified INTEGER NOT NULL DEFAULT 1');
}

// submitted_by: who dropped the pin -- needed so routes/courts.js can block
// a submitter from confirming their own court, and null for OSM-seeded rows.
const hasSubmittedByCol = db.prepare("PRAGMA table_info(courts)").all()
  .some((c) => c.name === 'submitted_by');
if (!hasSubmittedByCol) {
  db.exec('ALTER TABLE courts ADD COLUMN submitted_by INTEGER REFERENCES users(id)');
}

// GET /courts's queryNearbyCourts runs a bounding-box scan plus a LEFT JOIN
// and several correlated subqueries per row on every request -- fine
// against a small local seed, but the courts table is now ~33k rows after
// the England-wide OSM seed, and better-sqlite3 runs synchronously on
// Node's main thread, so an unindexed scan at that size blocks the whole
// server for the duration of the query (the actual cause of "courts don't
// reliably show up" -- intermittent timeouts, not a real absence of data).
db.exec('CREATE INDEX IF NOT EXISTS idx_courts_lat_lng ON courts(latitude, longitude)');
db.exec('CREATE INDEX IF NOT EXISTS idx_club_courts_court_id ON club_courts(court_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_club_courts_club_id ON club_courts(club_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_court_confirmations_court_id ON court_confirmations(court_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_club_watches_club_id ON club_watches(club_id)');

// Everything below was audited against every route file's actual WHERE/JOIN
// usage (not guessed from the schema) -- these are the foreign-key/lookup
// columns real hot paths filter on that had no index at all until now:
// history loads, message-thread open/poll, highlight-job/rally-clip
// polling, coach-note lookups, push-token lookups, and Drills & Lessons
// practice-attempt counts. Deliberately NOT indexed here (already covered):
// users.email (UNIQUE, auto-indexed), and coach_links(coach_id,student_id),
// shared_analyses(analysis_id,friend_id), user_blocks(blocker_id,blocked_id)
// -- each already has a UNIQUE(...) constraint whose auto-index (or its
// leftmost-column prefix) already covers every real query against that
// table, confirmed by reading each query site rather than assumed from the
// schema.
db.exec('CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_messages_user_a_b ON messages(user_a_id, user_b_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_rally_clips_user_id ON rally_clips(user_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_rally_clips_job_id ON rally_clips(job_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_highlight_jobs_user_id ON highlight_jobs(user_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_coach_notes_analysis_id ON coach_notes(analysis_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_push_tokens_user_id ON push_tokens(user_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_drill_practice_attempts_step_user ON drill_practice_attempts(step_id, user_id)');

// The six below were added after auditing real query sites against what
// was actually indexed (2026-08-22). Two shapes kept showing up:
//   1. `WHERE user_a_id = ? OR user_b_id = ?` (messages.js, leaderboard.js)
//      -- a compound index, or a UNIQUE(user_a_id, user_b_id) constraint's
//      auto-index, only serves the LEFTMOST column of an OR query; the
//      second leg still forces a full table scan. friend_links(user_a_id,
//      user_b_id) was previously assumed "already covered" by its UNIQUE
//      constraint above -- that assumption was wrong for this query shape.
//   2. A column with real per-request query traffic but no index at all
//      (analysis_usage.user_id on every /api/analyse call; court_id on two
//      courts.js routes against a ~33k-court table; analyses.shot_type on
//      the worldwide leaderboard).
db.exec('CREATE INDEX IF NOT EXISTS idx_messages_user_b_id ON messages(user_b_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_friend_links_user_b_id ON friend_links(user_b_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_analysis_usage_user_created ON analysis_usage(user_id, created_at)');
db.exec('CREATE INDEX IF NOT EXISTS idx_court_watches_court_id ON court_watches(court_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_availability_posts_court_id ON availability_posts(court_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_analyses_shot_type ON analyses(shot_type)');

// Self-serve password reset. Only the sha256 hash of the reset token is
// ever stored (auth.js hashes it before the INSERT) -- same reasoning as
// never storing a plaintext password, even though this token is
// short-lived (1 hour, enforced in auth.js). used_at is set rather than
// deleting the row, so a reused/replayed token fails cleanly instead of
// just not being found.
db.exec(`
  CREATE TABLE IF NOT EXISTS password_resets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at    TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );
`);
db.exec('CREATE INDEX IF NOT EXISTS idx_password_resets_token_hash ON password_resets(token_hash)');
db.exec('CREATE INDEX IF NOT EXISTS idx_password_resets_user_id ON password_resets(user_id)');

// analysis_usage only exists to answer "how many today" (see
// usageLimit.js's `date(created_at) = date('now')`) -- every row past
// yesterday is dead weight. It was previously only ever pruned on a
// failed analysis (usageLimit.releaseUsageSlot) or full account deletion,
// so a normal successful-analysis row lived forever. A 2-day retention
// keeps yesterday's rows around for any date-boundary edge case around
// midnight, at negligible size (one row per free-tier analysis).
db.prepare("DELETE FROM analysis_usage WHERE created_at < datetime('now', '-2 days')").run();

module.exports = db;
